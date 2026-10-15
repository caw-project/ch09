"""How `build_server` configures the Socket.IO server it builds.

Construction opens no connection — the R2 manager connects when the server
first handles a client — so this runs at the unit layer.
"""

from __future__ import annotations

from typing import Any

import pytest

from messaging.realtime import RealtimeContext, build_server
from messaging.settings import Settings

PING_ENV = ("MESSAGING_SOCKET_PING_INTERVAL_SECONDS", "MESSAGING_SOCKET_PING_TIMEOUT_SECONDS")


def _settings(**overrides: Any) -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_messaging",
        redis_cache_url="redis://redis-cache:6379/0",
        redis_realtime_url="redis://redis-rt:6379/0",
        redis_streams_url="redis://redis-streams:6379/0",
        elasticsearch_url="http://elasticsearch:9200",
        auth_issuer="http://localhost:8001",
        auth_jwks_url="http://auth:8000/.well-known/jwks.json",
        **overrides,
    )


def _server(settings: Settings):
    # Only `settings` is read while the server is built; the rest is used by
    # handlers, which no test here invokes.
    context = RealtimeContext(  # type: ignore[arg-type]
        settings=settings, sessions=None, security=None, jobs=None, assets=None
    )
    return build_server(context)


@pytest.fixture(autouse=True)
def _no_ping_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PING_ENV:
        monkeypatch.delenv(name, raising=False)


def test_ping_interval_and_timeout_come_from_settings() -> None:
    server = _server(
        _settings(messaging_socket_ping_interval_seconds=2, messaging_socket_ping_timeout_seconds=3)
    )

    assert server.eio.ping_interval == 2
    assert server.eio.ping_timeout == 3


def test_ping_defaults_are_python_socketios_own() -> None:
    """25s and 20s: production keeps the library's behaviour unless told otherwise."""
    server = _server(_settings())

    assert server.eio.ping_interval == 25
    assert server.eio.ping_timeout == 20


TUNNEL_HOST = "quiet-fox-runs.trycloudflare.com"


def _admits(server, origin: str) -> bool:
    """Whether engine.io's handshake would accept `origin`, behind k3s's Traefik.

    The environ is what Traefik hands on for a request that came through a
    Cloudflare quick tunnel: plain `http` to the pod, `ws` as the forwarded proto.
    """
    environ = {
        "HTTP_HOST": TUNNEL_HOST,
        "wsgi.url_scheme": "http",
        "HTTP_X_FORWARDED_PROTO": "ws",
        "HTTP_ORIGIN": origin,
    }
    allowed = server.eio._cors_allowed_origins(environ)
    return allowed is None or origin in allowed


def test_an_explicit_origin_is_matched_as_given_behind_a_tls_tunnel() -> None:
    """A configured https origin must be admitted, or every handshake through a tunnel fails."""
    server = _server(_settings(cors_allowed_origins=[f"https://{TUNNEL_HOST}"]))

    assert _admits(server, f"https://{TUNNEL_HOST}")
    assert not _admits(server, f"http://{TUNNEL_HOST}")


def test_without_a_list_a_tunnel_origin_is_refused_behind_traefik() -> None:
    """Why the chart always sets the list: the empty-list predicate rebuilds `http://`."""
    server = _server(_settings(cors_allowed_origins=[]))

    assert _admits(server, f"http://{TUNNEL_HOST}")
    assert not _admits(server, f"https://{TUNNEL_HOST}")


def test_ping_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESSAGING_SOCKET_PING_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("MESSAGING_SOCKET_PING_TIMEOUT_SECONDS", "2")

    settings = _settings()

    assert settings.messaging_socket_ping_interval_seconds == 2
    assert settings.messaging_socket_ping_timeout_seconds == 2
