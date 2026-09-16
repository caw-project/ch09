"""Reactions (doc 02 §3.1.5, §4).

Same shape as `messages.py`: plain async functions taking an `AsyncSession`
first, pure rules above them, no FastAPI imports — so the same rules would serve
a socket handler if one is ever added.

**The allowlist is the whole validation rule.** Shortcodes rather than emoji
characters, so there is no unicode normalisation, no skin-tone or ZWJ question,
and nothing variable-width in an indexed column — the client decides what glyph
to draw. Widening the tuple later is one line; narrowing it strands rows, which
is why `summarise` ignores a shortcode it no longer knows rather than raising.

**Order comes from the allowlist, not from the query.** Postgres groups in
whatever order suits it, and chips that reordered themselves as counts changed
would move under the pointer between a person deciding to click and clicking.

This module returns its own `Summary` dataclass rather than the API model: no
domain module in this service imports `schemas`, and `routers/messages.py` is
where DTOs get built.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.models import Message, Reaction

__all__ = [
    "REACTION_EMOJI",
    "Summary",
    "UnknownEmojiError",
    "add",
    "clear_for_message",
    "may_react",
    "remove",
    "summaries_for",
    "summarise",
    "validate",
]

#: What a person may react with. Server-owned and deliberately small: six things
#: a reader recognises at a glance, and no picker that needs a search box.
REACTION_EMOJI: tuple[str, ...] = ("thumbsup", "heart", "tada", "smile", "eyes", "check")

#: Display position, so ordering is a lookup rather than a scan.
_ORDER: dict[str, int] = {emoji: index for index, emoji in enumerate(REACTION_EMOJI)}


class UnknownEmojiError(Exception):
    """Not one of `REACTION_EMOJI`."""


@dataclass(frozen=True)
class Summary:
    """One emoji on one message: how many, and whether the caller is one of them."""

    emoji: str
    count: int
    reacted: bool


def validate(emoji: str) -> str:
    """Return the shortcode unchanged, or raise.

    No trimming and no case folding. A client that sends `"THUMBSUP "` has a bug,
    and quietly accepting it would mean the column holds two spellings of one
    reaction the first time the normalisation is skipped.
    """
    if emoji not in _ORDER:
        raise UnknownEmojiError(emoji)
    return emoji


def may_react(message: Message) -> bool:
    """Whether this message can take a reaction. A tombstone cannot.

    A pure function over the loaded row (register D32), so the rule is unit
    tested with no session; the router maps `False` to a 409.
    """
    return message.deleted_at is None


def summarise(
    rows: Iterable[tuple[uuid.UUID, str, int, bool]],
) -> dict[uuid.UUID, list[Summary]]:
    """Grouped `(message_id, emoji, count, reacted)` rows into per-message summaries.

    Pure, so the ordering rule and the retired-shortcode rule are unit tested
    without a database.
    """
    grouped: dict[uuid.UUID, list[Summary]] = {}
    for message_id, emoji, count, reacted in rows:
        if emoji not in _ORDER:
            continue
        grouped.setdefault(message_id, []).append(
            Summary(emoji=emoji, count=count, reacted=bool(reacted))
        )

    for summaries in grouped.values():
        summaries.sort(key=lambda summary: _ORDER[summary.emoji])
    return grouped


async def summaries_for(
    session: AsyncSession, *, message_ids: Iterable[uuid.UUID], user_id: uuid.UUID
) -> dict[uuid.UUID, list[Summary]]:
    """Every reaction on a page of messages, in **one** grouped query.

    One query for the page and not one per message: that is the entire reason
    reactions are aggregated onto the message DTO rather than served from an
    endpoint of their own, and `test_a_page_of_history_costs_one_reaction_query`
    is what holds it.

    `bool_or` answers "is the caller among them" in the same pass as the count,
    so `reacted` costs no second round trip — and it is computed per request
    from the caller's own id, never stored and never broadcast.
    """
    ids = list(message_ids)
    if not ids:
        return {}

    query = (
        select(
            Reaction.message_id,
            Reaction.emoji,
            func.count().label("count"),
            func.bool_or(Reaction.user_id == user_id).label("reacted"),
        )
        .where(Reaction.message_id.in_(ids))
        .group_by(Reaction.message_id, Reaction.emoji)
    )
    rows = (await session.execute(query)).all()
    return summarise((r.message_id, r.emoji, r.count, r.reacted) for r in rows)


async def add(
    session: AsyncSession, *, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
) -> None:
    """React, or do nothing if this person already reacted that way.

    `ON CONFLICT DO NOTHING` rather than a read-then-write: two tabs clicking at
    once would both see "not reacted" and one would fail on the key. The
    conflict is the normal case, not an error.
    """
    await session.execute(
        insert(Reaction)
        .values(message_id=message_id, user_id=user_id, emoji=emoji)
        .on_conflict_do_nothing()
    )


async def remove(
    session: AsyncSession, *, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str
) -> None:
    """Take a reaction back. Removing one that is not there is not an error."""
    await session.execute(
        delete(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
    )


async def clear_for_message(session: AsyncSession, *, message_id: uuid.UUID) -> None:
    """Drop every reaction on a message, when it is deleted.

    The foreign key cascades on a *row* delete, and a delete here is a
    tombstone — the row stays. So this is explicit rather than implied.
    """
    await session.execute(delete(Reaction).where(Reaction.message_id == message_id))
