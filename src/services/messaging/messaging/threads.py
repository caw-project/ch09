"""Single-level threads (spec §3.1, register D8a).

A reply is a `messages` row with `thread_root_id` set. Everything here is either
a pure rule over a loaded row or one query over the partial index
`ix_messages_thread`; nothing imports FastAPI, so the REST routes and the
Socket.IO handlers share it.

**Replies are kept out of three places by one predicate each** — channel
history (`messages.history_page`), unread (`channels._with_read_state`) and
search hydration (`search._hydrate`) — all `thread_root_id IS NULL`. This module
is where the replies are read back.

**A root's summary is aggregated, never stored**, per page in one grouped query,
the way `reactions.summaries_for` does it: a stored counter would need
`last_reply_at` recomputed on every reply delete anyway, and two writers to keep
in step.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import messages
from messaging.models import Message
from shared import Page, PageRequest, build_page

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "NO_REPLIES",
    "NoSuchThreadError",
    "Summary",
    "is_reply",
    "replies_page",
    "resolve_root",
    "root_for",
    "summaries_for",
    "summary_for",
]


class NoSuchThreadError(Exception):
    """The named root is unknown, or lives in another channel.

    One exception for both on purpose: the router answers them identically, so an
    id from another channel cannot be told from one that does not exist.
    """


@dataclass(frozen=True)
class Summary:
    """How many live replies a root has, and when the newest one came."""

    reply_count: int
    last_reply_at: datetime | None


#: Every reply, and any message that is not a root with replies.
NO_REPLIES = Summary(0, None)


def is_reply(message: Message) -> bool:
    return message.thread_root_id is not None


def root_for(candidate: Message | None, *, channel_id: uuid.UUID) -> uuid.UUID:
    """The root a new reply to `candidate` is filed under (single-level, R2).

    A reply names its root, so a reply to a reply files under the same root —
    including a tombstoned reply (assumed decision 21). A tombstoned *root* is
    still a root and still takes replies (R10). `None` or a row in another
    channel raises, so the two cannot be told apart.
    """
    if candidate is None or candidate.channel_id != channel_id:
        raise NoSuchThreadError
    return candidate.thread_root_id if candidate.thread_root_id is not None else candidate.id


async def resolve_root(
    session: AsyncSession, *, channel_id: uuid.UUID, candidate_id: uuid.UUID
) -> uuid.UUID:
    """Load the named row and apply `root_for`."""
    candidate = await messages.get(session, message_id=candidate_id)
    return root_for(candidate, channel_id=channel_id)


async def summaries_for(
    session: AsyncSession, *, root_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Summary]:
    """The summary of every root on a page, in **one** grouped query.

    Unaliased and grouped on `messages.thread_root_id`, which is what the tests
    that count and order statements look for. Counts `deleted_at IS NULL` only
    (R4): a deleted reply is not a reply anyone can count on.
    """
    ids = list(root_ids)
    if not ids:
        return {}

    query = (
        select(Message.thread_root_id, func.count(), func.max(Message.created_at))
        .where(Message.thread_root_id.in_(ids), Message.deleted_at.is_(None))
        .group_by(Message.thread_root_id)
    )
    rows = (await session.execute(query)).all()
    return {root_id: Summary(count, last) for root_id, count, last in rows}


async def summary_for(session: AsyncSession, *, root_id: uuid.UUID) -> Summary:
    """One root's summary — `summaries_for` over a single id."""
    return (await summaries_for(session, root_ids=[root_id])).get(root_id, NO_REPLIES)


async def replies_page(
    session: AsyncSession, *, root_id: uuid.UUID, page: PageRequest
) -> Page[Message]:
    """One page of a thread's replies, newest first, tombstones included.

    Keyset on `id DESC` like history, and served by the same partial index
    (`thread_root_id, id`). No `deleted_at` filter: a deleted reply is shown as a
    tombstone (R5), exactly as history shows them.
    """
    query = (
        # conventions: ok — replies keep their tombstones in a thread (R5), as history does.
        select(Message)
        .where(Message.thread_root_id == root_id)
        .order_by(Message.id.desc())
        .limit(page.fetch_limit)
    )
    if page.cursor:
        (last_id,) = page.cursor  # parsed and shape-checked by `messages.HISTORY_CURSOR`
        query = query.where(Message.id < last_id)

    rows = (await session.execute(query)).scalars().all()
    return build_page(rows, page, key=lambda m: (str(m.id),))
