"""Renaming yourself, and unique names (issue gh-3, Req 1-3; register D46).

Over REST against a real Postgres, because the rule that matters is the one the
database enforces: two accounts can never hold one name, however the requests
interleave. D46 is a deliberate exception to workspace scoping - the 409 may
reveal that a name exists somewhere, and must name nobody.

The races are staged with a held transaction rather than a sleep: one session
holds the name uncommitted, the other starts and blocks on the unique index, and
only then does the holder commit. The sleep only gives the second task time to
reach the index; if it arrives sooner it simply blocks earlier.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy import func, select, text

from auth import identities
from auth.main import create_app
from auth.models import User, Workspace, WorkspaceMember
from testkit import dexflow
from testkit.auth import A_SIGNING_KEY, build_settings
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE
from testkit.dexflow import session_cookie

TAKEN = "That name is already taken."
LENGTH = "A display name must be 1 to 100 characters."
CHARACTERS = "A display name cannot contain invisible or control characters."

ZWSP = chr(0x200B)
HANGUL_FILLER = chr(0x3164)
CGJ = chr(0x034F)
NBSP = chr(0x00A0)
E_ACUTE = chr(0x00E9)
E_DIAERESIS = chr(0x00EB)
COMBINING_ACUTE = chr(0x0301)
CAPITAL_E_ACUTE = chr(0x00C9)


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def me(client: httpx.AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()


async def rename(
    client: httpx.AsyncClient, tokens: dict[str, Any], name: str | None
) -> httpx.Response:
    return await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": name}
    )


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def row(sessions, email: str) -> dict[str, Any]:
    async with sessions() as session:
        result = await session.execute(
            text("SELECT display_name, version, updated_at FROM users WHERE email = :email"),
            {"email": email},
        )
        return dict(result.mappings().one())


# --------------------------------------------------------------------------
# Req 1 - the rename itself
# --------------------------------------------------------------------------


async def test_a_rename_is_stored_trimmed_and_nfc(client: httpx.AsyncClient) -> None:
    """The stored form is the trimmed, composed one - in the response and on a later read."""
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "  Jose" + COMBINING_ACUTE + "  ")

    assert resp.status_code == 200, resp.text
    assert resp.json()["displayName"] == "Jos" + E_ACUTE
    assert (await me(client, tokens))["displayName"] == "Jos" + E_ACUTE


async def test_a_refused_name_is_400_on_display_name_and_changes_nothing(
    client: httpx.AsyncClient,
) -> None:
    """Each example Req 1 refuses is a 400 on `displayName`, with the rule's own text."""
    tokens = await sign_in(client)
    cases = [
        ("Grace" + ZWSP, CHARACTERS),
        ("Grace" + HANGUL_FILLER, CHARACTERS),
        ("Gr" + CGJ + "ace", CHARACTERS),
        ("Grace\x07", CHARACTERS),
        (NBSP, LENGTH),
        ("   ", LENGTH),
        ("a" * 101, LENGTH),
    ]

    for name, message in cases:
        resp = await rename(client, tokens, name)

        assert resp.status_code == 400, (name, resp.text)
        assert resp.json()["errors"]["displayName"] == [message], name
        assert (await me(client, tokens))["displayName"] == "ada", name


async def test_a_name_of_exactly_100_characters_is_accepted(client: httpx.AsyncClient) -> None:
    """The upper bound's inside edge, beside the 101 refused above."""
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "a" * 100)

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "a" * 100


# --------------------------------------------------------------------------
# Req 2 / D46 - unique everywhere
# --------------------------------------------------------------------------


async def test_a_taken_name_is_409_and_names_nobody(client: httpx.AsyncClient) -> None:
    """The refusal reveals only that the name exists - no user, id, email or workspace."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces = await me(client, grace)

    resp = await rename(client, ada, "GRACE")

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert set(body) == {"type", "title", "status", "detail", "instance", "traceId", "errors"}
    assert body["detail"] == TAKEN
    assert body["errors"] == {"displayName": [TAKEN]}
    for secret in ("grace", graces["id"], GRACE):
        assert secret not in resp.text
    assert (await me(client, ada))["displayName"] == "ada"

    # The positive half: the same call with a free name is accepted.
    assert (await rename(client, ada, "Grace Hopper")).status_code == 200


async def test_names_differing_only_in_normalisation_collide_both_ways(
    client: httpx.AsyncClient,
) -> None:
    """Req 2's NFC clause: a name taken composed is taken decomposed, and the reverse."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)

    assert (await rename(client, grace, "Jos" + E_ACUTE)).status_code == 200
    taken = await rename(client, ada, "JOSE" + COMBINING_ACUTE)
    assert taken.status_code == 409, taken.text

    assert (await rename(client, grace, "Zo" + E_DIAERESIS)).status_code == 200
    taken = await rename(client, ada, "zoe" + chr(0x0308))
    assert taken.status_code == 409, taken.text
    assert (await me(client, ada))["displayName"] == "ada"


async def test_changing_only_your_own_capitals_is_allowed(client: httpx.AsyncClient) -> None:
    """Your own name never collides with yourself - but it does with everyone else."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)

    own = await rename(client, ada, "ADA")
    assert own.status_code == 200, own.text
    assert own.json()["displayName"] == "ADA"

    other = await rename(client, grace, "ada")
    assert other.status_code == 409, other.text


async def test_saving_the_name_you_have_changes_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    """Req 1: no bump of `version` or `updated_at` - and a real rename still bumps both."""
    tokens = await sign_in(client)
    before = await row(sessions, ADA)

    same = await rename(client, tokens, "  ada  ")
    assert same.status_code == 200, same.text
    assert same.json()["displayName"] == "ada"
    assert await row(sessions, ADA) == before

    changed = await rename(client, tokens, "Ada Lovelace")
    assert changed.status_code == 200
    after = await row(sessions, ADA)
    assert after["version"] == before["version"] + 1
    assert after["updated_at"] > before["updated_at"]


async def test_a_deleted_accounts_name_stays_taken(client: httpx.AsyncClient, sessions) -> None:
    """Uniqueness counts deleted accounts on purpose: a freed name is a name to impersonate."""
    ada = await sign_in(client, ADA)
    await sign_in(client, GRACE)
    await delete_account(sessions, GRACE)

    taken = await rename(client, ada, "grace")
    assert taken.status_code == 409, taken.text
    assert taken.json()["errors"] == {"displayName": [TAKEN]}

    assert (await rename(client, ada, "grace the second")).status_code == 200


async def test_a_name_in_a_workspace_you_cannot_see_is_still_taken(
    postgres_dsn, redis_url, dex_issuer, engine
) -> None:
    """D46: global, not per workspace - and the answer is the same as for a neighbour.

    Built without the shared demo workspace, so Ada and Alan genuinely share
    nothing; locally everyone meets there, which would hide the rule.
    """
    app = create_app(
        build_settings(
            postgres_dsn,
            redis_url,
            dex_issuer,
            app_env="production",
            auth_signing_key=A_SIGNING_KEY,
        )
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        ada = await sign_in(c, ADA)
        alan = await sign_in(c, ALAN)
        graces = await sign_in(c, GRACE)
        # Nothing shared: Alan cannot see Ada at all.
        assert (
            await c.get(f"/api/v1/users/{(await me(c, ada))['id']}", headers=bearer(alan))
        ).status_code == 404

        elsewhere = await rename(c, alan, "ada")
        assert elsewhere.status_code == 409, elsewhere.text
        # Same answer for a name nobody could see as for any other taken name.
        assert (await rename(c, graces, "ALAN")).json()["errors"] == elsewhere.json()["errors"]
        assert elsewhere.json()["errors"] == {"displayName": [TAKEN]}
        assert (await me(c, alan))["displayName"] == "alan"


async def test_two_renames_to_one_name_at_once(client: httpx.AsyncClient, sessions) -> None:
    """Exactly one wins and the other is told so; the database never holds two."""
    grace = await sign_in(client, GRACE)
    alan = await sign_in(client, ALAN)

    results = await asyncio.gather(rename(client, grace, "Sam"), rename(client, alan, "Sam"))

    assert sorted(r.status_code for r in results) == [200, 409]
    async with sessions() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(func.lower(User.display_name) == "sam")
        )
    assert count == 1


async def test_a_rename_leaves_the_users_workspace_name(client: httpx.AsyncClient) -> None:
    """Guard: a workspace's name is not its owner's, so a rename must not rewrite it."""
    tokens = await sign_in(client)

    await rename(client, tokens, "Ada Lovelace")

    listed = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    assert "ada's Workspace" in [w["name"] for w in listed.json()["items"]]


async def test_the_name_claim_changes_at_the_next_refresh(client: httpx.AsyncClient) -> None:
    """Guard: the token keeps the old name until renewal, which re-reads the user."""
    tokens = await sign_in(client)

    await rename(client, tokens, "Ada Lovelace")

    stale = await client.get("/api/v1/auth/userinfo", headers=bearer(tokens))
    assert stale.json()["name"] == "ada"
    renewal = await client.post("/api/v1/auth/refresh", headers=session_cookie(tokens))
    assert renewal.status_code == 200, renewal.text
    fresh = await client.get("/api/v1/auth/userinfo", headers=bearer(dexflow.renewed(renewal)))
    assert fresh.json()["name"] == "Ada Lovelace"


# --------------------------------------------------------------------------
# Req 3 - first sign-in
# --------------------------------------------------------------------------


async def provision(sessions, email: str, display_name: str) -> User:
    async with sessions() as session:
        user = await identities.provision_user(
            session, email=email, display_name=display_name, demo_workspace_name=None
        )
        await session.commit()
        return user


async def test_a_first_sign_in_with_a_taken_name_gets_the_first_free_suffix(sessions) -> None:
    """`ADA` is taken as `ada`, `ada 2` is taken too, so the account is `ADA 3` - and so is its workspace."""
    await provision(sessions, "one@example.com", "ada")
    await provision(sessions, "two@example.com", "ada 2")

    user = await provision(sessions, "three@example.com", "ADA")

    assert user.display_name == "ADA 3"
    async with sessions() as session:
        workspace = (
            await session.execute(
                select(Workspace.name)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == user.id)
            )
        ).scalar_one()
    assert workspace == "ADA 3's Workspace"


async def test_a_returning_sign_in_never_overwrites_the_name(client: httpx.AsyncClient) -> None:
    """Guard: the IdP says "ada" again, and the user's chosen name wins."""
    tokens = await sign_in(client)
    assert (await rename(client, tokens, "Ada Lovelace")).status_code == 200

    again = await sign_in(client)

    assert (await me(client, again))["displayName"] == "Ada Lovelace"


async def test_two_first_sign_ins_with_one_name_both_succeed(sessions) -> None:
    """The index fails the second insert; sign-in answers by taking the next suffix."""
    results = await asyncio.gather(
        provision(sessions, "a@example.com", "Sam"), provision(sessions, "b@example.com", "Sam")
    )

    assert sorted(u.display_name for u in results) == ["Sam", "Sam 2"]


async def test_a_sign_in_behind_an_uncommitted_rename_takes_the_next_suffix(
    client: httpx.AsyncClient, sessions
) -> None:
    """Order 1 of the rename/sign-in race: the renamer holds "X", the sign-in falls to "X 2"."""
    await sign_in(client, GRACE)

    async with sessions() as holder:
        graces = (await holder.execute(select(User).where(User.email == GRACE))).scalar_one()
        graces.display_name = "X"
        await holder.flush()

        signing_in = asyncio.create_task(provision(sessions, "new@example.com", "X"))
        await asyncio.sleep(0.2)
        await holder.commit()

    assert (await signing_in).display_name == "X 2"
    assert (await row(sessions, GRACE))["display_name"] == "X"


async def test_a_rename_behind_an_uncommitted_first_sign_in_is_409(
    client: httpx.AsyncClient, sessions
) -> None:
    """Order 2: the sign-in holds "X" first, so the rename that waited on it is refused."""
    grace = await sign_in(client, GRACE)

    async with sessions() as holder:
        await identities.provision_user(
            holder, email="new@example.com", display_name="X", demo_workspace_name=None
        )
        renaming = asyncio.create_task(rename(client, grace, "X"))
        await asyncio.sleep(0.2)
        await holder.commit()

    resp = await renaming
    assert resp.status_code == 409, resp.text
    assert resp.json()["errors"] == {"displayName": [TAKEN]}
    assert (await row(sessions, GRACE))["display_name"] == "grace"


async def test_an_idp_name_with_refused_characters_is_cleaned(sessions) -> None:
    """Sign-in never refuses over a name, and a stored name is always a valid one."""
    user = await provision(sessions, "zw@example.com", "Sam" + ZWSP)

    assert user.display_name == "Sam"
