"""Per-user preferences over REST, and the merge underneath (gh-3 Req 6; register D28).

One row per user, global to the person rather than to a workspace. The routes
are exercised through Dex like the rest of Auth; the merge race is proven at the
store, because forcing two requests to interleave through HTTP would be luck.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from auth.models import User
from shared import uuid7
from testkit import dexflow
from testkit.auth import DEMO_WORKSPACE
from testkit.dex import ADA, DEX_PASSWORD
from testkit.dexflow import session_cookie

URL = "/api/v1/users/me/preferences"
GONE = "This account no longer exists."


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def get(client: httpx.AsyncClient, tokens: dict[str, Any]) -> httpx.Response:
    return await client.get(URL, headers=bearer(tokens))


async def patch(client: httpx.AsyncClient, tokens: dict[str, Any], body: Any) -> httpx.Response:
    return await client.patch(URL, headers=bearer(tokens), json=body)


async def rows(sessions) -> int:
    async with sessions() as session:
        return int(await session.scalar(text("SELECT count(*) FROM user_preferences")))


async def wait_until_blocked(sessions) -> None:
    """Return once some backend in this database waits on a lock; fail after 5 s."""
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
    pytest.fail("B never blocked on the preferences row")


async def test_no_row_reads_as_empty_and_creates_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    """Reading is free of side effects: a user with no choices has no row."""
    tokens = await sign_in(client)

    resp = await get(client, tokens)

    assert resp.status_code == 200
    assert resp.json() == {}
    assert await rows(sessions) == 0


async def test_an_empty_patch_changes_nothing_and_writes_no_row(
    client: httpx.AsyncClient, sessions
) -> None:
    """`{}` answers with the current keys and still creates nothing."""
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {})

    assert resp.status_code == 200
    assert resp.json() == {}
    assert await rows(sessions) == 0


async def test_a_patch_is_stored_and_read_back(client: httpx.AsyncClient) -> None:
    """The answer is the stored keys, flat, and a later read agrees."""
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {"clock": "24h"})

    assert resp.status_code == 200
    assert resp.json() == {"clock": "24h"}
    assert (await get(client, tokens)).json() == {"clock": "24h"}


async def test_null_removes_a_key(client: httpx.AsyncClient) -> None:
    """`null` is "automatic" again: the key is gone, not stored as null."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "24h"})

    resp = await patch(client, tokens, {"clock": None})

    assert resp.status_code == 200
    assert resp.json() == {}
    assert (await get(client, tokens)).json() == {}


async def test_the_last_write_on_one_key_wins(client: httpx.AsyncClient) -> None:
    """Two tabs on the same key: the later choice stands."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "24h"})

    await patch(client, tokens, {"clock": "12h"})

    assert (await get(client, tokens)).json() == {"clock": "12h"}


async def test_an_unknown_key_is_400_and_nothing_changes(client: httpx.AsyncClient) -> None:
    """The valid key in the same body is not applied either."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "12h"})

    resp = await patch(client, tokens, {"clock": "24h", "theme": "dark"})

    assert resp.status_code == 400
    assert resp.json()["errors"]["theme"]
    assert "clock" not in resp.json()["errors"]
    assert (await get(client, tokens)).json() == {"clock": "12h"}


async def test_a_bad_value_is_400(client: httpx.AsyncClient) -> None:
    """A value outside the key's set is an error on that key."""
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {"clock": "13h"})

    assert resp.status_code == 400
    assert resp.json()["errors"]["clock"]
    assert (await get(client, tokens)).json() == {}


async def test_a_deleted_account_is_404(client: httpx.AsyncClient, sessions) -> None:
    """The token is still valid by signature; the account behind it is gone.

    The `detail` is asserted: before the routes exist the router's own 404
    answers, and a bare status check would pass without them.
    """
    tokens = await sign_in(client)
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :e"), {"e": ADA}
        )
        await session.commit()

    read = await get(client, tokens)
    write = await patch(client, tokens, {"clock": "24h"})

    assert read.status_code == 404
    assert read.json()["detail"] == GONE
    assert write.status_code == 404
    assert write.json()["detail"] == GONE


async def test_preferences_follow_the_user_across_workspaces(client: httpx.AsyncClient) -> None:
    """They belong to the person: a token for another workspace reads the same choice."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "24h"})
    listed = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    demo = next(w["id"] for w in listed.json()["items"] if w["name"] == DEMO_WORKSPACE)

    switched = await client.post(
        "/api/v1/auth/switch-workspace",
        json={"workspaceId": demo},
        headers=session_cookie(tokens),
    )
    assert switched.status_code == 200

    resp = await get(client, switched.json())

    assert resp.status_code == 200
    assert resp.json() == {"clock": "24h"}


async def test_preferences_need_a_token(client: httpx.AsyncClient) -> None:
    """Both routes sit behind `require_user`: no bearer, 401."""
    assert (await client.get(URL)).status_code == 401
    assert (await client.patch(URL, json={"clock": "24h"})).status_code == 401


async def test_two_writers_on_different_keys_both_land(sessions) -> None:
    """Two tabs set different keys at once: the merge keeps both.

    A read-modify-write in Python would let the second overwrite the first.
    """
    from auth.preferences import PreferencesPatch, apply_patch, read

    user = User(id=uuid7(), email="merge@x.dev", display_name="merge")
    async with sessions.begin() as session:
        session.add(user)

    async with sessions() as a, sessions() as b:
        await apply_patch(a, user.id, PreferencesPatch(set={"clock": "24h"}, remove=frozenset()))

        writer_b = asyncio.create_task(
            apply_patch(b, user.id, PreferencesPatch(set={"probe": "1"}, remove=frozenset()))
        )
        try:
            await wait_until_blocked(sessions)
            await a.commit()
            await asyncio.wait_for(writer_b, timeout=10)
        finally:
            writer_b.cancel()
        await b.commit()

    async with sessions() as session:
        assert await read(session, user.id) == {"clock": "24h", "probe": "1"}
