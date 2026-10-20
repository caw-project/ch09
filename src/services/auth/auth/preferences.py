"""Per-user preferences (register D28; issue gh-3, Req 6-7).

A user's settings live in Auth, one JSON map per user, and the server decides
which keys exist: `KEYS` maps each to a validator, so a client cannot store
anything the service does not understand. `clock` is the first key.

`parse_patch` is pure. `read` and `apply` are the only SQL; `apply` is one atomic
upsert, so two tabs writing different keys at the same moment both keep theirs.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UNKNOWN = "Unknown preference."
BAD_CLOCK = 'Must be "12h", "24h" or null.'

CLOCK_VALUES = ("12h", "24h")


def _check_clock(value: object) -> str | None:
    # `isinstance` first: `True` and `1` must not be compared into a match.
    if isinstance(value, str) and value in CLOCK_VALUES:
        return None
    return BAD_CLOCK


# Read at request time, never copied: a key is added here and nowhere else.
KEYS: dict[str, Callable[[object], str | None]] = {"clock": _check_clock}


@dataclass(frozen=True)
class Patch:
    """What to merge in (`set`) and which keys to drop (`remove`)."""

    set: dict[str, object]
    remove: frozenset[str]


class InvalidPreferencesError(ValueError):
    """The patch had unknown keys or bad values; `errors` lists every one."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__("invalid preferences")
        self.errors = errors


def parse_patch(body: Mapping[str, object]) -> Patch:
    """Validate a PATCH body: `null` removes a key, anything else must pass its validator."""
    errors: dict[str, list[str]] = {}
    to_set: dict[str, object] = {}
    remove: set[str] = set()

    for key, value in body.items():
        validator = KEYS.get(key)
        if validator is None:
            errors[key] = [UNKNOWN]
        elif value is None:
            remove.add(key)
        elif (problem := validator(value)) is not None:
            errors[key] = [problem]
        else:
            to_set[key] = value

    if errors:
        raise InvalidPreferencesError(errors)
    return Patch(set=to_set, remove=frozenset(remove))


async def read(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """The stored map, `{}` when the user has none. Never inserts."""
    result = await session.execute(
        text("SELECT prefs FROM user_preferences WHERE user_id = :uid"), {"uid": user_id}
    )
    prefs = result.scalar_one_or_none()
    return dict(prefs) if prefs else {}


async def apply(session: AsyncSession, user_id: uuid.UUID, patch: Patch) -> dict[str, Any]:
    """Merge `patch` into the user's map in one statement and return the result.

    The `ON CONFLICT` update takes the row lock and merges into the latest
    committed value, so concurrent patches of different keys keep both.
    """
    result = await session.execute(
        text(
            """
            INSERT INTO user_preferences (user_id, prefs, version, updated_at)
            VALUES (:uid, CAST(:set AS jsonb) - CAST(:remove AS text[]), 1, now())
            ON CONFLICT (user_id) DO UPDATE
               SET prefs = (user_preferences.prefs || CAST(:set AS jsonb))
                           - CAST(:remove AS text[]),
                   version = user_preferences.version + 1,
                   updated_at = now()
            RETURNING prefs
            """
        ),
        {"uid": user_id, "set": json.dumps(patch.set), "remove": sorted(patch.remove)},
    )
    merged = dict(result.scalar_one())
    await session.commit()
    return merged
