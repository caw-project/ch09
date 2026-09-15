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
    context = RealtimeContext(settings=settings, sessions=None, security=None, jobs=None)  # type: ignore[arg-type]
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


def test_ping_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESSAGING_SOCKET_PING_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("MESSAGING_SOCKET_PING_TIMEOUT_SECONDS", "2")

    settings = _settings()

    assert settings.messaging_socket_ping_interval_seconds == 2
    assert settings.messaging_socket_ping_timeout_seconds == 2
