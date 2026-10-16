"""Per-user preferences (register D28): which keys exist, and how a patch lands.

One row per user holds a JSON object. A write is one statement —
`INSERT … ON CONFLICT DO UPDATE SET prefs = (prefs || new) - removed` — so two
writers of different keys both land and neither reads, modifies and overwrites
the other's. `merge` never commits: the caller owns the transaction, which is
also what lets a test hold one open.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import ConfigDict
from sqlalchemy import ARRAY, Text, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import UserPreferences
from auth.schemas import CamelRequest


class PreferencesPatch(CamelRequest):
    """A preferences edit. Absent leaves a key alone; `null` removes it.

    Unknown keys are refused by name, so a typo cannot silently store nothing
    (and nothing unvalidated can be stored).
    """

    model_config = ConfigDict(extra="forbid")

    clock: Literal["12h", "24h"] | None = None


def split(patch: PreferencesPatch) -> tuple[dict[str, str], list[str]]:
    """The keys to set and the keys to remove, from what the request carried."""
    to_set: dict[str, str] = {}
    to_remove: list[str] = []
    for key in patch.model_fields_set:
        value = getattr(patch, key)
        if value is None:
            to_remove.append(key)
        else:
            to_set[key] = value
    return to_set, to_remove


async def read(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """The user's preferences; `{}` with no row, and no row is created."""
    result = await session.execute(
        select(UserPreferences.prefs).where(UserPreferences.user_id == user_id)
    )
    return dict(result.scalar_one_or_none() or {})


async def merge(
    session: AsyncSession, user_id: uuid.UUID, to_set: dict[str, str], to_remove: list[str]
) -> dict[str, Any]:
    """Apply a patch in one statement and return the merged object."""
    statement = insert(UserPreferences).values(user_id=user_id, prefs=to_set)
    merged = (UserPreferences.prefs.op("||", return_type=JSONB)(statement.excluded.prefs)).op(
        "-", return_type=JSONB
    )(cast(to_remove, ARRAY(Text)))
    statement = statement.on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "prefs": merged,
            "version": UserPreferences.version + 1,
            "updated_at": func.now(),
        },
    ).returning(UserPreferences.prefs)

    result = await session.execute(statement)
    return dict(result.scalar_one())
