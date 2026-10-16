"""Per-user preferences (gh-3, Req 6; register D28).

One row per user, not per workspace, written by one atomic merge so two tabs
setting different keys cannot lose each other. Reading never creates the row.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from testkit import dexflow
from testkit.auth import DEMO_WORKSPACE
from testkit.dex import ADA, DEX_PASSWORD, GRACE
from testkit.dexflow import session_cookie

URL = "/api/v1/users/me/preferences"


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def get(client: httpx.AsyncClient, tokens: dict[str, Any]) -> httpx.Response:
    return await client.get(URL, headers=bearer(tokens))


async def patch(client: httpx.AsyncClient, tokens: dict[str, Any], body: Any) -> httpx.Response:
    return await client.patch(URL, headers=bearer(tokens), json=body)


async def choose_24h(client: httpx.AsyncClient, tokens: dict[str, Any]) -> None:
    """Setup that insists it worked, so a missing route fails here and not three lines on."""
    resp = await patch(client, tokens, {"clock": "24h"})
    assert resp.status_code == 200, resp.text


async def user_id(client: httpx.AsyncClient, tokens: dict[str, Any]) -> uuid.UUID:
    me = await client.get("/api/v1/users/me", headers=bearer(tokens))
    return uuid.UUID(me.json()["id"])


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


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


async def stored(sessions, who: uuid.UUID) -> dict[str, Any]:
    async with sessions() as session:
        value = await session.scalar(
            text("SELECT prefs FROM user_preferences WHERE user_id = :id"), {"id": who}
        )
    return json.loads(value) if isinstance(value, str) else value


async def test_no_preferences_read_as_an_empty_object_and_create_no_row(
    client: httpx.AsyncClient, sessions
) -> None:
    tokens = await sign_in(client)

    resp = await get(client, tokens)

    assert resp.status_code == 200
    assert resp.json() == {}
    async with sessions() as session:
        rows = await session.scalar(text("SELECT count(*) FROM user_preferences"))
    assert rows == 0


async def test_a_patch_is_read_back(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {"clock": "24h"})

    assert resp.status_code == 200
    assert resp.json() == {"clock": "24h"}
    assert (await get(client, tokens)).json() == {"clock": "24h"}


async def test_null_removes_a_key(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await choose_24h(client, tokens)

    resp = await patch(client, tokens, {"clock": None})

    assert resp.status_code == 200
    assert resp.json() == {}
    assert (await get(client, tokens)).json() == {}


async def test_an_unknown_key_is_400_and_nothing_changes(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await choose_24h(client, tokens)

    resp = await patch(client, tokens, {"theme": "dark"})

    assert resp.status_code == 400
    assert "theme" in resp.json()["errors"]
    assert (await get(client, tokens)).json() == {"clock": "24h"}


async def test_a_bad_value_is_400_and_nothing_changes(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await choose_24h(client, tokens)

    resp = await patch(client, tokens, {"clock": "13h"})

    assert resp.status_code == 400
    assert "clock" in resp.json()["errors"]
    assert (await get(client, tokens)).json() == {"clock": "24h"}


@pytest.mark.parametrize("with_row", [True, False], ids=["with_row", "without_row"])
async def test_merges_of_different_keys_both_land(
    client: httpx.AsyncClient, sessions, with_row: bool
) -> None:
    """Two tabs, two keys: the second writer must wait for the first, not overwrite it.

    A holds its transaction open after its merge; B's merge must block on the
    row (or on the key being inserted). A read-modify-write build does not
    block, and loses A's key (with a row) or collides on the primary key
    (without one).
    """
    from auth import preferences  # deferred: only these two tests need the module at red

    who = await user_id(client, await sign_in(client))
    if with_row:
        async with sessions.begin() as session:
            await preferences.merge(session, who, {"c": "0"}, [])

    async with sessions() as a, sessions() as b:
        await preferences.merge(a, who, {"a": "1"}, [])
        second = asyncio.create_task(preferences.merge(b, who, {"b": "2"}, []))
        blocked = await waiting_on_a_lock(sessions)
        await a.commit()
        await asyncio.wait_for(second, timeout=10)
        await b.commit()

    assert blocked, "the second merge did not wait for the first writer to finish"
    expected = {"a": "1", "b": "2", **({"c": "0"} if with_row else {})}
    assert await stored(sessions, who) == expected

    if with_row:
        async with sessions.begin() as session:
            await preferences.merge(session, who, {"a": "3"}, [])
        assert (await stored(sessions, who))["a"] == "3"


async def test_preferences_are_per_user_not_per_workspace(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    await choose_24h(client, ada)
    listed = await client.get("/api/v1/workspaces", headers=bearer(ada))
    demo = next(w["id"] for w in listed.json()["items"] if w["name"] == DEMO_WORKSPACE)

    switched = await client.post(
        "/api/v1/auth/switch-workspace", json={"workspaceId": demo}, headers=session_cookie(ada)
    )
    assert switched.status_code == 200
    in_demo = {"accessToken": switched.json()["accessToken"]}

    assert (await get(client, in_demo)).json() == {"clock": "24h"}
    assert (await get(client, grace)).json() == {}


async def test_a_deleted_account_gets_404_on_both(client: httpx.AsyncClient, sessions) -> None:
    """The detail is what a missing route lacks: a 404 here must come from the handler."""
    tokens = await sign_in(client)
    await delete_account(sessions, ADA)

    read = await get(client, tokens)
    write = await patch(client, tokens, {"clock": "24h"})

    assert read.status_code == 404
    assert read.json()["detail"] == "This account no longer exists."
    assert write.status_code == 404
    assert write.json()["detail"] == "This account no longer exists."


async def test_preferences_need_a_token(client: httpx.AsyncClient) -> None:
    read = await client.get(URL)
    write = await client.patch(URL, json={"clock": "24h"})

    assert read.status_code == 401
    assert write.status_code == 401
