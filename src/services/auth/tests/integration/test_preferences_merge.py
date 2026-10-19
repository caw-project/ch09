"""The preferences merge, and two tabs writing at once (issue gh-3, Decision 25).

`merge` is called directly, with keys the route would refuse, because `clock` is
the only key there is and the rule being proven is about *two* keys. It is its own
file because it imports `auth.preferences` at the top: in the route tests that
import would stop them running before the module exists.

A race is held the way `test_display_names.py` holds one: a session writes and does
not commit, a second write starts, and the test waits for Postgres to report a
backend blocked on a lock before settling the first.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.models import User
from auth.preferences import PreferencesPatch, merge
from shared import uuid7


async def wait_until_blocked(engine: AsyncEngine) -> None:
    for _ in range(100):
        async with engine.connect() as connection:
            waiting = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the second write never waited on the first")


async def a_user(sessions) -> uuid.UUID:
    user = User(id=uuid7(), email="ada@example.com", display_name="Ada")
    async with sessions.begin() as session:
        session.add(user)
    return user.id


async def stored(sessions, user_id: uuid.UUID) -> dict[str, Any] | None:
    async with sessions() as session:
        row = (
            await session.execute(
                text("SELECT prefs FROM user_preferences WHERE user_id = :u"), {"u": user_id}
            )
        ).first()
    return None if row is None else row.prefs


async def commit_one(sessions, user_id: uuid.UUID, patch: PreferencesPatch) -> dict[str, str]:
    async with sessions() as session:
        merged = await merge(session, user_id, patch)
        await session.commit()
    return merged


async def concurrent(
    sessions,
    engine: AsyncEngine,
    user_id: uuid.UUID,
    *,
    first: PreferencesPatch,
    second: PreferencesPatch,
    first_commits: bool,
) -> dict[str, str]:
    """Hold `first` uncommitted, start `second`, wait for it to block, settle `first`."""
    async with sessions() as holder:
        await merge(holder, user_id, first)

        task = asyncio.ensure_future(commit_one(sessions, user_id, second))
        try:
            await wait_until_blocked(engine)
        except BaseException:
            await holder.rollback()
            await asyncio.gather(task, return_exceptions=True)
            raise

        if first_commits:
            await holder.commit()
        else:
            await holder.rollback()
        return await task


@pytest.mark.parametrize("commits", [True, False], ids=["holder-commits", "holder-rolls-back"])
async def test_merges_on_different_keys_both_survive(sessions, engine, commits: bool) -> None:
    user_id = await a_user(sessions)

    returned = await concurrent(
        sessions,
        engine,
        user_id,
        first=PreferencesPatch({"a": "1"}, []),
        second=PreferencesPatch({"b": "2"}, []),
        first_commits=commits,
    )

    expected = {"a": "1", "b": "2"} if commits else {"b": "2"}
    assert returned == expected
    assert await stored(sessions, user_id) == expected


async def test_on_one_key_the_later_commit_wins(sessions, engine) -> None:
    user_id = await a_user(sessions)

    returned = await concurrent(
        sessions,
        engine,
        user_id,
        first=PreferencesPatch({"a": "1"}, []),
        second=PreferencesPatch({"a": "2"}, []),
        first_commits=True,
    )

    assert returned == {"a": "2"}
    assert await stored(sessions, user_id) == {"a": "2"}


async def test_a_removal_and_a_set_in_one_patch(sessions) -> None:
    user_id = await a_user(sessions)
    await commit_one(sessions, user_id, PreferencesPatch({"a": "1", "b": "2"}, []))

    merged = await commit_one(sessions, user_id, PreferencesPatch({"c": "3"}, ["a"]))
    assert merged == {"b": "2", "c": "3"}

    # A key both set and removed is removed: the removal applies after the merge.
    both = await commit_one(sessions, user_id, PreferencesPatch({"b": "9", "d": "4"}, ["b"]))
    assert both == {"c": "3", "d": "4"}
    assert await stored(sessions, user_id) == {"c": "3", "d": "4"}
