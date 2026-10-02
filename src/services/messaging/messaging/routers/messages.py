"""Message endpoints (spec §3.1).

A separate module from `routers/channels.py` even though two of the three routes
hang off `/channels/{id}`: these are a different resource with a different
authority rule, and they own different rows of the design doc's endpoint table.

**Visibility is the guard, for reading and for writing.** Every route here goes
through `channels.get_visible` and never through `channels.is_member`. Spec §3.1
says "channel member" against these rows; taken literally it would make a public
channel readable only by whoever created it, because nothing in this scope lets
anyone join a channel themselves. Membership gates administering a channel, not
talking in one.

**A channel you cannot see is a 404, and so is a message in it.** The two misses
raise the same wording deliberately: a caller must not be able to tell "no such
message" from "not your channel", or the id becomes an oracle.

**Plain `require_user`.** Messages are not in the fail-closed denylist set
(Conventions §5.2, spec §3.1), so an unreachable R1 fails open here as it does
for ordinary reads.

**Every write publishes to the channel's room after it commits, never before.**
A broadcast for a row whose transaction then fails is a message that exists only
in other people's windows. `sio` is `None` under `ASGITransport`, so the
publisher is a return statement in every integration test — the router code is
the same either way. Then, for the search index, it enqueues a `jobs:index` job —
fire-and-forget, see `indexing.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import socketio
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import attachments as attachments_domain
from messaging import channels, indexing, messages, realtime, threads
from messaging import reactions as reactions_domain
from messaging.assets import AssetClient, AssetUnavailableError, AttachmentNotFoundError
from messaging.db import session as db_session
from messaging.models import Message, MessageAttachment
from messaging.schemas import (
    Attachment,
    AttachmentDownloadResponse,
    EditMessageRequest,
    MessageListResponse,
    MessageResponse,
    ReactionSummary,
    SendMessageRequest,
    ThreadResponse,
)
from messaging.settings import Settings
from shared import (
    JobQueue,
    PageRequest,
    ProblemException,
    UserPrincipal,
    page_request_for,
    require_user,
    uuid7,
)

#: Two prefixes, one surface. History and sending hang off the channel that owns
#: them; a single message is addressable on its own.
channel_router = APIRouter(prefix="/api/v1/channels", tags=["messages"])
router = APIRouter(prefix="/api/v1/messages", tags=["messages"])

HistoryPage = Annotated[PageRequest, Depends(page_request_for(*messages.HISTORY_CURSOR))]

#: One message per rule, so the composer can put it against the field rather
#: than showing "invalid message" and leaving the user to guess.
_BODY_PROBLEMS: dict[type[Exception], str] = {
    messages.BodyRequiredError: "A message cannot be empty.",
    messages.BodyTooLongError: "A message must be {max_chars} characters or fewer.",
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _assets(request: Request) -> AssetClient:
    """The app's Asset client — one per process, built in `create_app`."""
    return request.app.state.assets


def _body_problem(exc: Exception, *, max_chars: int) -> ProblemException:
    message = _BODY_PROBLEMS[type(exc)].format(max_chars=max_chars)
    return ProblemException.validation_error(message, errors={"body": [message]})


def _as_message(
    row: Message,
    *,
    reactions: list[reactions_domain.Summary],
    attachments: list[MessageAttachment],
    thread: threads.Summary = threads.NO_REPLIES,
) -> MessageResponse:
    """The DTO, with a deleted row's body redacted here rather than in the query.

    Server-side, and `""` rather than `null`: the DTO types `body` as a non-null
    string, so a null would force a check at every render site in the SPA. The
    client renders the tombstone from `deletedAt`.

    **Built field by field rather than validated from the row.** `reactions` is
    neither a column nor a relationship — it is an aggregate the caller has
    already run for a whole page, and making it a relationship would turn it
    into a query per message. So there is nothing on the row for
    `model_validate` to read.

    **`reactions` and `attachments` are required and keyword-only.** Every
    caller has to say what this message's are, including the ones that say `[]`,
    because a default would make a forgotten aggregate look exactly like a
    message nobody reacted to or attached anything to. Both are loaded page-wide
    by the caller. `attachments` is passed through `visible`, so a tombstone
    shows none however the caller loaded them.

    **`thread` is a root's reply summary, and every caller that builds a DTO
    from a stored row must pass it** — an edit, a reaction or a delete that
    answered "no replies" would overwrite "2 replies" in every window through
    the event it publishes. It defaults to `NO_REPLIES` only because the
    callers that mean exactly that (a reply, a message just sent, the index
    payload's fixtures) are the ones with nothing to look up.
    """
    return MessageResponse(
        id=row.id,
        channel_id=row.channel_id,
        author_id=row.author_id,
        thread_root_id=row.thread_root_id,
        body="" if row.deleted_at else row.body,
        attachments=[
            Attachment(
                asset_id=a.asset_id,
                file_name=a.file_name,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
            )
            for a in attachments_domain.visible(row, attachments)
        ],
        reactions=[
            ReactionSummary(emoji=s.emoji, count=s.count, reacted=s.reacted) for s in reactions
        ],
        created_at=row.created_at,
        edited_at=row.edited_at,
        deleted_at=row.deleted_at,
        version=row.version,
        reply_count=thread.reply_count,
        last_reply_at=thread.last_reply_at,
    )


async def summary_of(session: AsyncSession, row: Message) -> threads.Summary:
    """A stored row's own reply summary: a reply has none, a root is aggregated."""
    if threads.is_reply(row):
        return threads.NO_REPLIES
    return await threads.summary_for(session, root_id=row.id)


async def publish_reply_summary(
    session: AsyncSession,
    sio: socketio.AsyncServer | None,
    root_id: uuid.UUID,
    channel_id: uuid.UUID,
) -> None:
    """Broadcast a root's summary, **read now** — call it after the commit.

    The session's next statement begins a new transaction (READ COMMITTED), so
    it counts every reply committed so far, this one included; read before the
    commit, two concurrent replies would each count only themselves.
    """
    summary = await threads.summary_for(session, root_id=root_id)
    await realtime.publish_thread_summary_changed(
        sio, channel_id=channel_id, root_id=root_id, summary=summary
    )


async def _one_with_reactions(
    session: AsyncSession, principal: UserPrincipal, row: Message
) -> MessageResponse:
    """One message's DTO, with its own reactions and reply summary loaded.

    The single-message counterpart to the page-wide aggregates in
    `list_messages`: same queries, one id.
    """
    found = await reactions_domain.summaries_for(
        session, message_ids=[row.id], user_id=principal.user_id
    )
    stored = await attachments_domain.for_messages(session, [row.id])
    return _as_message(
        row,
        reactions=found.get(row.id, []),
        attachments=stored.get(row.id, []),
        thread=await summary_of(session, row),
    )


async def _visible_channel(
    session: AsyncSession, principal: UserPrincipal, channel_id: uuid.UUID
) -> channels.VisibleChannel:
    found = await channels.get_visible(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
    )
    if found is None:
        raise ProblemException.not_found("No such channel.")
    return found


async def _visible_message(
    session: AsyncSession, principal: UserPrincipal, message_id: uuid.UUID
) -> Message:
    """A message, if the caller can see the channel it is in.

    Both halves raise the same 404 wording on purpose — see the module
    docstring.
    """
    found = await messages.get(session, message_id=message_id)
    if found is None:
        raise ProblemException.not_found("No such channel.")

    await _visible_channel(session, principal, found.channel_id)
    return found


@channel_router.get("/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    channel_id: uuid.UUID,
    page: HistoryPage,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> MessageListResponse:
    """A channel's history, newest first, cursor-paginated (Conventions §4.1).

    Deleted messages are included, with their bodies redacted — the tombstone is
    part of the history, not something the client reconstructs.
    """
    await _visible_channel(session, principal, channel_id)

    found = await messages.history_page(session, channel_id=channel_id, page=page)
    # One grouped query for the whole page, never one per message.
    summaries = await reactions_domain.summaries_for(
        session, message_ids=[m.id for m in found.items], user_id=principal.user_id
    )
    counts = await threads.summaries_for(session, root_ids=[m.id for m in found.items])
    stored = await attachments_domain.for_messages(session, [m.id for m in found.items])
    return MessageListResponse(
        items=[
            _as_message(
                m,
                reactions=summaries.get(m.id, []),
                attachments=stored.get(m.id, []),
                thread=counts.get(m.id, threads.NO_REPLIES),
            )
            for m in found.items
        ],
        next_cursor=found.next_cursor,
    )


@channel_router.post(
    "/{channel_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    channel_id: uuid.UUID,
    body: SendMessageRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
    jobs: JobQueue = Depends(indexing.queue),
    assets: AssetClient = Depends(_assets),
) -> MessageResponse:
    """Say something in a channel the caller can see, with up to ten files.

    Spec §3.1 keeps this as the REST fallback once the Socket.IO send exists;
    both call the same domain function, so the rules cannot drift between them.

    **Claim, then insert.** Everything that can be refused is refused first —
    visibility, the attachment count, the body — then the message's id is
    chosen, its assets are claimed from Asset for that id, and only then is the
    message written. A refused or unreachable claim (409, 503) leaves nothing
    behind. The body is checked *before* the claim: a bad body must not claim
    assets for a message that will never exist.
    """
    await _visible_channel(session, principal, channel_id)
    settings = _settings(request)
    max_chars = settings.messaging_max_body_chars

    root_id: uuid.UUID | None = None
    if body.thread_root_id is not None:
        # An unknown id and one in another channel answer the same, so ids
        # cannot be probed (CH004). Refused before anything is created.
        try:
            root_id = await threads.resolve_root(
                session, channel_id=channel_id, candidate_id=body.thread_root_id
            )
        except threads.NoSuchThreadError as exc:
            raise ProblemException.not_found("No such thread.") from exc

    try:
        attachments_domain.check_attachment_ids(
            body.attachment_ids, max_attachments=settings.messaging_max_attachments
        )
    except (
        attachments_domain.TooManyAttachmentsError,
        attachments_domain.DuplicateAttachmentError,
    ) as exc:
        raise attachments_domain.ids_problem(
            exc, max_attachments=settings.messaging_max_attachments
        ) from exc
    try:
        messages.validate_body(
            body.body, max_chars=max_chars, allow_empty=bool(body.attachment_ids)
        )
    except tuple(_BODY_PROBLEMS) as exc:
        raise _body_problem(exc, max_chars=max_chars) from exc

    message_id = uuid7()
    metas = await attachments_domain.claim_for_send(
        assets,
        # The token's `wsp` and `sub`: the claim is for the caller, in their workspace.
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        message_id=message_id,
        asset_ids=body.attachment_ids,
    )
    created, stored = await messages.create(
        session,
        message_id=message_id,
        channel_id=channel_id,
        author_id=principal.user_id,
        body=body.body,
        max_chars=max_chars,
        thread_root_id=root_id,
        attachments=metas,
    )

    # A message nobody has seen yet has no reactions and no replies, so this one
    # needs no query.
    response = _as_message(created, reactions=[], attachments=stored)
    await session.commit()
    await realtime.publish_message_received(sio, response)
    if root_id is not None:
        await publish_reply_summary(session, sio, root_id, channel_id)
    await indexing.enqueue_upsert(jobs, response, workspace_id=principal.workspace_id)
    return response


@router.get("/{message_id}/thread", response_model=ThreadResponse)
async def get_thread(
    message_id: uuid.UUID,
    page: HistoryPage,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ThreadResponse:
    """A root and a page of its replies, newest first, tombstones included.

    Visibility is the guard, as on every message route (spec §3.1.1). Naming a
    reply is a 404 with its own wording: the caller can see the reply, so
    saying what is wrong with the id leaks nothing.
    """
    row = await _visible_message(session, principal, message_id)
    if threads.is_reply(row):
        raise ProblemException.not_found("No such thread.")

    found = await threads.replies_page(session, root_id=row.id, page=page)
    # The root and the page's replies in one reactions query, and one attachments query.
    ids = [row.id, *(m.id for m in found.items)]
    reacted = await reactions_domain.summaries_for(
        session, message_ids=ids, user_id=principal.user_id
    )
    stored = await attachments_domain.for_messages(session, ids)
    root = _as_message(
        row,
        reactions=reacted.get(row.id, []),
        attachments=stored.get(row.id, []),
        thread=await threads.summary_for(session, root_id=row.id),
    )
    return ThreadResponse(
        root=root,
        items=[
            _as_message(m, reactions=reacted.get(m.id, []), attachments=stored.get(m.id, []))
            for m in found.items
        ],
        next_cursor=found.next_cursor,
    )


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> MessageResponse:
    """One message, if the caller can see the channel it is in."""
    row = await _visible_message(session, principal, message_id)
    return await _one_with_reactions(session, principal, row)


@router.get(
    "/{message_id}/attachments/{asset_id}/download-url",
    response_model=AttachmentDownloadResponse,
)
async def attachment_download_url(
    message_id: uuid.UUID,
    asset_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    assets: AssetClient = Depends(_assets),
) -> AttachmentDownloadResponse:
    """A short-lived URL for one attachment, for anyone who can see the message.

    **This is where download authorization lives** (register D43): Asset has no
    public download route, so a file can only be fetched through a message, and a
    message can only be seen by someone who can see its channel.

    A channel the caller cannot see, or no such message, is the usual `No such
    channel.`. After that Messaging's *own* record decides: a deleted message, or
    an asset that is not on this one, is `No such attachment.` without asking
    Asset, which would happily mint a URL for either. 503 when Asset is down.
    """
    message = await _visible_message(session, principal, message_id)
    stored = await attachments_domain.for_messages(session, [message.id])
    if attachments_domain.find_on(message, stored.get(message.id, []), asset_id) is None:
        raise ProblemException.not_found("No such attachment.")

    try:
        minted = await assets.download_url(
            workspace_id=principal.workspace_id, message_id=message.id, asset_id=asset_id
        )
    except AttachmentNotFoundError as exc:
        raise ProblemException.not_found("No such attachment.") from exc
    except AssetUnavailableError as exc:
        raise ProblemException.service_unavailable(
            "Attachments can't be fetched right now."
        ) from exc
    return AttachmentDownloadResponse(url=minted.url, expires_at=minted.expires_at)


@router.patch("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: uuid.UUID,
    body: EditMessageRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
    jobs: JobQueue = Depends(indexing.queue),
) -> MessageResponse:
    """Rewrite a message. **The author, and nobody else.**

    Not even a channel admin, who *can* delete this message. That asymmetry is
    the point rather than an oversight: deleting someone's words is moderation,
    and rewriting them under their name is forgery.

    403 here and not 404, which is the opposite of the channel rules two files
    over — and correct. A message the caller cannot see never reaches this
    check; one they can see is already on their screen, so refusing the edit
    discloses nothing, and a 404 would be a lie about a row they are looking at.

    There is no time window (register D8d).
    """
    max_chars = _settings(request).messaging_max_body_chars

    try:
        edited = await messages.edit(
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            message_id=message_id,
            body=body.body,
            expected_version=body.version,
            max_chars=max_chars,
        )
    except tuple(_BODY_PROBLEMS) as exc:
        raise _body_problem(exc, max_chars=max_chars) from exc
    except messages.AlreadyDeletedError as exc:
        # 409, not 404: the tombstone is right there in the history the caller
        # is reading, so "no such message" would be untrue. The request is
        # well-formed and the resource's state refuses it, which is what 409 is
        # for.
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
    response = await _one_with_reactions(session, principal, edited)
    await session.commit()
    await realtime.publish_message_edited(sio, response)
    await indexing.enqueue_upsert(jobs, response, workspace_id=principal.workspace_id)
    return response


@router.delete("/{message_id}", response_model=MessageResponse)
async def delete_message(
    message_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
    jobs: JobQueue = Depends(indexing.queue),
) -> MessageResponse:
    """Tombstone a message. The author, or an admin of its channel.

    **200 with the tombstoned message, not 204.** A delete here does not remove
    a row from the list — it stays with `body: ""` and `deletedAt` set, and the
    client has to render it. With 204 the client would have to refetch a page it
    is already holding to learn what to draw; with the row in hand it replaces
    one entry in its cache. The same argument as returning the created row from
    a `POST`, and a deliberate deviation from "DELETE returns 204" rather than a
    surprise in the OpenAPI document.

    Deleting twice returns the same tombstone, unchanged — and enqueues no
    second index job, because nothing about the document changed.
    """
    try:
        result = await messages.delete(
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            message_id=message_id,
        )
    except messages.NotDeletableError as exc:
        raise ProblemException.forbidden(
            "Only the author or a channel admin can delete a message."
        ) from exc

    if result is None:
        raise ProblemException.not_found("No such channel.")

    if result.deleted_now:
        # No orphan counts, and a tombstone carries none. In the same
        # transaction as the tombstone, so there is no window in which the
        # message is deleted and its reactions are still being counted.
        await reactions_domain.clear_for_message(session, message_id=message_id)

    # A deleted root keeps its summary and its thread (R10). No attachments: a
    # tombstone shows none (`_as_message` applies `visible`), so there is
    # nothing to load. The rows and the blobs stay (register D16).
    response = _as_message(
        result.message,
        reactions=[],
        attachments=[],
        thread=await summary_of(session, result.message),
    )
    await session.commit()
    # The redacted DTO, not an id: the row stays in the history and every
    # recipient has to render the tombstone.
    await realtime.publish_message_deleted(sio, response)
    if result.deleted_now and result.message.thread_root_id is not None:
        # A deleted reply lowers its root's count (R4), read after the commit.
        await publish_reply_summary(
            session, sio, result.message.thread_root_id, result.message.channel_id
        )
    if result.deleted_now:
        await indexing.enqueue_delete(jobs, response, workspace_id=principal.workspace_id)
    return response
