"""Per-user preferences over REST (issue gh-3, Req 6; register D28).

`GET` and `PATCH /api/v1/users/me/preferences`. The row is the user's, not a
workspace's, and it is created by the first write — reading must never create it.
The merge itself, and its race, are in `test_preferences_merge.py`: that file
imports `auth.preferences`, which would stop these route tests running if it were
imported here.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text

from testkit import dexflow
from testkit.dex import ADA, DEX_PASSWORD

URL = "/api/v1/users/me/preferences"
BAD_CLOCK = ['Must be "12h" or "24h".']
GONE = "This account no longer exists."


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def user_id(client: httpx.AsyncClient, tokens: dict[str, Any]) -> str:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()["id"]


async def rows(sessions) -> list[Any]:
    async with sessions() as session:
        return (
            await session.execute(text("SELECT user_id, prefs, version FROM user_preferences"))
        ).all()


async def test_no_row_reads_as_empty_and_creates_none(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)

    resp = await client.get(URL, headers=bearer(tokens))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {}
    assert await rows(sessions) == []


async def test_a_patch_is_stored_and_read_back(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)

    patched = await client.patch(URL, headers=bearer(tokens), json={"clock": "24h"})

    assert patched.status_code == 200, patched.text
    assert patched.json() == {"clock": "24h"}
    assert (await client.get(URL, headers=bearer(tokens))).json() == {"clock": "24h"}
    stored = await rows(sessions)
    assert [(str(r.user_id), r.prefs) for r in stored] == [
        (await user_id(client, tokens), {"clock": "24h"})
    ]

    changed = await client.patch(URL, headers=bearer(tokens), json={"clock": "12h"})
    assert changed.json() == {"clock": "12h"}
    assert (await client.get(URL, headers=bearer(tokens))).json() == {"clock": "12h"}


async def test_null_removes_the_key(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await client.patch(URL, headers=bearer(tokens), json={"clock": "24h"})
    assert (await client.get(URL, headers=bearer(tokens))).json() == {"clock": "24h"}

    removed = await client.patch(URL, headers=bearer(tokens), json={"clock": None})

    assert removed.status_code == 200, removed.text
    assert removed.json() == {}
    assert (await client.get(URL, headers=bearer(tokens))).json() == {}


async def test_a_patch_that_removes_everything_still_writes_the_row(
    client: httpx.AsyncClient, sessions
) -> None:
    """Decision 27: only *reading* must not create a row."""
    tokens = await sign_in(client)

    resp = await client.patch(URL, headers=bearer(tokens), json={"clock": None})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {}
    stored = await rows(sessions)
    assert [r.prefs for r in stored] == [{}]


async def test_an_unknown_key_is_400_and_changes_nothing(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    await client.patch(URL, headers=bearer(tokens), json={"clock": "24h"})

    resp = await client.patch(URL, headers=bearer(tokens), json={"clock": "12h", "theme": "x"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"] == {"theme": ["Unknown preference."]}
    # The good key beside the bad one was not applied either.
    assert (await client.get(URL, headers=bearer(tokens))).json() == {"clock": "24h"}


async def test_a_bad_value_is_400(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.patch(URL, headers=bearer(tokens), json={"clock": "25h"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"] == {"clock": BAD_CLOCK}
    assert (await client.get(URL, headers=bearer(tokens))).json() == {}


async def test_each_write_bumps_the_version(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)

    versions = []
    for value in ("24h", "12h", "24h"):
        patched = await client.patch(URL, headers=bearer(tokens), json={"clock": value})
        assert patched.status_code == 200, patched.text
        (row,) = await rows(sessions)
        versions.append(row.version)

    assert versions[1] == versions[0] + 1
    assert versions[2] == versions[1] + 1


async def test_a_deleted_account_gets_404_on_both(client: httpx.AsyncClient, sessions) -> None:
    tokens = await sign_in(client)
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": ADA}
        )
        await session.commit()

    read = await client.get(URL, headers=bearer(tokens))
    write = await client.patch(URL, headers=bearer(tokens), json={"clock": "24h"})

    assert read.status_code == 404
    assert read.json()["detail"] == GONE
    assert write.status_code == 404
    assert write.json()["detail"] == GONE
    assert await rows(sessions) == []


async def test_the_routes_need_a_token(client: httpx.AsyncClient) -> None:
    read = await client.get(URL)
    write = await client.patch(URL, json={"clock": "24h"})

    assert read.status_code == 401
    assert write.status_code == 401
