"""A deleted account signs in to nothing (spec §4, Conventions §3).

Nothing in the API deletes an account yet, so `users.deleted_at` is set directly
in SQL. What these pin is that every way back in reads the column: a refresh
token issued before the deletion, an authorization code collected before it, a
fresh federated sign-in, and the access token the user is still holding.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text

from testkit import dexflow
from testkit.dex import ADA, DEX_PASSWORD, GRACE
from testkit.dexflow import session_cookie


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def test_a_deleted_account_cannot_refresh(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)
    await delete_account(sessions, ADA)

    resp = await client.post("/api/v1/auth/refresh", headers=session_cookie(tokens))

    assert resp.status_code == 401


async def test_a_deleted_account_has_no_profile(client: httpx.AsyncClient, sessions) -> None:
    """The access token is still valid by signature; the account behind it is gone."""
    tokens = await sign_in(client)
    await delete_account(sessions, ADA)

    resp = await client.get("/api/v1/users/me", headers=bearer(tokens))

    assert resp.status_code == 404


async def test_a_deleted_account_is_left_out_of_the_members_list(
    client: httpx.AsyncClient, sessions
) -> None:
    ada = await sign_in(client, ADA)
    await sign_in(client, GRACE)
    listed = await client.get("/api/v1/workspaces", headers=bearer(ada))
    workspace = next(w["id"] for w in listed.json()["items"] if w["role"] == "owner")
    added = await client.post(
        f"/api/v1/workspaces/{workspace}/members",
        headers=bearer(ada),
        json={"email": GRACE, "role": "member"},
    )
    assert added.status_code == 201, added.text
    await delete_account(sessions, GRACE)

    resp = await client.get(f"/api/v1/workspaces/{workspace}/members", headers=bearer(ada))

    assert [m["user"]["displayName"] for m in resp.json()["items"]] == ["ada"]


async def test_signing_in_to_a_deleted_account_is_account_not_found(
    client: httpx.AsyncClient, sessions
) -> None:
    """A valid upstream login, and nothing left to sign in to.

    The identity row survives the deletion, so this is the return-visit path —
    and it must not quietly provision a fresh account for the same person.
    """
    await sign_in(client)
    await delete_account(sessions, ADA)

    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)

    assert attempt["code"] is None
    assert attempt["error"] == "account_not_found"


async def test_a_code_collected_before_the_deletion_is_refused(
    client: httpx.AsyncClient, sessions
) -> None:
    """Deleted between the callback and the SPA spending the code."""
    await sign_in(client)
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)
    assert attempt["code"]
    await delete_account(sessions, ADA)

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": attempt["verifier"],
        },
    )

    assert resp.status_code == 401
