"""Cross-origin access for the SPA.

The case worth a test is the default: no configured origins must install no
middleware, so a service deployed same-origin does not advertise cross-origin
access it was never meant to allow.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from shared import install_cors, socket_allowed_origins

ORIGIN = "http://localhost:5173"


def build(origins: list[str]) -> FastAPI:
    app = FastAPI()
    install_cors(app, origins=origins)

    @app.get("/thing")
    async def thing() -> dict[str, bool]:
        return {"ok": True}

    return app


async def call(app: FastAPI, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/thing", headers={"Origin": origin})


async def preflight(app: FastAPI, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            "/thing",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )


async def test_a_configured_origin_is_allowed() -> None:
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-origin"] == ORIGIN


async def test_an_unlisted_origin_gets_no_allow_header() -> None:
    """No wildcard: an origin that is not on the list is simply not answered for."""
    response = await call(build([ORIGIN]), "https://evil.example")

    assert "access-control-allow-origin" not in response.headers


async def test_no_configured_origins_installs_nothing() -> None:
    """The deployed default. Same-origin behind an ingress needs no CORS at all."""
    response = await call(build([]), ORIGIN)

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_the_authorization_header_survives_preflight() -> None:
    """Every authenticated call carries it, so a preflight that drops it breaks everything."""
    response = await preflight(build([ORIGIN]), ORIGIN)

    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed


async def test_credentials_are_allowed() -> None:
    """Without this the browser drops the refresh cookie on cross-origin calls.

    CSRF is closed by `SameSite=Strict` on the cookie itself rather than by
    refusing credentials here — see `auth/cookies.py`.
    """
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-credentials"] == "true"


async def test_credentials_are_never_paired_with_a_wildcard() -> None:
    """A browser rejects `*` outright once credentials are in play."""
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-origin"] != "*"


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
async def test_the_methods_the_api_uses_are_allowed(method: str) -> None:
    response = await preflight(build([ORIGIN]), ORIGIN)

    assert method in response.headers["access-control-allow-methods"]


# --- socket_allowed_origins: Socket.IO's own check, behind a proxy ----------
#
# engine.io does its own origin check, separate from `install_cors`'s
# middleware, and only accepts a list or a callable `(origin, environ) -> bool`
# (Conventions §5.6's "no origins configured" default still has to hold here).
# Environ dicts below use engine.io's WSGI-style keys, exactly as its ASGI
# driver builds them; `HTTP_ORIGIN` is not needed because engine.io passes the
# origin as the callable's first argument.


def environ(host: str, **extra: Any) -> dict[str, Any]:
    env: dict[str, Any] = {"HTTP_HOST": host, "wsgi.url_scheme": "http"}
    env.update(extra)
    return env


def test_configured_origins_are_returned_unchanged() -> None:
    origins = [ORIGIN]

    assert socket_allowed_origins(origins) == origins


def test_a_proxy_reporting_ws_on_the_upgrade_is_still_same_origin() -> None:
    """The bug: Traefik sends `X-Forwarded-Proto: ws` on the WebSocket upgrade."""
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080", HTTP_X_FORWARDED_PROTO="ws")
    assert allowed("http://localhost:8080", env)


def test_a_proxy_reporting_wss_maps_to_https() -> None:
    allowed = socket_allowed_origins([])

    env = environ("lab.example", HTTP_X_FORWARDED_PROTO="wss")
    assert allowed("https://lab.example", env)


def test_a_proxy_reporting_plain_http_is_still_allowed() -> None:
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080", HTTP_X_FORWARDED_PROTO="http")
    assert allowed("http://localhost:8080", env)


def test_with_no_forwarded_headers_the_wsgi_scheme_is_used() -> None:
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080")
    assert allowed("http://localhost:8080", env)


def test_the_first_forwarded_host_in_a_chain_is_the_origin_host() -> None:
    """A proxy chain lists the client-facing host first, then the internal hop."""
    allowed = socket_allowed_origins([])

    env = environ(
        "collabhub-messaging:8000",
        HTTP_X_FORWARDED_PROTO="ws",
        HTTP_X_FORWARDED_HOST="a.localhost:8080, internal",
    )
    assert allowed("http://a.localhost:8080", env)


def test_a_foreign_site_is_refused() -> None:
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080", HTTP_X_FORWARDED_PROTO="ws")
    assert not allowed("http://evil.example", env)


def test_a_different_port_is_refused() -> None:
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080")
    assert not allowed("http://localhost:5173", env)


def test_a_different_scheme_is_refused() -> None:
    """No scheme leniency: `ws`/`wss` are normalised, but https is not http."""
    allowed = socket_allowed_origins([])

    env = environ("localhost:8080", HTTP_X_FORWARDED_PROTO="ws")
    assert not allowed("https://localhost:8080", env)


def test_with_no_host_headers_the_predicate_returns_false() -> None:
    """Fails closed when a handshake has neither Host nor X-Forwarded-Host."""
    allowed = socket_allowed_origins([])

    # environ with neither HTTP_HOST nor HTTP_X_FORWARDED_HOST
    env = {"wsgi.url_scheme": "http"}
    assert not allowed("http://localhost:8080", env)
