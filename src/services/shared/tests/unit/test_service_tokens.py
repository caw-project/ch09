"""`ServiceTokenSource` — one cached service token, refetched only when it must be.

Conventions §5.5: cache until shortly before expiry. The transport is an httpx
`MockTransport`, so no socket opens (unit layer) and nothing about the HTTP client
is faked: the request is built and parsed by the real client.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from shared.service_tokens import ServiceTokenSource, ServiceTokenUnavailableError

TOKEN_URL = "http://auth.test/api/v1/auth/token"
EXPIRES_IN = 900


class Auth:
    """A scripted token endpoint that counts what it was asked."""

    def __init__(self, *, status: int = 200, gate: asyncio.Event | None = None) -> None:
        self.requests: list[dict] = []
        self.status = status
        self.gate = gate

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if self.gate is not None:
            await self.gate.wait()
        if self.status != 200:
            return httpx.Response(self.status, json={"title": "Unauthorized"})
        return httpx.Response(
            200,
            json={
                "accessToken": f"token-{len(self.requests)}",
                "tokenType": "Bearer",
                "expiresIn": EXPIRES_IN,
            },
        )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def source(handler, clock: Clock | None = None) -> ServiceTokenSource:
    return ServiceTokenSource(
        token_url=TOKEN_URL,
        client_id="messaging",
        client_secret="s3cret",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=clock or Clock(),
    )


async def test_the_grant_is_the_clients_credentials():
    """Breaks if the body is not the Auth service's `client_credentials` request."""
    auth = Auth()
    assert await source(auth).token() == "token-1"
    assert auth.requests == [
        {"grantType": "client_credentials", "clientId": "messaging", "clientSecret": "s3cret"}
    ]


async def test_one_fetch_serves_until_the_margin():
    """Breaks if the token is fetched per call, or kept past `expiresIn` minus the margin."""
    auth, clock = Auth(), Clock()
    tokens = source(auth, clock)
    assert await tokens.token() == "token-1"

    clock.now += EXPIRES_IN - 61
    assert await tokens.token() == "token-1"
    assert len(auth.requests) == 1

    clock.now += 2  # now 59 s before expiry: inside the 60 s margin
    assert await tokens.token() == "token-2"
    assert len(auth.requests) == 2


async def test_two_concurrent_callers_fetch_once():
    """Breaks if each waiting caller starts its own grant — a send burst would stampede Auth."""
    gate = asyncio.Event()
    auth = Auth(gate=gate)
    tokens = source(auth)

    first = asyncio.create_task(tokens.token())
    second = asyncio.create_task(tokens.token())
    for _ in range(10):  # let both reach the held fetch
        await asyncio.sleep(0)
    assert len(auth.requests) == 1
    assert not first.done()

    gate.set()
    assert await asyncio.gather(first, second) == ["token-1", "token-1"]
    assert len(auth.requests) == 1


async def test_invalidate_forces_a_fetch():
    """Asset's 401 means the cached token is bad: breaks if `invalidate` leaves it in place."""
    auth = Auth()
    tokens = source(auth)
    assert await tokens.token() == "token-1"
    assert await tokens.token() == "token-1"  # cached, so invalidate is what changes it

    tokens.invalidate()

    assert await tokens.token() == "token-2"


async def test_a_refused_grant_raises_unavailable():
    """Breaks if a 401 from Auth leaks out as an httpx error or an empty token."""
    with pytest.raises(ServiceTokenUnavailableError):
        await source(Auth(status=401)).token()


async def test_a_refused_grant_is_not_cached():
    """Breaks if a failure is remembered: the next call must try Auth again."""
    auth = Auth(status=503)
    tokens = source(auth)
    with pytest.raises(ServiceTokenUnavailableError):
        await tokens.token()
    auth.status = 200
    assert await tokens.token() == "token-2"


async def test_auth_unreachable_raises_unavailable():
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ServiceTokenUnavailableError):
        await source(unreachable).token()
