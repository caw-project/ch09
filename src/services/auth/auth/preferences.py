"""Per-user preferences (register D28): validation, read and merge.

Stored as one `jsonb` object per user. The keys are validated here — an unknown
key or a bad value is refused by name — so the column never holds anything the
SPA does not know how to read. Reading never creates a row; writing upserts one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CLOCK_VALUES = ("12h", "24h")

_UNKNOWN = "Unknown preference."
_BAD_CLOCK = 'Must be "12h" or "24h".'


@dataclass(frozen=True)
class PreferencesPatch:
    """What a PATCH asks for: keys to set, keys to remove (sent as `null`)."""

    set: dict[str, str]
    remove: list[str]


class InvalidPreferencesError(ValueError):
    """A patch with a key or value we refuse; `errors` names every bad key."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__("Invalid preferences.")
        self.errors = errors


def parse_patch(raw: Mapping[str, object]) -> PreferencesPatch:
    """Validate a whole patch, or raise naming every key that is wrong."""
    to_set: dict[str, str] = {}
    remove: list[str] = []
    errors: dict[str, list[str]] = {}

    for key, value in raw.items():
        if key != "clock":
            errors[key] = [_UNKNOWN]
        elif value is None:
            remove.append(key)
        elif isinstance(value, str) and value in CLOCK_VALUES:
            to_set[key] = value
        else:
            errors[key] = [_BAD_CLOCK]

    if errors:
        raise InvalidPreferencesError(errors)
    return PreferencesPatch(to_set, remove)


async def read(session: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """The user's preferences; `{}` when they have never saved one. Creates nothing."""
    result = await session.execute(
        text("SELECT prefs FROM user_preferences WHERE user_id = :user_id"), {"user_id": user_id}
    )
    row = result.first()
    return {} if row is None else dict(row.prefs)


async def merge(
    session: AsyncSession, user_id: uuid.UUID, patch: PreferencesPatch
) -> dict[str, str]:
    """Apply a patch in one statement and return the merged preferences. No commit.

    The merge is the database's, not a read-modify-write in Python: two tabs
    saving different keys cannot lose each other, because the second upsert
    waits on the first's row and then merges into what it committed. On one
    key the last commit wins. A key both set and removed is removed.
    """
    result = await session.execute(
        text(
            "INSERT INTO user_preferences AS p (user_id, prefs, version, updated_at) "
            "VALUES (:user_id, CAST(:prefs AS jsonb) - CAST(:remove AS text[]), 1, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "prefs = (p.prefs || EXCLUDED.prefs) - CAST(:remove AS text[]), "
            "version = p.version + 1, updated_at = now() "
            "RETURNING prefs"
        ),
        {"user_id": user_id, "prefs": json.dumps(patch.set), "remove": patch.remove},
    )
    merged: dict[str, Any] = result.scalar_one()
    return dict(merged)
