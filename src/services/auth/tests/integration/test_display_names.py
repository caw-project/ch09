"""Names under concurrency, and at first sign-in (gh-3 Req 2 and 3; register D46).

The race tests work at the store, with two sessions, so the interleaving is
forced rather than hoped for: A writes a name and holds its transaction open, B
tries for the same name and is seen waiting on A, and only then does A commit.
What decides the outcome is the unique index — a SELECT-then-UPDATE check would
let B straight through, and `wait_until_blocked` would never see it wait.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text

from auth import identities
from auth.models import User, Workspace, WorkspaceMember
from shared import uuid7
from testkit import dexflow
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE


async def wait_until_blocked(sessions) -> None:
    """Return once some backend in this database waits on a lock; fail after 5 s.

    A poll, never a sleep: the moment B reaches the index is not ours to guess.
    Bounded, so a build with no index fails here instead of hanging the run.
    """
    deadline = time.monotonic() + 5
    async with sessions() as probe:
        while time.monotonic() < deadline:
            waiting = await probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            if waiting:
                return
            await asyncio.sleep(0.05)
    pytest.fail("B never blocked on the name index")


async def a_stored_user(sessions, email: str, name: str, *, deleted: bool = False) -> User:
    user = User(id=uuid7(), email=email, display_name=name)
    if deleted:
        user.deleted_at = datetime.now(UTC)
    async with sessions.begin() as session:
        session.add(user)
    return user


async def settle[T](task: asyncio.Task[T]) -> T:
    """Await a task that was waiting on a lock, without ever leaving it behind."""
    try:
        return await asyncio.wait_for(task, timeout=10)
    finally:
        if not task.done():
            task.cancel()


async def count_with_key(sessions, key: str) -> int:
    async with sessions() as session:
        return int(
            await session.scalar(
                text("SELECT count(*) FROM users WHERE display_name_key = :k"), {"k": key}
            )
        )


async def test_two_renames_to_one_name_one_wins(sessions) -> None:
    """Two accounts save "Sam" at once: one commits, the other is told it is taken.

    The index is the control. A pre-check cannot see A's uncommitted row, so a
    build built on one lets B through and the count below is two.
    """
    rename_user = identities.rename_user
    grace = await a_stored_user(sessions, "grace@x.dev", "grace")
    alan = await a_stored_user(sessions, "alan@x.dev", "alan")

    async with sessions() as a, sessions() as b:
        a_grace = await a.get(User, grace.id)
        b_alan = await b.get(User, alan.id)
        assert await rename_user(a, a_grace, "Sam") is True

        racer = asyncio.create_task(rename_user(b, b_alan, "Sam"))
        try:
            await wait_until_blocked(sessions)
            await a.commit()
            with pytest.raises(identities.NameTakenError):
                await settle(racer)
        finally:
            racer.cancel()
        await b.rollback()

    assert await count_with_key(sessions, "sam") == 1
    async with sessions() as session:
        names = {
            u.email: u.display_name for u in (await session.execute(select(User))).scalars().all()
        }
    assert names == {"grace@x.dev": "Sam", "alan@x.dev": "alan"}


async def test_a_rename_racing_a_first_sign_in(sessions) -> None:
    """A rename to "X" racing a first sign-in named "X": one holds it, the other falls to "X 2".

    The sign-in is never refused: it takes the next suffix, and its own workspace
    is named from the name it actually got.
    """
    rename_user = identities.rename_user
    grace = await a_stored_user(sessions, "grace@x.dev", "grace")

    async with sessions() as a, sessions() as b:
        a_grace = await a.get(User, grace.id)
        assert await rename_user(a, a_grace, "X") is True

        signing_in = asyncio.create_task(
            identities.provision_user(
                b, email="newcomer@x.dev", display_name="X", demo_workspace_name=None
            )
        )
        try:
            await wait_until_blocked(sessions)
            await a.commit()
            newcomer = await settle(signing_in)
        finally:
            signing_in.cancel()
        await b.commit()
        newcomer_id = newcomer.id

    async with sessions() as session:
        stored = await session.get(User, newcomer_id)
        workspace = (
            await session.execute(
                select(Workspace.name)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == newcomer_id)
            )
        ).scalar_one()
    assert stored.display_name == "X 2"
    assert workspace == "X 2's Workspace"
    assert await count_with_key(sessions, "x") == 1


async def test_two_first_sign_ins_with_one_name(sessions) -> None:
    """Two new accounts arrive as "Sam" together: "Sam" and "Sam 2", neither refused."""
    async with sessions() as a, sessions() as b:
        first = await identities.provision_user(
            a, email="first@x.dev", display_name="Sam", demo_workspace_name=None
        )
        await a.flush()

        second_task = asyncio.create_task(
            identities.provision_user(
                b, email="second@x.dev", display_name="Sam", demo_workspace_name=None
            )
        )
        try:
            await wait_until_blocked(sessions)
            await a.commit()
            second = await settle(second_task)
        finally:
            second_task.cancel()
        await b.commit()
        first_id, second_id = first.id, second.id

    async with sessions() as session:
        names = {
            user_id: (await session.get(User, user_id)).display_name
            for user_id in (first_id, second_id)
        }
    assert names == {first_id: "Sam", second_id: "Sam 2"}


# --------------------------------------------------------------------------
# Through the real callback
# --------------------------------------------------------------------------


async def sign_in(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def own_workspace_name(client: httpx.AsyncClient, tokens: dict[str, Any]) -> str:
    resp = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    return next(w["name"] for w in resp.json()["items"] if w["role"] == "owner")


async def test_a_taken_idp_name_gets_the_first_free_suffix(client: httpx.AsyncClient) -> None:
    """Grace is "alan" when Alan first signs in: he becomes "alan 2", workspace and all."""
    await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    taken = await client.patch(
        "/api/v1/users/me", headers=bearer(grace), json={"displayName": "alan"}
    )
    assert taken.status_code == 200

    alan = await sign_in(client, ALAN)

    profile = (await client.get("/api/v1/users/me", headers=bearer(alan))).json()
    assert profile["displayName"] == "alan 2"
    assert await own_workspace_name(client, alan) == "alan 2's Workspace"


async def test_a_deleted_accounts_name_is_skipped_at_sign_in(
    client: httpx.AsyncClient, sessions
) -> None:
    """A deleted account still holds its name, so a newcomer cannot be given it."""
    await a_stored_user(sessions, "gone@x.dev", "alan", deleted=True)

    alan = await sign_in(client, ALAN)

    profile = (await client.get("/api/v1/users/me", headers=bearer(alan))).json()
    assert profile["displayName"] == "alan 2"
