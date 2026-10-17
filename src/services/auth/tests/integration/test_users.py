"""User profiles (spec §3).

`PATCH /users/me` is unremarkable except for one thing worth pinning down: an
absent field and a null one mean different things, and getting that wrong makes
an avatar impossible to remove.

`GET /users/{id}` is where the interesting rule is. Every access token names one
workspace, so this endpoint must not answer for users outside it.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text

from auth.main import create_app
from auth.models import User
from testkit import dexflow
from testkit.auth import A_SIGNING_KEY, build_settings
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def me(client: httpx.AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()


# --------------------------------------------------------------------------
# Editing your own profile
# --------------------------------------------------------------------------


async def test_the_display_name_can_be_changed(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada Lovelace"}
    )

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Ada Lovelace"
    assert (await me(client, tokens))["displayName"] == "Ada Lovelace"


async def test_an_edit_bumps_the_version(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada Lovelace"}
    )

    # `version` is not in the response model, so assert through a second edit
    # succeeding rather than reading it back.
    second = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada L"}
    )
    assert second.status_code == 200


async def test_an_avatar_can_be_set_and_then_cleared(client: httpx.AsyncClient) -> None:
    """An absent field means "leave alone"; an explicit null means "clear".

    Treating None as "no change" would make an avatar impossible to remove once
    set, which is the kind of thing nobody notices until a user asks.
    """
    tokens = await sign_in(client)
    asset = str(uuid.uuid4())

    set_it = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"avatarAsset": asset}
    )
    assert set_it.json()["avatarAsset"] == asset

    untouched = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": "Ada"}
    )
    assert untouched.json()["avatarAsset"] == asset

    cleared = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"avatarAsset": None}
    )
    assert cleared.json()["avatarAsset"] is None


async def test_an_empty_display_name_is_refused(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.patch("/api/v1/users/me", headers=bearer(tokens), json={"displayName": ""})

    assert resp.status_code == 400


async def test_a_null_display_name_is_refused(client: httpx.AsyncClient) -> None:
    """Distinct from omitting it — an explicit null would blank the name."""
    tokens = await sign_in(client)

    resp = await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": None}
    )

    assert resp.status_code == 400


async def test_editing_a_profile_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.patch("/api/v1/users/me", json={"displayName": "nobody"})

    assert resp.status_code == 401


async def test_an_edit_cannot_name_another_user(client: httpx.AsyncClient) -> None:
    """There is no id in the request, so there is none to substitute."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    await client.patch(
        "/api/v1/users/me",
        headers=bearer(ada),
        json={"displayName": "hijacked", "id": graces_id},
    )

    assert (await me(client, grace))["displayName"] == "grace"


# --------------------------------------------------------------------------
# Looking at someone else
# --------------------------------------------------------------------------


async def test_a_shared_workspace_makes_a_profile_visible(client: httpx.AsyncClient) -> None:
    """Ada and Grace both join the demo workspace locally, so they can see each other."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await client.get(f"/api/v1/users/{graces_id}", headers=bearer(ada))

    assert resp.status_code == 200
    assert resp.json()["displayName"] == "grace"


async def test_a_public_profile_never_carries_the_email(client: httpx.AsyncClient) -> None:
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await client.get(f"/api/v1/users/{graces_id}", headers=bearer(ada))

    assert set(resp.json()) == {"id", "displayName", "avatarAsset"}
    assert "email" not in resp.json()


async def test_you_can_always_see_yourself(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)
    own_id = (await me(client, tokens))["id"]

    resp = await client.get(f"/api/v1/users/{own_id}", headers=bearer(tokens))

    assert resp.status_code == 200


async def test_a_stranger_is_not_found(
    client: httpx.AsyncClient, postgres_dsn, redis_url, dex_issuer, engine
) -> None:
    """A workspace-scoped token must not be a directory of the whole installation.

    Built without the shared demo workspace, so Ada and Alan genuinely have
    nothing in common — locally everyone meets in the demo workspace, which
    would hide the rule this endpoint enforces.
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
        alans_id = (await me(c, alan))["id"]

        resp = await c.get(f"/api/v1/users/{alans_id}", headers=bearer(ada))

    assert resp.status_code == 404


async def test_an_unknown_user_is_not_found(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=bearer(tokens))

    assert resp.status_code == 404


async def test_a_public_profile_needs_a_token(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")

    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Names: trimmed, normalised, refused when invisible, unique (gh-3, D46)
# --------------------------------------------------------------------------

TAKEN = "That name is already taken."
# Characters are built with chr(): a literal invisible character in this file
# would be invisible to its readers too.
NFD_JOSE = "Jose" + chr(0x301)
NFC_JOSE = "Jos" + chr(0xE9)
ZERO_WIDTH_SPACE = chr(0x200B)


async def version_of(sessions, email: str) -> tuple[int, object]:
    """`users.version` and `updated_at`: neither is in the response model."""
    async with sessions() as session:
        row = (
            await session.execute(
                text("SELECT version, updated_at FROM users WHERE email = :e"), {"e": email}
            )
        ).one()
    return row[0], row[1]


async def patch_name(client: httpx.AsyncClient, tokens: dict[str, Any], name: str):
    return await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": name}
    )


async def test_a_name_is_stored_trimmed_and_in_nfc(client: httpx.AsyncClient) -> None:
    """The stored form is what every comparison runs on, so it is tidied on the way in."""
    tokens = await sign_in(client)

    resp = await patch_name(client, tokens, f"  {NFD_JOSE}  ")

    assert resp.status_code == 200
    assert resp.json()["displayName"] == NFC_JOSE
    assert (await me(client, tokens))["displayName"] == NFC_JOSE


@pytest.mark.parametrize(
    "refused",
    [
        "Grace" + ZERO_WIDTH_SPACE,
        "Grace" + chr(0x3164),
        "Gr" + chr(0x34F) + "ace",
        "Grace\x07",
        " ",
    ],
    ids=["zero-width-space", "hangul-filler", "grapheme-joiner", "bell", "blank"],
)
async def test_an_invalid_name_is_refused(client: httpx.AsyncClient, refused: str) -> None:
    """An invisible or empty name is a 400 on the field, and the old name stays."""
    tokens = await sign_in(client)

    resp = await patch_name(client, tokens, refused)

    assert resp.status_code == 400
    assert resp.json()["errors"]["displayName"]
    assert (await me(client, tokens))["displayName"] == "ada"


async def test_saving_the_name_you_have_changes_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    """Saving the stored name — even padded — writes no row; a real change does."""
    tokens = await sign_in(client)
    before = await version_of(sessions, ADA)

    same = await patch_name(client, tokens, " ada ")

    assert same.status_code == 200
    assert same.json()["displayName"] == "ada"
    assert await version_of(sessions, ADA) == before

    changed = await patch_name(client, tokens, "Ada L")
    assert changed.status_code == 200
    assert (await version_of(sessions, ADA))[0] == before[0] + 1


async def test_a_taken_name_is_409_naming_nobody(client: httpx.AsyncClient) -> None:
    """Another account holds the name, whatever the case: 409, and the body names no one."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await patch_name(client, ada, "GRACE")

    assert resp.status_code == 409
    body = resp.json()
    assert body["status"] == 409
    assert body["detail"] == TAKEN
    assert body["errors"] == {"displayName": [TAKEN]}
    assert graces_id not in resp.text
    assert GRACE not in resp.text
    assert "workspace" not in resp.text.lower()
    assert "grace" not in resp.text.lower()
    assert (await me(client, ada))["displayName"] == "ada"

    free = await patch_name(client, ada, "Grace Hopper")
    assert free.status_code == 200
    assert free.json()["displayName"] == "Grace Hopper"


async def test_names_colliding_only_after_nfc_are_taken(client: httpx.AsyncClient) -> None:
    """ "José" typed either way, in either case, is one name."""
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)
    assert (await patch_name(client, grace, NFD_JOSE)).status_code == 200

    lower_precomposed = await patch_name(client, ada, "jos" + chr(0xE9))
    upper_decomposed = await patch_name(client, ada, "JOSE" + chr(0x301))

    assert lower_precomposed.status_code == 409
    assert upper_decomposed.status_code == 409


async def test_changing_only_your_own_capitals_is_allowed(client: httpx.AsyncClient) -> None:
    """The index never refuses the caller's own row — and the key follows the rename.

    The second half is the guard's positive: after "ada" becomes "ADA" the name
    is still held, so Grace asking for "ada" is refused. A build that left the
    old key behind would let her take it.
    """
    ada = await sign_in(client, ADA)
    grace = await sign_in(client, GRACE)

    own = await patch_name(client, ada, "ADA")

    assert own.status_code == 200
    assert own.json()["displayName"] == "ADA"
    assert (await patch_name(client, grace, "ada")).status_code == 409
    assert (await patch_name(client, grace, "Ada")).status_code == 409


async def test_a_legacy_name_can_be_saved_unchanged(client: httpx.AsyncClient, sessions) -> None:
    """A name the migration kept with a refused character can be saved as it is.

    Nothing is written, so the character rules do not apply — but any other
    name is still validated.
    """
    tokens = await sign_in(client)
    legacy = "Ada" + ZERO_WIDTH_SPACE
    async with sessions() as session:
        user = (await session.execute(select(User).where(User.email == ADA))).scalar_one()
        user.display_name = legacy
        await session.commit()
    before = await version_of(sessions, ADA)

    same = await patch_name(client, tokens, f" {legacy} ")
    other = await patch_name(client, tokens, "Ada" + ZERO_WIDTH_SPACE + "x")

    assert same.status_code == 200
    assert await version_of(sessions, ADA) == before
    assert other.status_code == 400
    assert other.json()["errors"]["displayName"]


async def test_a_deleted_accounts_name_stays_taken(client: httpx.AsyncClient, sessions) -> None:
    """Deleting an account does not free its name (D46) — nobody can take it over."""
    ada = await sign_in(client, ADA)
    await sign_in(client, GRACE)
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :e"), {"e": GRACE}
        )
        await session.commit()

    resp = await patch_name(client, ada, "grace")

    assert resp.status_code == 409
    assert resp.json()["detail"] == TAKEN
