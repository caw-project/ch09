"""Federated sign-in through a real Dex (spec §5.1, register D5).

These are the tests that matter most in this service: everything else assumes an
identity, and this is where one comes from. They drive the genuine
authorization-code flow — Dex's login form and all — so a change that breaks
real sign-in cannot pass here.

The negative tests carry the weight. A login flow that works is easy; one that
also refuses a replayed state, a spent code, a stolen code without its verifier,
and an id_token minted for someone else is the point.
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from sqlalchemy import select

from auth import pkce
from auth.main import create_app
from auth.models import ExternalIdentity
from auth.oidc import FederatedIdentity
from auth.settings import Settings
from testkit import dexflow
from testkit.apps import asgi_client
from testkit.auth import SPA_REDIRECT, build_settings
from testkit.dex import ADA, DEX_CLIENT_ID, DEX_PASSWORD, GRACE


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def claims(tokens: dict[str, Any]) -> dict[str, Any]:
    return jwt.decode(tokens["accessToken"], options={"verify_signature": False})


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


async def test_a_dex_sign_in_issues_a_collabhub_token_pair(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    assert tokens["tokenType"] == "Bearer"
    assert tokens["expiresIn"] == 900
    assert tokens["accessToken"]
    assert tokens["refreshCookie"]


async def test_the_token_carries_the_identity_dex_asserted(client: httpx.AsyncClient) -> None:
    tokens = await sign_in(client)

    body = claims(tokens)

    assert body["email"] == ADA
    assert body["name"] == "ada"
    assert uuid.UUID(body["sub"])
    assert uuid.UUID(body["wsp"])
    assert body["roles"] == ["owner"]


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def test_signing_in_records_the_external_identity(
    client: httpx.AsyncClient, sessions
) -> None:
    """`external_identities` is what makes the second sign-in the same account.

    Asserted against the table rather than through behaviour, because the row is
    the thing register D5 was waiting on: it was created empty by the MVP and
    stayed empty until federation landed.
    """
    tokens = await sign_in(client)

    async with sessions() as session:
        rows = (await session.execute(select(ExternalIdentity))).scalars().all()

    assert len(rows) == 1
    assert rows[0].provider == "oidc:dex"
    assert rows[0].subject  # Dex's opaque subject, not the email
    assert rows[0].subject != ADA
    assert str(rows[0].user_id) == claims(tokens)["sub"]


async def test_signing_in_twice_links_no_second_identity(
    client: httpx.AsyncClient, sessions
) -> None:
    await sign_in(client)
    await sign_in(client)

    async with sessions() as session:
        rows = (await session.execute(select(ExternalIdentity))).scalars().all()

    assert len(rows) == 1


async def test_signing_in_twice_is_the_same_account(client: httpx.AsyncClient) -> None:
    first = claims(await sign_in(client))
    second = claims(await sign_in(client))

    assert first["sub"] == second["sub"]
    assert first["wsp"] == second["wsp"]


async def test_two_dex_users_are_two_accounts(client: httpx.AsyncClient) -> None:
    ada = claims(await sign_in(client, ADA))
    grace = claims(await sign_in(client, GRACE))

    assert ada["sub"] != grace["sub"]
    assert ada["email"] == ADA
    assert grace["email"] == GRACE


# --------------------------------------------------------------------------
# Beginning a login
# --------------------------------------------------------------------------


async def test_login_redirects_to_dex_with_pkce_and_state(client: httpx.AsyncClient) -> None:
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})

    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == [DEX_CLIENT_ID]
    assert query["state"]
    assert query["nonce"]
    assert query["code_challenge"]


async def test_our_own_pkce_challenge_is_not_the_spas(client: httpx.AsyncClient) -> None:
    """The two PKCE exchanges are independent — sharing them would leak the SPA's.

    If the challenge sent to Dex were the SPA's, then Dex (or anything that saw
    the authorization request) would hold the challenge protecting the
    CollabHub code as well.
    """
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})

    sent_to_dex = parse_qs(urlparse(resp.headers["location"]).query)["code_challenge"][0]
    assert sent_to_dex != challenge


async def test_login_requires_a_code_challenge(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/login/dex")

    assert resp.status_code == 400


async def test_login_refuses_plain_pkce(client: httpx.AsyncClient) -> None:
    """`plain` proves nothing; accepting it would be a way to turn PKCE off."""
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get(
        "/api/v1/auth/login/dex",
        params={"codeChallenge": challenge, "codeChallengeMethod": "plain"},
    )

    assert resp.status_code == 400
    assert "codeChallengeMethod" in resp.json()["errors"]


async def test_an_unknown_provider_is_a_404(client: httpx.AsyncClient) -> None:
    challenge = pkce.challenge_for(pkce.new_verifier())

    resp = await client.get("/api/v1/auth/login/okta", params={"codeChallenge": challenge})

    assert resp.status_code == 404


# --------------------------------------------------------------------------
# The callback — everything here redirects rather than raises
# --------------------------------------------------------------------------


async def test_a_replayed_state_is_refused(client: httpx.AsyncClient) -> None:
    """`state` is single-use: the second callback with it finds nothing in R1."""
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)

    replay = await client.get("/api/v1/auth/callback/dex", params=attempt["callback"])

    assert replay.status_code == 302
    assert parse_qs(urlparse(replay.headers["location"]).query)["error"] == ["invalid_state"]


async def test_an_unknown_state_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/callback/dex", params={"code": "anything", "state": "never-issued"}
    )

    assert resp.status_code == 302
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["invalid_state"]


async def test_a_provider_error_is_passed_to_the_spa(client: httpx.AsyncClient) -> None:
    """A denied consent must reach the SPA, not a Problem Details page."""
    resp = await client.get("/api/v1/auth/callback/dex", params={"error": "access_denied"})

    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == SPA_REDIRECT
    assert parse_qs(location.query)["error"] == ["access_denied"]


async def test_a_callback_without_a_code_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/callback/dex", params={"state": "x"})

    assert resp.status_code == 302
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["invalid_request"]


async def test_a_successful_callback_lands_on_the_configured_spa_uri(
    client: httpx.AsyncClient,
) -> None:
    """The redirect target is configuration, never taken from the request.

    There is no `redirect_uri` parameter on any endpoint here, so there is no
    open redirect to validate against an allow-list — the question never
    reaches the service.
    """
    challenge = pkce.challenge_for(pkce.new_verifier())
    started = await client.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})
    callback = await dexflow.authenticate(
        started.headers["location"], email=ADA, password=DEX_PASSWORD
    )

    resp = await client.get(
        "/api/v1/auth/callback/dex",
        params={key: values[0] for key, values in callback.items()},
    )

    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == SPA_REDIRECT
    assert parse_qs(location.query)["code"]


async def test_a_state_issued_for_one_provider_is_refused_on_another(
    postgres_dsn: str, redis_url: str, dex_issuer: str, engine
) -> None:
    """A login begun at one provider cannot be finished at another.

    Otherwise a code and state from a provider an attacker controls could be
    replayed into the callback of one the victim trusts — or the other way
    round. The second provider here is Dex again under another name, so the only
    thing that differs between the two callbacks is the provider in the path.
    """
    base = build_settings(postgres_dsn, redis_url, dex_issuer)
    dex = base.oidc_providers[0]
    settings = build_settings(
        postgres_dsn,
        redis_url,
        dex_issuer,
        oidc_providers=[dex, dex.model_copy(update={"name": "other"})],
    )

    async with asgi_client(create_app(settings)) as c:
        challenge = pkce.challenge_for(pkce.new_verifier())
        started = await c.get("/api/v1/auth/login/dex", params={"codeChallenge": challenge})
        callback = await dexflow.authenticate(
            started.headers["location"], email=ADA, password=DEX_PASSWORD
        )

        resp = await c.get(
            "/api/v1/auth/callback/other",
            params={key: values[0] for key, values in callback.items()},
        )

    assert resp.status_code == 302
    assert parse_qs(urlparse(resp.headers["location"]).query)["error"] == ["invalid_state"]


# --------------------------------------------------------------------------
# Linking a new identity to an existing account by email
# --------------------------------------------------------------------------


class AssertingProvider:
    """Stands in for `OidcClient`, asserting whatever identity the test gives it.

    Dex marks every static account's email verified, so it cannot reach the
    refusal. This replaces only the provider at the far end of the redirect:
    the login state, the callback, the database and the code exchange are all
    real. `test_oidc.py` covers the real client's reading of an id_token.
    """

    def __init__(self, identity: FederatedIdentity) -> None:
        self.name = identity.provider
        self._identity = identity

    async def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        return f"https://idp.example/authorize?state={state}"

    async def exchange(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> FederatedIdentity:
        return self._identity

    async def aclose(self) -> None:
        return None


async def arrive_elsewhere(
    app_settings: Settings, *, email_verified: bool
) -> tuple[dict[str, Any], dexflow.Attempt, dict[str, Any] | None]:
    """Ada signs in through Dex, then again through a provider she has not used.

    Returns her Dex session, the second attempt, and its session if it got one.
    """
    app = create_app(app_settings)
    async with asgi_client(app) as c:
        ada = await sign_in(c, ADA)
        app.state.oidc_clients["other"] = AssertingProvider(
            FederatedIdentity(
                provider="other",
                subject="ada-at-the-other-provider",
                email=ADA,
                email_verified=email_verified,
                display_name="Ada",
            )
        )

        verifier = pkce.new_verifier()
        started = await c.get(
            "/api/v1/auth/login/other", params={"codeChallenge": pkce.challenge_for(verifier)}
        )
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        returned = await c.get(
            "/api/v1/auth/callback/other", params={"code": "a-code", "state": state}
        )
        spa = parse_qs(urlparse(returned.headers["location"]).query)
        attempt = dexflow.Attempt(
            verifier=verifier,
            spa=spa,
            code=spa.get("code", [None])[0],
            error=spa.get("error", [None])[0],
        )
        session = await dexflow.finish(c, attempt) if attempt["code"] else None

    return ada, attempt, session


async def test_a_verified_email_links_a_new_identity_to_the_existing_account(
    app_settings: Settings, engine, sessions
) -> None:
    ada, attempt, session = await arrive_elsewhere(app_settings, email_verified=True)

    assert attempt["error"] is None
    assert session is not None
    assert claims(session)["sub"] == claims(ada)["sub"]
    async with sessions() as db:
        rows = (await db.execute(select(ExternalIdentity))).scalars().all()
    assert {(r.provider, str(r.user_id)) for r in rows} == {
        ("oidc:dex", claims(ada)["sub"]),
        ("oidc:other", claims(ada)["sub"]),
    }


async def test_an_unverified_email_is_not_linked_to_the_existing_account(
    app_settings: Settings, engine, sessions
) -> None:
    """Some providers let anyone set any address. Honouring it is account takeover."""
    _, attempt, session = await arrive_elsewhere(app_settings, email_verified=False)

    assert attempt["error"] == "email_not_verified"
    assert session is None
    async with sessions() as db:
        rows = (await db.execute(select(ExternalIdentity))).scalars().all()
    assert [r.provider for r in rows] == ["oidc:dex"]


# --------------------------------------------------------------------------
# Spending the authorization code
# --------------------------------------------------------------------------


async def test_the_authorization_code_is_single_use(client: httpx.AsyncClient) -> None:
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)
    await dexflow.finish(client, attempt)

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": attempt["verifier"],
        },
    )

    assert resp.status_code == 401


async def test_a_code_without_its_verifier_is_worthless(client: httpx.AsyncClient) -> None:
    """The whole reason the code may travel in a redirect URL.

    Someone reading the code out of browser history, a referrer header or a
    proxy log has everything except the verifier, which never left the SPA.
    """
    attempt = await dexflow.begin(client, email=ADA, password=DEX_PASSWORD)

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": pkce.new_verifier(),
        },
    )

    assert resp.status_code == 401


async def test_an_unknown_code_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": "never-issued",
            "codeVerifier": pkce.new_verifier(),
        },
    )

    assert resp.status_code == 401


async def test_an_unsupported_grant_type_is_refused(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={"grantType": "password", "code": "x", "codeVerifier": "y"},
    )

    assert resp.status_code == 400
    assert "grantType" in resp.json()["errors"]


async def test_a_snake_case_body_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/token",
        json={"grant_type": "authorization_code", "code": "x", "code_verifier": "y"},
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------
# dev-login is gone (register D5 settled)
# --------------------------------------------------------------------------


async def test_dev_login_no_longer_exists(client: httpx.AsyncClient) -> None:
    """It was deleted, not disabled — there is no flag to turn it back on."""
    resp = await client.post("/api/v1/auth/dev-login", json={"email": "anyone@example.com"})

    assert resp.status_code == 404
