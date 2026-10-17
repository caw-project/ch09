"""Per-user preferences (gh-3; register D28).

One `user_preferences` row per person, global to them rather than to a workspace.
The server owns the set of keys and the values each accepts, so a client cannot
store an arbitrary blob. `parse_patch` is the only place a body is validated; the
store takes what it returns.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import UserPreferences

KNOWN: Mapping[str, frozenset[str]] = {"clock": frozenset({"12h", "24h"})}


@dataclass(frozen=True)
class PreferencesPatch:
    """What a request changes: keys to set, and keys to put back to automatic."""

    set: dict[str, str]
    remove: frozenset[str]


class InvalidPreferencesError(ValueError):
    """A body with an unknown key or a bad value; `errors` is keyed by preference."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__("invalid preferences")
        self.errors = errors


def _bad_value(allowed: frozenset[str]) -> str:
    options = ", ".join(f'"{value}"' for value in sorted(allowed))
    head, last = options.rsplit(", ", 1) if ", " in options else ("", options)
    return f"Must be {head}, {last} or null." if head else f"Must be {last} or null."


def parse_patch(body: Mapping[str, object]) -> PreferencesPatch:
    """Validate a PATCH body. Every error is reported at once; nothing is half-applied."""
    to_set: dict[str, str] = {}
    to_remove: set[str] = set()
    errors: dict[str, list[str]] = {}

    for key, value in body.items():
        allowed = KNOWN.get(key)
        if allowed is None:
            errors[key] = ["Unknown preference."]
        elif value is None:
            to_remove.add(key)
        elif isinstance(value, str) and value in allowed:
            to_set[key] = value
        else:
            errors[key] = [_bad_value(allowed)]

    if errors:
        raise InvalidPreferencesError(errors)
    return PreferencesPatch(set=to_set, remove=frozenset(to_remove))


async def read(session: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """The stored keys, or `{}` for a user who has chosen nothing."""
    prefs = await session.scalar(
        select(UserPreferences.prefs).where(UserPreferences.user_id == user_id)
    )
    return dict(prefs or {})


async def apply_patch(
    session: AsyncSession, user_id: uuid.UUID, patch: PreferencesPatch
) -> dict[str, str]:
    """Merge `patch` into the user's row and return the keys now stored.

    One `INSERT … ON CONFLICT DO UPDATE`, so two tabs setting different keys both
    land (a read-modify-write would let the second overwrite the first) and the
    same key is last-write-wins. The merge exists only in SQL. An empty patch
    writes nothing.
    """
    if not patch.set and not patch.remove:
        return await read(session, user_id)

    merged = UserPreferences.prefs.op("||")(cast(patch.set, JSONB)).op("-")(
        cast(sorted(patch.remove), ARRAY(Text))
    )
    insert = pg_insert(UserPreferences).values(
        user_id=user_id,
        prefs=cast(patch.set, JSONB),
        version=1,
    )
    upsert = insert.on_conflict_do_update(
        index_elements=[UserPreferences.user_id],
        set_={
            "prefs": merged,
            "version": UserPreferences.version + 1,
            "updated_at": func.now(),
        },
    ).returning(UserPreferences.prefs)
    result = await session.execute(upsert)
    return dict(result.scalar_one())
