"""Inbound Socket.IO events — the write half of `/messaging` (spec §3.2).

A module of its own rather than more handlers in `realtime.py`: that file owns
the connection, the rooms and the outbound publishers, and this one owns what a
client can ask the server to do. `register_write_handlers` is the entry point,
called once from `build_asgi_app`.

Four rules run through every write handler here — `send_message`,
`edit_message`, `delete_message` and `mark_read`. `typing` persists nothing
and acks nothing, and of these rules it keeps the visibility check and only the
expiry half of the token check.

**Nothing raises.** A python-socketio handler that raises never sends its
acknowledgement, so the client's callback simply never fires and the optimistic
bubble hangs forever with no error to show. `@_acked` — S5's, imported — turns a
`ProblemException` into an error ack and anything unexpected into a 500-shaped
one. A write handler without it is the easiest bug to add to this module.

**Visibility authorizes the write, not room membership.** The delivery plan said
"a client may only act on a channel it has joined", and that is wrong twice
over. It is the wrong *test*: `POST /channels/{id}/messages` is open to anyone
who can see the channel, so gating the socket on membership would make it
stricter than the route it replaces and resurrect the bug that rule closed. And
it is not a durable *fact*: a room is per-`sid` in-memory state, lost on every
reconnect and re-established by the client's own `connect` handler — so a send
across a reconnect would race its own `join_channel` and fail for a reason no
user could act on. A room decides who *receives* a broadcast and nothing else.

**Every write re-checks the token.** A REST call verifies signature, expiry and
the denylist on every request; a socket connection is verified once and can
outlive its fifteen-minute token by hours. That was tolerable while the socket
could only read. So each write re-tests expiry and the denylist (`principal_of`,
`check_revoked`) — the signature cannot have changed since the handshake.
Without that, moving the composer onto the socket would be a security regression.

**The same domain functions the REST routers call.** Not a second copy of the
rules — `messages.create`, `messages.edit`, `messages.delete`, and the same
commit-then-publish order, so the two transports cannot drift on what is allowed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import socketio
from pydantic import Field, ValidationError

from messaging import (
    attachments,
    channels,
    dms,
    indexing,
    messages,
    reactions,
    read_state,
    realtime,
    threads,
)
from messaging.realtime import NAMESPACE, RealtimeContext, _acked, _ok
from messaging.routers.messages import _as_message, publish_reply_summary, summary_of
from messaging.schemas import MAX_BODY_FIELD_LENGTH, CamelRequest
from shared import ProblemException, TokenState, UserPrincipal, uuid7

_log = logging.getLogger("collabhub.messaging.realtime_writes")


class SendMessagePayload(CamelRequest):
    """`send_message`: `{channelId, body, threadRootId?, attachmentIds?}` (spec §3.2).

    `threadRootId` makes the message a reply, normalised under its root exactly
    as the REST route does.

    `attachmentIds` is optional, and a client sends it only when there are some.
    The rules are the REST body's, checked by the same domain functions.

    Validated here rather than in `schemas.py`: these are not REST bodies, they
    never appear in the OpenAPI document, and they belong beside the handlers
    that read them.
    """

    channel_id: uuid.UUID
    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)
    thread_root_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class EditMessagePayload(CamelRequest):
    """`edit_message` — **with `version`**, which spec §3.2 originally omitted.

    The expected version is required on `PATCH /messages/{id}`, and a socket
    event without one would make this the way to lose someone else's edit
    silently. One rule, two transports.
    """

    message_id: uuid.UUID
    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)
    version: int


class DeleteMessagePayload(CamelRequest):
    """Unconditional, so no `version` — a channel admin deleting a message its
    author has just edited is not a conflict worth surfacing."""

    message_id: uuid.UUID


class MarkReadPayload(CamelRequest):
    """`mark_read`: `{channelId, messageId}` (spec §3.2)."""

    channel_id: uuid.UUID
    message_id: uuid.UUID


class TypingPayload(CamelRequest):
    channel_id: uuid.UUID


def _parse(model: type[CamelRequest], payload: Any) -> Any:
    """Validate an inbound payload, or raise it as a 400 `ProblemException`.

    A bare `ValidationError` would reach `@_acked` as an unexpected error and ack
    a 500. At most five validation messages are passed on.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ProblemException.validation_error(
            "The event payload is not valid.",
            errors={"payload": [e["msg"] for e in exc.errors()][:5]},
        ) from exc


def register_write_handlers(  # noqa: C901 — a registry of handlers; mccabe counts each one
    sio: socketio.AsyncServer, context: RealtimeContext
) -> None:
    """Attach the inbound events to a server S5 already built."""

    async def principal_of(sid: str) -> UserPrincipal:
        """The connection's principal, plus the expiry check the handshake made only once.

        Expiry is re-tested on **every** inbound event including `typing`: it
        costs nothing and it is the difference between a connection that is
        authenticated and one that merely was.
        """
        session = await sio.get_session(sid, namespace=NAMESPACE)
        principal: UserPrincipal = session["principal"]

        if principal.expires_at <= datetime.now(UTC):
            raise ProblemException.unauthorized("The access token has expired.")
        return principal

    async def check_revoked(principal: UserPrincipal) -> None:
        """The denylist half, on writes only, and **fail-open** on an outage.

        Only `REVOKED` refuses. Channel writes are outside the fail-closed set in
        Conventions §5.2 — the REST routers say so in their own docstrings — so
        any other state, an unreachable R1 included, accepts the write exactly as
        it accepts a `GET`.

        `typing` skips this entirely: it persists nothing, and a Redis round trip
        per typing event is real load for no authority gained.
        """
        state = await context.security.denylist.state(principal.token_id)
        if state is TokenState.REVOKED:
            raise ProblemException.unauthorized("The access token has been revoked.")

    async def authorized_channel(
        session, principal: UserPrincipal, channel_id: uuid.UUID
    ) -> channels.VisibleChannel:
        visible = await channels.get_visible(
            session,
            # From the principal, and from nothing in the payload — which has no
            # workspace field to be tempted by, exactly as the REST surface has
            # no workspace in a path.
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            channel_id=channel_id,
        )
        if visible is None:
            raise ProblemException.not_found("No such channel.")
        return visible

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def send_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(SendMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            visible = await authorized_channel(session, principal, event.channel_id)

            root_id: uuid.UUID | None = None
            if event.thread_root_id is not None:
                try:
                    root_id = await threads.resolve_root(
                        session, channel_id=event.channel_id, candidate_id=event.thread_root_id
                    )
                except threads.NoSuchThreadError as exc:
                    raise ProblemException.not_found("No such thread.") from exc

            max_attachments = context.settings.messaging_max_attachments
            try:
                attachments.check_attachment_ids(
                    event.attachment_ids, max_attachments=max_attachments
                )
            except (
                attachments.TooManyAttachmentsError,
                attachments.DuplicateAttachmentError,
            ) as exc:
                raise attachments.ids_problem(exc, max_attachments=max_attachments) from exc

            max_chars = context.settings.messaging_max_body_chars
            try:
                # Before the claim: a bad body must not claim assets for a
                # message that will never exist.
                messages.validate_body(
                    event.body, max_chars=max_chars, allow_empty=bool(event.attachment_ids)
                )
            except messages.BodyRequiredError as exc:
                raise _body_problem("A message cannot be empty.") from exc
            except messages.BodyTooLongError as exc:
                raise _body_problem(f"A message must be {max_chars} characters or fewer.") from exc

            # Before the insert, as the REST route does (plan decision 15).
            first_in_dm = await dms.opens_dm(session, visible.channel, thread_root_id=root_id)

            # Claim, then insert — the same order, and the same helper, as the
            # REST route, so the two transports cannot refuse differently.
            message_id = uuid7()
            metas = await attachments.claim_for_send(
                context.assets,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                message_id=message_id,
                asset_ids=event.attachment_ids,
            )
            created, stored = await messages.create(
                session,
                message_id=message_id,
                channel_id=event.channel_id,
                author_id=principal.user_id,
                body=event.body,
                max_chars=max_chars,
                thread_root_id=root_id,
                attachments=metas,
            )

            # A message nobody has seen yet has no reactions and no replies, so no query.
            response = _as_message(created, reactions=[], attachments=stored)
            await session.commit()

            # Commit, then publish. A broadcast for a row whose transaction failed
            # is a message that exists only in other people's windows.
            await realtime.publish_message_received(sio, response)
            pair = dms.pair_of(visible.channel) if first_in_dm else None
            if pair is not None:
                await realtime.publish_channel_added(
                    sio,
                    workspace_id=principal.workspace_id,
                    channel_id=event.channel_id,
                    user_ids=pair,
                )
            if root_id is not None:
                # Read after the commit, in this session's next transaction.
                await publish_reply_summary(session, sio, root_id, event.channel_id)
        await indexing.enqueue_upsert(context.jobs, response, workspace_id=principal.workspace_id)
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def edit_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(EditMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            try:
                edited = await messages.edit(
                    session,
                    workspace_id=principal.workspace_id,
                    user_id=principal.user_id,
                    message_id=event.message_id,
                    body=event.body,
                    expected_version=event.version,
                    max_chars=context.settings.messaging_max_body_chars,
                )
            except messages.BodyRequiredError as exc:
                raise _body_problem("A message cannot be empty.") from exc
            except messages.BodyTooLongError as exc:
                raise _body_problem(
                    f"A message must be {context.settings.messaging_max_body_chars} "
                    "characters or fewer."
                ) from exc
            except messages.AlreadyDeletedError as exc:
                raise ProblemException.conflict("This message was deleted.") from exc
            except messages.NotAuthorError as exc:
                raise ProblemException.forbidden("Only the author can edit a message.") from exc
            except messages.VersionConflictError as exc:
                raise ProblemException.conflict(
                    "This message was changed by someone else. Reload and try again."
                ) from exc

            if edited is None:
                raise ProblemException.not_found("No such channel.")

            # An edit changes the text and nothing else — the reactions and the
            # attachments stay.
            summaries = (
                await reactions.summaries_for(
                    session, message_ids=[edited.id], user_id=principal.user_id
                )
            ).get(edited.id, [])
            stored = await attachments.for_messages(session, [edited.id])
            response = _as_message(
                edited,
                reactions=summaries,
                attachments=stored.get(edited.id, []),
                thread=await summary_of(session, edited),
            )
            await session.commit()

        await realtime.publish_message_edited(sio, response)
        await indexing.enqueue_upsert(context.jobs, response, workspace_id=principal.workspace_id)
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def delete_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(DeleteMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            try:
                result = await messages.delete(
                    session,
                    workspace_id=principal.workspace_id,
                    user_id=principal.user_id,
                    message_id=event.message_id,
                )
            except messages.NotDeletableError as exc:
                raise ProblemException.forbidden(
                    "Only the author or a channel admin can delete a message."
                ) from exc

            if result is None:
                raise ProblemException.not_found("No such channel.")

            if result.deleted_now:
                # The REST delete clears them too: one rule, both transports.
                await reactions.clear_for_message(session, message_id=event.message_id)

            # A deleted root keeps its summary (R10); a tombstone shows no
            # attachments (`_as_message` applies `visible`).
            response = _as_message(
                result.message,
                reactions=[],
                attachments=[],
                thread=await summary_of(session, result.message),
            )
            await session.commit()

            await realtime.publish_message_deleted(sio, response)
            if result.deleted_now and result.message.thread_root_id is not None:
                # A deleted reply lowers its root's count, read after the commit.
                await publish_reply_summary(
                    session, sio, result.message.thread_root_id, result.message.channel_id
                )
        # A repeat delete changed nothing, so it has nothing to index.
        if result.deleted_now:
            await indexing.enqueue_delete(
                context.jobs, response, workspace_id=principal.workspace_id
            )
        # The tombstone, not an id — the row stays in the history and the client
        # that issued the delete has to render it like everyone else.
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def mark_read(sid: str, payload: Any) -> dict[str, Any]:
        """Move the caller's read marker; tell their other sessions if it moved.

        A write, so it gets the write checks — expiry and the denylist, failing
        open — even though what it writes is only ever the caller's own.
        """
        event = _parse(MarkReadPayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            advanced = await read_state.mark_read(
                session,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                channel_id=event.channel_id,
                message_id=event.message_id,
            )
            if advanced is None:
                raise ProblemException.not_found("No such channel.")
            await session.commit()

        if advanced:
            await realtime.publish_read_receipt(
                sio,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                channel_id=event.channel_id,
                message_id=event.message_id,
                # This tab already knows; the broadcast is for the others.
                skip_sid=sid,
            )
        return _ok()

    @sio.event(namespace=NAMESPACE)
    async def typing(sid: str, payload: Any) -> None:
        """Fan out that someone is typing. Ephemeral, and never persisted.

        **No acknowledgement**: there is nothing to confirm. No `typing_stopped`
        either — the receiver expires an indicator on a timer, because a server
        tracking who is typing would need that state shared across pods through
        R2 for something the design calls ephemeral, and would still have to
        invent a timeout for the client that closed its laptop mid-word.

        The payload carries no display name. Messaging holds none, and the
        browser already resolves every other name from the workspace directory;
        a second source for the same name invites drift, even on an event too
        short-lived to go stale.

        **Authorized on channel visibility**, like every write, with the
        workspace from the principal. The fan-out is to a room, and a room says
        nothing about who may *send* to it: without this, anyone could put their
        name into another workspace's channel, or a private one they are not in.
        It costs one query per typing event, which the client's 2s throttle keeps
        cheap. The denylist is still skipped — see `check_revoked`.
        """
        try:
            event = _parse(TypingPayload, payload)
            principal = await principal_of(sid)
            async with context.sessions() as session:
                await authorized_channel(session, principal, event.channel_id)
        except ProblemException:
            # Nothing to ack, so nothing to tell. A malformed or expired typing
            # event, or one for a channel the sender cannot see, is simply not
            # fanned out.
            return

        await sio.emit(
            "user_typing",
            {"channelId": str(event.channel_id), "userId": str(principal.user_id)},
            room=realtime.room(event.channel_id),
            namespace=NAMESPACE,
            # The sender never sees their own indicator. The client also
            # discards its own `userId`, which covers the second tab that
            # `skip_sid` cannot.
            skip_sid=sid,
        )


def _body_problem(message: str) -> ProblemException:
    """The same shape the REST route produces, so one client parser serves both."""
    return ProblemException.validation_error(message, errors={"body": [message]})
