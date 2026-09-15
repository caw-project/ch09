"""Token verification with no network (Conventions §5.1, §5.5).

`decode_claims` is the verification core every front door shares, and it needs
only a `KeySource` — a `StaticKeySource` from `tokens.key_source()`, or a
`JwksClient` over `httpx.MockTransport`. The denylist is never consulted on these
paths, so it is a client that is never connected.

The HTTP-level tests of `require_user` and the denylist are integration tests in
`tests/integration/test_security.py`, because they need a real R1.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import jwt
import pytest
import redis.asyncio as aioredis
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI

from shared import (
    Denylist,
    JwksClient,
    KeySource,
    ProblemException,
    SecurityConfig,
    SecurityContext,
    ServicePrincipal,
    install_problem_handlers,
    install_security,
    jwks_document,
    keys,
    require_service,
)
from shared.keys import DEFAULT_HARD_REFRESH_SECONDS
from shared.security import decode_claims
from testkit.apps import asgi_client
from testkit.tokens import ISSUER, KEY_ID, USER_AUDIENCE, Tokens


@pytest.fixture
async def denylist() -> AsyncIterator[Denylist]:
    # Constructing a client opens no connection, and nothing here reaches it.
    client = aioredis.from_url("redis://denylist.invalid:6379/0")
    yield Denylist(client)
    await client.aclose()


def context(key_source: KeySource, denylist: Denylist) -> SecurityContext:
    return SecurityContext(
        key_source=key_source, config=SecurityConfig(issuer=ISSUER), denylist=denylist
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _segments(header: dict[str, Any], claims: dict[str, Any]) -> str:
    return f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"


def _claims_of(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


async def _refused(ctx: SecurityContext, token: str, audience: str = USER_AUDIENCE) -> int:
    with pytest.raises(ProblemException) as raised:
        await decode_claims(ctx, token, audience=audience)
    return raised.value.status


# --- the algorithm is the server's choice, never the token's ----------------


async def test_a_token_with_alg_none_is_refused(tokens: Tokens, denylist: Denylist) -> None:
    """An unsigned token naming a real kid: only the algorithm allowlist stops it."""
    unsigned = _segments({"alg": "none", "typ": "JWT", "kid": KEY_ID}, _claims_of(tokens.mint()))
    token = f"{unsigned}."

    assert await _refused(context(tokens.key_source(), denylist), token) == 401


async def test_an_hs256_token_keyed_with_the_public_key_is_refused(
    tokens: Tokens, signing_key: rsa.RSAPrivateKey, denylist: Denylist
) -> None:
    """Key confusion: the RSA public key is public, so as an HMAC secret it forges anything."""
    public_pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    signing_input = _segments(
        {"alg": "HS256", "typ": "JWT", "kid": KEY_ID}, _claims_of(tokens.mint())
    )
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{_b64(signature)}"

    assert await _refused(context(tokens.key_source(), denylist), token) == 401


# --- required claims ---------------------------------------------------------


@pytest.mark.parametrize("claim", ["sub", "jti", "exp"])
async def test_a_token_missing_a_required_claim_is_refused(
    tokens: Tokens, denylist: Denylist, claim: str
) -> None:
    """No `sub` is no principal, no `jti` cannot be revoked, no `exp` never expires."""
    token = tokens.mint(**{claim: None})
    assert claim not in _claims_of(token)

    assert await _refused(context(tokens.key_source(), denylist), token) == 401


# --- the internal audience ---------------------------------------------------


def _internal_app(tokens: Tokens, denylist: Denylist) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    install_security(
        app, key_source=tokens.key_source(), config=SecurityConfig(issuer=ISSUER), denylist=denylist
    )

    @app.post("/api/v1/internal/variants")
    async def variants(
        principal: ServicePrincipal = Depends(require_service("assets:write-variants")),
    ) -> dict[str, str]:
        return {"service": principal.name}

    return app


async def test_an_internal_audience_token_without_a_service_subject_is_refused(
    tokens: Tokens, denylist: Denylist
) -> None:
    """The audience alone is not enough: the subject must name a service (§5.5)."""
    token = tokens.service(sub=str(tokens.ADA))

    async with asgi_client(_internal_app(tokens, denylist)) as client:
        resp = await client.post(
            "/api/v1/internal/variants", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 401
    assert resp.json()["type"] == "https://collabhub.dev/problems/unauthorized"


# --- Auth is down (the JWKS refresh) ----------------------------------------
#
# The consequence of a JWKS fetch failing, seen from the verification core: a
# raw `httpx` error out of `decode_claims` is an unhandled exception, which every
# service renders as a 500 for every request.


class _Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def monotonic(self) -> float:
        return self.now


class _Auth:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.up = True

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=self.document)

    def client(self) -> JwksClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))
        return JwksClient("http://auth/.well-known/jwks.json", http_client=http)


async def test_a_valid_token_is_still_verified_while_auth_is_down_and_the_cache_is_stale(
    tokens: Tokens,
    signing_key: rsa.RSAPrivateKey,
    denylist: Denylist,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(keys, "time", clock)
    auth = _Auth(jwks_document({KEY_ID: signing_key.public_key()}))
    ctx = context(auth.client(), denylist)
    await decode_claims(ctx, tokens.mint(), audience=USER_AUDIENCE)

    clock.now += DEFAULT_HARD_REFRESH_SECONDS + 1
    auth.up = False

    claims = await decode_claims(ctx, tokens.mint(), audience=USER_AUDIENCE)
    assert claims["sub"] == str(tokens.ADA)


async def test_a_token_is_refused_as_a_problem_when_auth_is_down_and_no_key_is_held(
    tokens: Tokens, denylist: Denylist, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "time", _Clock())
    auth = _Auth({"keys": []})
    auth.up = False

    status = await _refused(context(auth.client(), denylist), tokens.mint())

    # An outage, not a bad token: a 401 would send the SPA to sign in again,
    # against an Auth that cannot answer either.
    assert status == 503
