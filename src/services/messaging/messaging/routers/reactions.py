"""Reaction endpoints (doc 02 §3.1.5).

Its own module rather than two more routes in `routers/messages.py`: a reaction
is a different resource with a different body, and that file is already the
longest in the service.

**Visibility is the guard**, through `_visible_message` — the same
404-before-403 path every message route uses, with the same `"No such channel."`
wording, so an id cannot be used as an oracle. Anyone who can *see* the channel
may react: there is no membership gate and no admin gate, because reacting is
talking, not administering.

**Both routes return the whole message.** `PATCH` and `DELETE` on a message
already do, so the SPA writes the response through the one cache helper it
already has rather than growing a second cache keyed by message.

**Both are idempotent**, and that is the composite primary key doing the work
rather than a check-then-write. Reacting twice leaves one row; removing a
reaction that was never there is a 200 with the message unchanged.
"""

from __future__ import annotations

import uuid

import socketio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import reactions, realtime
from messaging.db import session as db_session
from messaging.models import Message
from messaging.routers.messages import _as_message, _visible_message, summary_of
from messaging.schemas import MessageResponse, ReactionRequest
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/messages", tags=["reactions"])


def _validated(emoji: str) -> str:
    """The allowlist check, as a Problem Details 400 under `errors.emoji`.

    400 rather than 422 because that is what `ProblemException.validation_error`
    means everywhere else on this platform — the same answer an empty message
    body gets.
    """
    try:
        return reactions.validate(emoji)
    except reactions.UnknownEmojiError as exc:
        message = "That is not a reaction you can use."
        raise ProblemException.validation_error(message, errors={"emoji": [message]}) from exc


def _state_of(summaries: list[reactions.Summary], emoji: str) -> tuple[int, bool]:
    """One emoji's count and the caller's own state, after the write.

    Read off the summaries already built for the response, so the broadcast
    costs no second query. An emoji nobody uses any more is `(0, False)`, which
    is how a chip disappears in every other window.
    """
    for summary in summaries:
        if summary.emoji == emoji:
            return summary.count, summary.reacted
    return 0, False


async def _respond(
    session: AsyncSession,
    principal: UserPrincipal,
    sio: socketio.AsyncServer | None,
    message: Message,
    emoji: str,
) -> MessageResponse:
    """Build the DTO, commit, then broadcast — the order every write here uses.

    A broadcast for a row whose transaction then failed is a count that exists
    only in other people's windows.
    """
    summaries = (
        await reactions.summaries_for(session, message_ids=[message.id], user_id=principal.user_id)
    ).get(message.id, [])
    # A root keeps its reply summary through a reaction, or the event the client
    # applies it from would zero "2 replies".
    response = _as_message(message, reactions=summaries, thread=await summary_of(session, message))
    await session.commit()

    count, reacted = _state_of(summaries, emoji)
    await realtime.publish_reaction_changed(
        sio,
        channel_id=message.channel_id,
        message_id=message.id,
        emoji=emoji,
        count=count,
        user_id=principal.user_id,
        reacted=reacted,
        thread_root_id=message.thread_root_id,
    )
    return response


@router.post("/{message_id}/reactions", response_model=MessageResponse)
async def add_reaction(
    message_id: uuid.UUID,
    body: ReactionRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """React to a message. Reacting again with the same emoji changes nothing.

    **200 rather than 201.** The useful answer is the message's new counts, and
    a repeat is not a creation — there is no new resource to point at either
    time, because a reaction is not addressable on its own.
    """
    message = await _visible_message(session, principal, message_id)
    emoji = _validated(body.emoji)

    if not reactions.may_react(message):
        # 409 and not 404: the caller can see this tombstone in the history they
        # are reading, so "no such message" would be a lie about a row on their
        # screen. The same argument `edit_message` makes.
        raise ProblemException.conflict("This message was deleted.")

    await reactions.add(session, message_id=message_id, user_id=principal.user_id, emoji=emoji)
    return await _respond(session, principal, sio, message, emoji)


@router.delete("/{message_id}/reactions/{emoji}", response_model=MessageResponse)
async def remove_reaction(
    message_id: uuid.UUID,
    emoji: str,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """Take a reaction back.

    **No tombstone check, unlike the add.** Deleting a message clears its
    reactions, so there is never anything on one to remove — and a second tab
    that has already removed it must not be told the message is in the wrong
    state for what is a no-op.
    """
    message = await _visible_message(session, principal, message_id)
    emoji = _validated(emoji)

    await reactions.remove(session, message_id=message_id, user_id=principal.user_id, emoji=emoji)
    return await _respond(session, principal, sio, message, emoji)
