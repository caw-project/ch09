"""Display names: renaming yourself, global uniqueness and first sign-in (issue gh-3).

Everything here goes through REST or `link_identity` against a real Postgres,
because the rule worth proving is the one the database enforces: no two accounts
hold the same name, whoever asks first and however the requests interleave.

**Holding a race.** A test that says "at the same instant" would pass by luck.
Instead one session writes a name and does *not* commit, a request for the same
name is started, and the test waits until Postgres reports a backend blocked on
a lock — proof the request really is waiting on the held name — and only then
settles the holder. Each race is run in both orders: the holder commits (the
request loses) and the holder rolls back (the request wins).

Characters that are awkward to read are built with `chr()`: the lint hook
rewrites a `\\u` escape into the raw character.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.identities import link_identity, memberships
from auth.models import User
from shared import uuid7
from testkit import dexflow
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE
from testkit.dexflow import renewed, session_cookie

TAKEN = "That name is already taken."
REQUIRED = "A display name is required."
TOO_LONG = "A display name is at most 100 characters."
INVISIBLE = "A display name cannot contain invisible or control characters."

NBSP = chr(0xA0)
ZWSP = chr(0x200B)
HANGUL_FILLER = chr(0x3164)
CGJ = chr(0x034F)
BELL = chr(0x07)
E_ACUTE = chr(0xE9)
COMBINING_ACUTE = chr(0x301)
JOSE = "Jos" + E_ACUTE
JOSE_DECOMPOSED = "Jose" + COMBINING_ACUTE


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def me(client: httpx.AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()


async def rename(
    client: httpx.AsyncClient, tokens: dict[str, Any], name: str, **extra: Any
) -> httpx.Response:
    return await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": name, **extra}
    )


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def stored(sessions, email: str) -> Any:
    async with sessions() as session:
        result = await session.execute(
            text(
                "SELECT display_name, version, updated_at, avatar_asset FROM users WHERE email = :e"
            ),
            {"e": email},
        )
        return result.one()


async def wait_until_blocked(engine: AsyncEngine) -> None:
    """Poll until some backend waits on a lock; fail after five seconds."""
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
    raise AssertionError("the request never waited on the held name")


async def race(
    sessions,
    engine: AsyncEngine,
    *,
    holder_email: str,
    held_name: str,
    commit: bool,
    request: Callable[[], Awaitable[Any]],
) -> Any:
    """Hold `held_name` for `holder_email`, start `request`, then settle the holder."""
    async with sessions() as holder:
        user = (await holder.execute(select(User).where(User.email == holder_email))).scalar_one()
        user.display_name = held_name
        await holder.flush()

        task = asyncio.ensure_future(request())
        try:
            await wait_until_blocked(engine)
        except BaseException:
            await holder.rollback()
            await asyncio.gather(task, return_exceptions=True)
            raise

        if commit:
            await holder.commit()
        else:
            await holder.rollback()
        return await task


# --------------------------------------------------------------------------
# What a rename stores, and what it refuses (Req 1)
# --------------------------------------------------------------------------


async def test_a_rename_is_stored_trimmed_and_composed(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "  " + JOSE_DECOMPOSED + "  ")

    assert resp.status_code == 200, resp.text
    assert resp.json()["displayName"] == JOSE
    assert (await me(client, tokens))["displayName"] == JOSE
    assert (await stored(sessions, ADA)).display_name == JOSE


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param("Grace" + ZWSP, INVISIBLE, id="zero-width-space"),
        pytest.param("Grace" + HANGUL_FILLER, INVISIBLE, id="hangul-filler"),
        pytest.param("Gr" + CGJ + "ace", INVISIBLE, id="grapheme-joiner"),
        pytest.param("Grace" + BELL, INVISIBLE, id="bell"),
        pytest.param(NBSP, REQUIRED, id="no-break-space"),
    ],
)
async def test_each_refused_example_is_400_on_the_field(
    client: httpx.AsyncClient, raw: str, message: str
) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, raw)

    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"]["displayName"] == [message]
    assert (await me(client, tokens))["displayName"] == "ada"


async def test_a_101_character_name_is_400_and_100_is_not(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    too_long = await rename(client, tokens, "x" * 101)
    assert too_long.status_code == 400, too_long.text
    assert too_long.json()["errors"]["displayName"] == [TOO_LONG]
    assert (await me(client, tokens))["displayName"] == "ada"

    # 102 raw characters, 100 once trimmed: the length is counted on the stored form.
    padded = await rename(client, tokens, " " + "x" * 100 + " ")
    assert padded.status_code == 200, padded.text
    assert padded.json()["displayName"] == "x" * 100


# --------------------------------------------------------------------------
# Unique everywhere (Req 2)
# --------------------------------------------------------------------------


async def test_a_taken_name_is_409_and_names_nobody(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_ids = [(await me(client, grace))["id"]]
    listed = await client.get("/api/v1/workspaces", headers=bearer(grace))
    graces_ids += [w["id"] for w in listed.json()["items"]]

    resp = await rename(client, ada, "GRACE")

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["detail"] == TAKEN
    assert body["errors"] == {"displayName": [TAKEN]}
    assert "grace" not in resp.text.lower()
    for leaked in graces_ids:
        assert leaked not in resp.text
    assert (await me(client, ada))["displayName"] == "ada"


async def test_names_that_collide_only_once_composed_are_taken(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    assert (await rename(client, grace, JOSE)).status_code == 200

    resp = await rename(client, ada, "jose" + COMBINING_ACUTE)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == TAKEN
    assert (await me(client, ada))["displayName"] == "ada"


async def test_changing_only_your_own_capitals_is_allowed(client: httpx.AsyncClient) -> None:
    """Not a collision with yourself. (Green by design at red; the unique index makes it matter.)"""
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "ADA")

    assert resp.status_code == 200, resp.text
    assert resp.json()["displayName"] == "ADA"
    assert (await me(client, tokens))["displayName"] == "ADA"


async def test_saving_the_name_you_have_writes_nothing(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)
    before = await stored(sessions, ADA)

    same = await rename(client, tokens, "ada")

    assert same.status_code == 200, same.text
    assert same.json()["displayName"] == "ada"
    unchanged = await stored(sessions, ADA)
    assert (unchanged.version, unchanged.updated_at) == (before.version, before.updated_at)

    # The positive: a capitals-only change is a real write.
    capitals = await rename(client, tokens, "Ada")
    assert capitals.status_code == 200, capitals.text
    after = await stored(sessions, ADA)
    assert after.display_name == "Ada"
    assert after.version == before.version + 1
    assert after.updated_at > before.updated_at


async def test_the_same_name_with_a_new_avatar_saves_the_avatar(
    client: httpx.AsyncClient, sessions
) -> None:
    """Green by design at red: guards an early return that would drop the avatar."""
    tokens = await sign_in(client)
    before = await stored(sessions, ADA)
    asset = str(uuid7())

    resp = await rename(client, tokens, "ada", avatarAsset=asset)

    assert resp.status_code == 200, resp.text
    assert resp.json()["avatarAsset"] == asset
    after = await stored(sessions, ADA)
    assert str(after.avatar_asset) == asset
    assert after.version == before.version + 1


async def test_a_deleted_accounts_name_stays_taken(client: httpx.AsyncClient, sessions) -> None:
    ada = await sign_in(client, ADA)
    await sign_in(client, GRACE)
    await delete_account(sessions, GRACE)

    taken = await rename(client, ada, "grace")
    assert taken.status_code == 409, taken.text
    assert taken.json()["detail"] == TAKEN

    free = await rename(client, ada, "grace2")
    assert free.status_code == 200, free.text


# --------------------------------------------------------------------------
# Races on a name (Where the rules meet 1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("commit", [True, False], ids=["holder-commits", "holder-rolls-back"])
async def test_a_rename_racing_a_held_rename(
    client: httpx.AsyncClient, sessions, engine, commit: bool
) -> None:
    ada = await sign_in(client, ADA)
    await sign_in(client, ALAN)

    resp = await race(
        sessions,
        engine,
        holder_email=ALAN,
        held_name="Sam",
        commit=commit,
        request=lambda: rename(client, ada, "sam"),
    )

    if commit:
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == TAKEN
        assert (await stored(sessions, ADA)).display_name == "ada"
        assert (await stored(sessions, ALAN)).display_name == "Sam"
    else:
        assert resp.status_code == 200, resp.text
        assert (await stored(sessions, ADA)).display_name == "sam"
        assert (await stored(sessions, ALAN)).display_name == "alan"


async def test_two_renames_at_once_one_wins(client: httpx.AsyncClient, sessions) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)

    first, second = await asyncio.gather(rename(client, ada, "Sam"), rename(client, grace, "Sam"))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with sessions() as session:
        holders = (
            await session.execute(
                text("SELECT display_name FROM users WHERE lower(display_name) = 'sam'")
            )
        ).all()
    assert len(holders) == 1


# --------------------------------------------------------------------------
# What a rename leaves alone
# --------------------------------------------------------------------------


async def test_a_rename_leaves_the_workspace_name(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    renamed = await rename(client, tokens, "Ada L")
    assert renamed.status_code == 200, renamed.text

    listed = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    owned = [w["name"] for w in listed.json()["items"] if w["role"] == "owner"]
    assert owned == ["ada's Workspace"]


async def test_the_token_keeps_the_old_name_until_renewed(client: httpx.AsyncClient) -> None:
    """Green by design: pins existing behaviour (Where the rules meet 4)."""
    tokens = await sign_in(client)
    renamed = await rename(client, tokens, "Ada L")
    assert renamed.status_code == 200, renamed.text

    old = await client.get("/api/v1/auth/userinfo", headers=bearer(tokens))
    assert old.json()["name"] == "ada"

    fresh = renewed(await client.post("/api/v1/auth/refresh", headers=session_cookie(tokens)))
    new = await client.get("/api/v1/auth/userinfo", headers=bearer(fresh))
    assert new.json()["name"] == "Ada L"


# --------------------------------------------------------------------------
# First sign-in (Req 3)
# --------------------------------------------------------------------------


async def first_sign_in(sessions, *, email: str, name: str) -> tuple[str, str]:
    """`link_identity` for a person nobody knows; the name they got and their workspace's."""
    async with sessions() as db:
        user = await link_identity(
            db,
            provider="oidc:test",
            subject=email,
            email=email,
            email_verified=True,
            display_name=name,
            demo_workspace_name=None,
        )
        assert user is not None
        await db.commit()
        owned = [m.workspace.name for m in await memberships(db, user.id) if m.role == "owner"]
        return user.display_name, owned[0]


async def test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix(sessions) -> None:
    async with sessions.begin() as db:
        db.add(User(id=uuid7(), email="one@example.com", display_name="Sam"))
        db.add(User(id=uuid7(), email="two@example.com", display_name="Sam 2"))

    name, workspace = await first_sign_in(sessions, email="new@example.com", name="sam")

    assert name == "sam 3"
    assert workspace == "sam 3's Workspace"


async def test_a_return_sign_in_keeps_a_renamed_name(client: httpx.AsyncClient) -> None:
    """Green by design at red, with the rename in it as the positive half."""
    tokens = await sign_in(client, ADA)
    renamed = await rename(client, tokens, "Ada L")
    assert renamed.status_code == 200, renamed.text

    again = await sign_in(client, ADA)

    assert (await me(client, again))["displayName"] == "Ada L"


@pytest.mark.parametrize("commit", [True, False], ids=["holder-commits", "holder-rolls-back"])
async def test_a_first_sign_in_racing_a_held_rename(
    client: httpx.AsyncClient, sessions, engine, commit: bool
) -> None:
    await sign_in(client, GRACE)

    name, workspace = await race(
        sessions,
        engine,
        holder_email=GRACE,
        held_name="Sam",
        commit=commit,
        request=lambda: first_sign_in(sessions, email="new@example.com", name="Sam"),
    )

    expected = "Sam 2" if commit else "Sam"
    assert (name, workspace) == (expected, f"{expected}'s Workspace")


async def test_two_first_sign_ins_with_one_name(sessions) -> None:
    results = await asyncio.gather(
        first_sign_in(sessions, email="a@example.com", name="Sam"),
        first_sign_in(sessions, email="b@example.com", name="Sam"),
    )

    assert {name for name, _ in results} == {"Sam", "Sam 2"}
    assert {workspace for _, workspace in results} == {"Sam's Workspace", "Sam 2's Workspace"}


async def test_an_unusable_idp_name_still_signs_in(sessions) -> None:
    name, workspace = await first_sign_in(sessions, email="zed@example.com", name=ZWSP)

    assert name == "zed"
    assert workspace == "zed's Workspace"
