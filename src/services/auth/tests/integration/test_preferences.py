"""Per-user preferences over REST (issue gh-3, Req 6; register D28).

One row per user, global across workspaces, merged by a single upsert. The
concurrency tests exist because a read-modify-write would pass every sequential
test here and still lose a tab's change.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from testkit import dexflow
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


async def rows(sessions) -> list[dict[str, Any]]:
    async with sessions() as session:
        result = await session.execute(text("SELECT prefs, version FROM user_preferences"))
        return [dict(r) for r in result.mappings().all()]


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def test_no_row_reads_empty_and_creates_none(client: httpx.AsyncClient, sessions) -> None:
    """Reading is free of side effects: a user who never chose has no row."""
    tokens = await sign_in(client)

    resp = await get(client, tokens)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {}
    assert await rows(sessions) == []


async def test_patch_merges_and_get_reads_it_back(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    first = await patch(client, tokens, {"clock": "24h"})
    assert first.status_code == 200, first.text
    assert first.json() == {"clock": "24h"}
    assert (await get(client, tokens)).json() == {"clock": "24h"}

    again = await patch(client, tokens, {"clock": "12h"})
    assert again.json() == {"clock": "12h"}
    assert (await get(client, tokens)).json() == {"clock": "12h"}


async def test_null_removes_a_key(client: httpx.AsyncClient) -> None:
    """Back to Automatic: the key is gone, not stored as null."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "24h"})

    removed = await patch(client, tokens, {"clock": None})

    assert removed.status_code == 200, removed.text
    assert removed.json() == {}
    assert (await get(client, tokens)).json() == {}


async def test_an_empty_patch_returns_the_stored_map_and_writes_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    tokens = await sign_in(client)

    blank = await patch(client, tokens, {})
    assert blank.status_code == 200, blank.text
    assert blank.json() == {}
    assert await rows(sessions) == []

    await patch(client, tokens, {"clock": "12h"})
    stored = await patch(client, tokens, {})
    assert stored.json() == {"clock": "12h"}
    assert (await rows(sessions))[0]["version"] == 1


async def test_an_unknown_key_is_400_and_nothing_changes(client: httpx.AsyncClient) -> None:
    """All or nothing: the valid key beside the unknown one is not applied either."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "12h"})

    resp = await patch(client, tokens, {"clock": "24h", "theme": "dark"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"] == {"theme": ["Unknown preference."]}
    assert (await get(client, tokens)).json() == {"clock": "12h"}


async def test_a_bad_value_is_400_on_its_key(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await patch(client, tokens, {"clock": "noon"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"] == {"clock": ['Must be "12h", "24h" or null.']}
    assert (await get(client, tokens)).json() == {}


async def test_a_deleted_account_gets_404_on_both_and_no_row(
    client: httpx.AsyncClient, sessions
) -> None:
    """The token is still valid by signature; the account behind it is not."""
    tokens = await sign_in(client)
    await delete_account(sessions, ADA)

    read = await get(client, tokens)
    write = await patch(client, tokens, {"clock": "24h"})

    assert read.status_code == 404
    assert read.json()["detail"] == GONE
    assert write.status_code == 404
    assert write.json()["detail"] == GONE
    assert await rows(sessions) == []


async def test_preferences_are_per_user_not_per_workspace(client: httpx.AsyncClient) -> None:
    """DA 7: one map per user. A token scoped to another workspace reads the same one."""
    tokens = await sign_in(client)
    await patch(client, tokens, {"clock": "24h"})
    workspaces = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    current = dexflow_workspace(tokens)
    other = next(w["id"] for w in workspaces.json()["items"] if w["id"] != current)

    switched = await client.post(
        "/api/v1/auth/switch-workspace",
        headers=session_cookie(tokens),
        json={"workspaceId": other},
    )
    assert switched.status_code == 200, switched.text

    assert (await get(client, dexflow.renewed(switched))).json() == {"clock": "24h"}


def dexflow_workspace(tokens: dict[str, Any]) -> str:
    """The `wsp` claim of an access token, read without verifying it."""
    payload = tokens["accessToken"].split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))["wsp"]


async def test_concurrent_patches_of_different_keys_keep_both(
    client: httpx.AsyncClient, sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tabs, two keys: the merge happens in the database, so neither overwrites the other."""
    # Imported here so only this test, which needs the module, depends on it at red.
    from auth import preferences

    monkeypatch.setitem(preferences.KEYS, "probe", lambda value: None)
    tokens = await sign_in(client)

    results = await asyncio.gather(
        patch(client, tokens, {"clock": "24h"}), patch(client, tokens, {"probe": "x"})
    )

    assert [r.status_code for r in results] == [200, 200]
    assert (await get(client, tokens)).json() == {"clock": "24h", "probe": "x"}
    assert (await rows(sessions))[0]["version"] == 2


async def test_concurrent_patches_of_one_key_lose_no_write(
    client: httpx.AsyncClient, sessions
) -> None:
    """Same key: the last write wins, and both are counted."""
    tokens = await sign_in(client)

    results = await asyncio.gather(
        patch(client, tokens, {"clock": "12h"}), patch(client, tokens, {"clock": "24h"})
    )

    assert [r.status_code for r in results] == [200, 200]
    assert (await get(client, tokens)).json() in ({"clock": "12h"}, {"clock": "24h"})
    assert (await rows(sessions))[0]["version"] == 2


async def test_preferences_need_a_token(client: httpx.AsyncClient) -> None:
    read = await client.get(URL)
    write = await client.patch(URL, json={"clock": "24h"})

    assert read.status_code == 401
    assert write.status_code == 401
