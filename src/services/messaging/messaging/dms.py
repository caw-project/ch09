"""Direct messages (issue 5, register D8b).

A DM is a `kind='dm'` channel whose stored `name` is the **pair key**
`dm:{low}:{high}` — the two user ids sorted, so it is the same whichever of them
opens it. `ux_channels_dm_pair` makes the key unique per workspace, which is what
lets get-or-create be one `INSERT … ON CONFLICT DO NOTHING` rather than a
check-then-insert with a gap in it. `name` is otherwise unused for a DM: renames
are refused, so the key never moves, and the partner is a pure parse of it.

Both people get a `member` row and nobody an `admin` row, so nothing can rename,
archive or re-member a DM and the last-admin rule never fires.
"""

from __future__ import annotations

import uuid

from sqlalchemy import exists, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.models import DM, MEMBER, Channel, ChannelMember, Message
from shared import uuid7

_PREFIX = "dm:"


class SelfDmError(Exception):
    """A direct message needs two different people."""


class FixedChannelError(Exception):
    """A DM's name, existence and membership are fixed."""


def pair_name(a: uuid.UUID, b: uuid.UUID) -> str:
    """The pair key: `dm:{low}:{high}`, canonical lowercase, order-independent."""
    if a == b:
        raise SelfDmError(a)
    low, high = sorted((a, b))
    return f"{_PREFIX}{low}:{high}"


def pair_of(channel: Channel) -> tuple[uuid.UUID, uuid.UUID] | None:
    """The two members a DM was keyed on. Kind decides, never the name's shape."""
    if channel.kind != DM:
        return None
    low, high = channel.name.removeprefix(_PREFIX).split(":")
    return uuid.UUID(low), uuid.UUID(high)


def partner_of(channel: Channel, user_id: uuid.UUID) -> uuid.UUID | None:
    """The pair member who isn't `user_id`; `None` on any other kind."""
    pair = pair_of(channel)
    if pair is None:
        return None
    return pair[1] if pair[0] == user_id else pair[0]


def check_manageable(channel: Channel) -> None:
    """Raise for a DM: it can't be renamed, archived or have its members changed."""
    if channel.kind == DM:
        raise FixedChannelError(channel.id)


async def open_dm(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    other_id: uuid.UUID,
) -> uuid.UUID:
    """Get or create the one DM between two people, and return its id. No commit.

    `pair_name` runs first so a DM with yourself writes nothing. A racing insert
    blocks on the unique index until the winner commits and then does nothing;
    under READ COMMITTED the `SELECT` after it sees the winner's row. Members are
    inserted only by the transaction that created the channel, so a loser never
    adds a second pair of rows.
    """
    name = pair_name(user_id, other_id)
    created = (
        await session.execute(
            pg_insert(Channel)
            .values(id=uuid7(), workspace_id=workspace_id, name=name, kind=DM, created_by=user_id)
            # `index_where` must match the partial index or Postgres can't infer it.
            .on_conflict_do_nothing(
                index_elements=["workspace_id", "name"], index_where=text("kind = 'dm'")
            )
            .returning(Channel.id)
        )
    ).scalar_one_or_none()

    if created is not None:
        session.add_all(
            ChannelMember(channel_id=created, user_id=uid, role=MEMBER)
            for uid in (user_id, other_id)
        )
        await session.flush()
        return created

    return (
        await session.execute(
            select(Channel.id).where(
                Channel.workspace_id == workspace_id, Channel.kind == DM, Channel.name == name
            )
        )
    ).scalar_one()


async def opens_dm(
    session: AsyncSession, channel: Channel, *, thread_root_id: uuid.UUID | None
) -> bool:
    """Is the message about to be inserted the first top-level one in a DM?

    Called **before** the insert, in the send's transaction: under READ COMMITTED
    the first message to commit was checked before any other committed, so it
    always emits `channel_added`. Counting after commit could see two and emit
    none. Deleted messages count — a tombstone keeps a DM listed.
    """
    if channel.kind != DM or thread_root_id is not None:
        return False
    has_one = await session.execute(
        select(exists().where(Message.channel_id == channel.id, Message.thread_root_id.is_(None)))
    )
    return not has_one.scalar_one()
