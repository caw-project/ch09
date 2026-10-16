"""A first sign-in whose name is taken falls to the next free suffix (gh-3, Req 3).

Mostly `identities.provision_user` on a real session, with rows planted
directly: the suffix rule reads the table, so the table is where its cases are.
Sign-in never refuses over a name and never overwrites an existing user's.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text

from auth import identities
from auth.models import User
from shared import uuid7
from testkit import dexflow
from testkit.dex import ADA, DEX_PASSWORD, GRACE

ZWSP = chr(0x200B)  # zero-width space


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def store(sessions, *names: str, deleted: bool = False) -> None:
    """Plant accounts that already hold these names."""
    async with sessions.begin() as session:
        for name in names:
            session.add(
                User(
                    id=uuid7(),
                    email=f"{uuid.uuid4().hex}@example.com",
                    display_name=name,
                    deleted_at=datetime.now(UTC) if deleted else None,
                )
            )


async def first_sign_in(sessions, name: str) -> User:
    async with sessions.begin() as session:
        return await identities.provision_user(
            session,
            email=f"{uuid.uuid4().hex}@example.com",
            display_name=name,
            demo_workspace_name=None,
        )


async def waiting_on_a_lock(sessions) -> bool:
    """Whether a statement in this database is blocked on a lock within five seconds."""
    for _ in range(100):
        async with sessions() as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            )
        if count:
            return True
        await asyncio.sleep(0.05)
    return False


async def test_the_first_free_suffix_is_taken(sessions) -> None:
    """With Sam, Sam 2 and Sam 4 held the answer is Sam 3 — a count would say Sam 4 or 5."""
    await store(sessions, "Sam", "Sam 2", "Sam 4")

    user = await first_sign_in(sessions, "Sam")

    assert user.display_name == "Sam 3"


async def test_a_free_name_is_kept_as_it_is(sessions) -> None:
    """The positive half: nothing is suffixed unless it has to be."""
    await store(sessions, "Sam")

    user = await first_sign_in(sessions, "Samantha")

    assert user.display_name == "Samantha"


async def test_suffixing_ignores_case(sessions) -> None:
    await store(sessions, "sam")

    user = await first_sign_in(sessions, "SAM")

    assert user.display_name == "SAM 2"


async def test_a_deleted_accounts_name_is_skipped(sessions) -> None:
    await store(sessions, "Sam", deleted=True)

    user = await first_sign_in(sessions, "Sam")

    assert user.display_name == "Sam 2"


async def test_the_own_workspace_is_named_from_the_result(sessions) -> None:
    await store(sessions, "Sam", "Sam 2")

    user = await first_sign_in(sessions, "Sam")

    async with sessions() as session:
        owned = [m.workspace.name for m in await identities.memberships(session, user.id)]
    assert user.display_name == "Sam 3"
    assert owned == ["Sam 3's Workspace"]


async def test_an_idp_name_is_cleaned(sessions) -> None:
    """A provider's padded, zero-width name is stored without them — and its workspace too."""
    user = await first_sign_in(sessions, " Sam" + ZWSP + " ")

    async with sessions() as session:
        owned = [m.workspace.name for m in await identities.memberships(session, user.id)]
    assert user.display_name == "Sam"
    assert owned == ["Sam's Workspace"]


async def test_two_first_sign_ins_with_one_name(sessions) -> None:
    """The second insert queues behind the first's uncommitted "Sam" and falls to "Sam 2".

    `demo_workspace_name=None` on both, so the only lock between them is the
    name's own — the demo workspace's advisory lock would block them at any build.
    """
    async with sessions() as first, sessions() as second:
        await identities.provision_user(
            first, email="one@example.com", display_name="Sam", demo_workspace_name=None
        )
        racing = asyncio.create_task(
            identities.provision_user(
                second, email="two@example.com", display_name="Sam", demo_workspace_name=None
            )
        )
        blocked = await waiting_on_a_lock(sessions)
        await first.commit()
        await asyncio.wait_for(racing, timeout=10)
        await second.commit()

    async with sessions() as session:
        stored = (
            await session.execute(
                text(
                    "SELECT display_name FROM users WHERE email IN ('one@example.com', 'two@example.com')"
                )
            )
        ).scalars()
        names = set(stored)
    assert blocked, "the second sign-in did not wait on the first one's uncommitted name"
    assert names == {"Sam", "Sam 2"}


async def test_a_first_sign_in_through_dex_takes_a_suffix(client: httpx.AsyncClient) -> None:
    """The whole path: Grace renames to "ada", then the real Ada arrives for the first time."""
    grace = await sign_in(client, GRACE)
    renamed = await client.patch(
        "/api/v1/users/me", headers=bearer(grace), json={"displayName": "ada"}
    )
    assert renamed.status_code == 200

    ada = await sign_in(client, ADA)

    me = await client.get("/api/v1/users/me", headers=bearer(ada))
    workspaces = await client.get("/api/v1/workspaces", headers=bearer(ada))
    assert me.json()["displayName"] == "ada 2"
    assert "ada 2's Workspace" in [w["name"] for w in workspaces.json()["items"]]


async def test_sign_in_never_overwrites_a_name(client: httpx.AsyncClient) -> None:
    """Green by design at red: the guard for the rewrite of `provision_user`.

    Paired with the suffix tests above — a build that re-applies the IdP's name
    on each sign-in passes those and fails this.
    """
    tokens = await sign_in(client)
    renamed = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada L"}
    )
    assert renamed.status_code == 200

    again = await sign_in(client)

    me = await client.get("/api/v1/users/me", headers=bearer(again))
    assert me.json()["displayName"] == "Ada L"
