"""Renaming yourself, and the one rule that no two accounts share a name (gh-3, Req 1-2).

Uniqueness is global, case-insensitive, trimmed, and counts deleted accounts
(register D46), so these run through the real app against a real Postgres: the
only thing that can arbitrate two renames to one name is the database's index,
and the races here are forced to meet inside it rather than hoped for.

`ada`, `grace` and `alan` are the display names Dex's three accounts arrive
with; the tests rename them to find out who may take what.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy import text

from auth import identities
from testkit import dexflow
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE

TAKEN = "That name is already taken."
INVISIBLE = "A display name cannot contain control or invisible characters."
ZWSP = chr(0x200B)  # zero-width space


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def rename(client: httpx.AsyncClient, tokens: dict[str, Any], name: str) -> httpx.Response:
    return await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": name}
    )


async def name_of(client: httpx.AsyncClient, tokens: dict[str, Any]) -> str:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()["displayName"]


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def waiting_on_a_lock(sessions) -> bool:
    """Whether some statement in this database is blocked on a lock, within five seconds.

    A fresh session per poll: `pg_stat_activity` is read as a snapshot that is
    fixed for the rest of a transaction, so one long-lived session would see
    the first answer for ever.
    """
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


# --------------------------------------------------------------------------
# What a name may be (Req 1)
# --------------------------------------------------------------------------


async def test_a_name_is_stored_trimmed(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "  Ada L  ")

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Ada L"
    assert await name_of(client, tokens) == "Ada L"


async def test_a_blank_name_is_400_and_nothing_changes(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "   ")

    assert resp.status_code == 400
    assert resp.json()["errors"]["displayName"] == ["A display name is required."]
    assert await name_of(client, tokens) == "ada"


async def test_length_is_counted_after_trimming(client: httpx.AsyncClient) -> None:
    """Padding must not count toward 100, and a 101st real character must."""
    tokens = await sign_in(client)

    padded = await rename(client, tokens, "  " + "a" * 100 + "  ")
    too_long = await rename(client, tokens, "b" * 101)

    assert padded.status_code == 200
    assert too_long.status_code == 400
    assert too_long.json()["errors"]["displayName"] == ["A display name is at most 100 characters."]
    assert await name_of(client, tokens) == "a" * 100


async def test_an_invisible_character_is_400(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "Ada" + ZWSP)

    assert resp.status_code == 400
    assert resp.json()["errors"]["displayName"] == [INVISIBLE]
    assert await name_of(client, tokens) == "ada"


# --------------------------------------------------------------------------
# Unique everywhere (Req 2)
# --------------------------------------------------------------------------


async def test_a_taken_name_is_409_and_names_nobody(client: httpx.AsyncClient) -> None:
    """The 409 may say a name exists; it must not say whose, or where."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await client.get("/api/v1/users/me", headers=bearer(grace))).json()["id"]

    resp = await rename(client, ada, "grace")

    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["detail"] == TAKEN
    assert body["errors"] == {"displayName": [TAKEN]}
    assert "@" not in resp.text
    assert graces_id not in resp.text
    assert "Workspace" not in resp.text
    assert await name_of(client, ada) == "ada"


async def test_your_own_capitals_are_free_and_nobody_elses_are(client: httpx.AsyncClient) -> None:
    """The index must not collide a row with itself, yet must collide it with another."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)

    own = await rename(client, ada, "ADA")
    other = await rename(client, grace, "ada")

    assert own.status_code == 200
    assert own.json()["displayName"] == "ADA"
    assert other.status_code == 409
    assert other.json()["detail"] == TAKEN
    assert await name_of(client, grace) == "grace"


async def test_case_folding_covers_accented_capitals(client: httpx.AsyncClient) -> None:
    """`lower()` under the image's collation maps É to é (decision 14) — proven on the real image."""
    grace = await sign_in(client, GRACE)
    alan = await sign_in(client, ALAN)

    first = await rename(client, grace, "Émile")
    second = await rename(client, alan, "émile")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == TAKEN


async def test_saving_the_name_you_have_changes_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    """A no-op save is a 200 that writes nothing; a real rename still bumps the version."""
    tokens = await sign_in(client)

    async def row() -> tuple[int, Any]:
        async with sessions() as session:
            found = await session.execute(
                text("SELECT version, updated_at FROM users WHERE email = :e"), {"e": ADA}
            )
            return tuple(found.one())  # type: ignore[return-value]

    before = await row()

    same = await rename(client, tokens, "ada")
    padded = await rename(client, tokens, "  ada ")

    assert same.status_code == 200
    assert same.json()["displayName"] == "ada"
    assert padded.status_code == 200
    assert await row() == before

    changed = await rename(client, tokens, "ada b")
    assert changed.status_code == 200
    version, updated_at = await row()
    assert version == before[0] + 1
    assert updated_at > before[1]


async def test_the_same_name_with_an_avatar_still_writes_the_avatar(
    client: httpx.AsyncClient,
) -> None:
    """The no-op rule needs "nothing else sent": the name alone is not enough to skip the write."""
    tokens = await sign_in(client)
    asset = "0199a000-0000-7000-8000-000000000001"

    resp = await client.patch(
        "/api/v1/users/me",
        headers=bearer(tokens),
        json={"displayName": "ada", "avatarAsset": asset},
    )

    assert resp.status_code == 200
    assert resp.json()["avatarAsset"] == asset


async def test_a_deleted_accounts_name_stays_taken(client: httpx.AsyncClient, sessions) -> None:
    ada = await sign_in(client, ADA)
    await sign_in(client, GRACE)
    await delete_account(sessions, GRACE)

    taken = await rename(client, ada, "grace")
    free = await rename(client, ada, "grace hopper")

    assert taken.status_code == 409
    assert taken.json()["detail"] == TAKEN
    assert free.status_code == 200


# --------------------------------------------------------------------------
# The races (Req 2, 3)
# --------------------------------------------------------------------------


async def test_two_renames_to_one_name_at_once(client: httpx.AsyncClient, sessions) -> None:
    """Exactly one of two simultaneous saves wins, and the database never holds both."""
    grace = await sign_in(client, GRACE)
    alan = await sign_in(client, ALAN)

    results = await asyncio.gather(rename(client, grace, "Sam"), rename(client, alan, "Sam"))

    assert sorted(r.status_code for r in results) == [200, 409]
    async with sessions() as session:
        holders = await session.scalar(
            text("SELECT count(*) FROM users WHERE lower(display_name) = 'sam'")
        )
    assert holders == 1


async def test_a_rename_waits_on_a_sign_up_holding_the_name(
    client: httpx.AsyncClient, sessions
) -> None:
    """A first sign-in that has inserted "Sam" but not committed owns it: the rename must queue."""
    ada = await sign_in(client, ADA)

    async with sessions() as signing_up:
        await identities.provision_user(
            signing_up, email="sam@example.com", display_name="Sam", demo_workspace_name=None
        )
        renaming = asyncio.create_task(rename(client, ada, "Sam"))
        blocked = await waiting_on_a_lock(sessions)
        await signing_up.commit()
        resp = await asyncio.wait_for(renaming, timeout=10)

    assert blocked, "the rename went ahead without waiting on the uncommitted holder of the name"
    assert resp.status_code == 409
    assert resp.json()["detail"] == TAKEN
    assert await name_of(client, ada) == "ada"


async def test_a_sign_up_after_a_rename_takes_a_suffix(client: httpx.AsyncClient, sessions) -> None:
    ada = await sign_in(client, ADA)
    assert (await rename(client, ada, "Sam")).status_code == 200

    async with sessions.begin() as session:
        user = await identities.provision_user(
            session, email="sam@example.com", display_name="Sam", demo_workspace_name=None
        )

    assert user.display_name == "Sam 2"
