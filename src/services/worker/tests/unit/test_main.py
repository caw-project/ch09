"""`worker.main.run`: what stops the Worker (design doc 05 §2).

Two rules from the module docstring. A Worker configured for a stream it has no
handlers for refuses to start, rather than dead-lettering every job on it. And a
consumer that dies takes the process with it, because a Worker answering
`/health/live` while consuming nothing is the failure nobody notices.

Unit tests, so nothing here opens a socket. The Elasticsearch and Redis clients
`run` builds are lazy and never used; `uvicorn.Server` is a stand-in that serves
until told to exit, which is the one thing `run` asks of it.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Iterator

import pytest

from worker import main
from worker.settings import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "redis_streams_url": "redis://redis-streams:6379/2",
        "elasticsearch_url": "http://elasticsearch:9200",
        "object_store_endpoint": "http://garage:3900",
        "worker_streams": "jobs:index",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def _restore_sigterm() -> Iterator[None]:
    """`run` installs a SIGTERM handler bound to its own loop and never removes it."""
    previous = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, previous)


class _Server:
    """Serves until `should_exit` is set, as Uvicorn's main loop does."""

    def __init__(self) -> None:
        self._exit = asyncio.Event()

    @property
    def should_exit(self) -> bool:
        return self._exit.is_set()

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        if value:
            self._exit.set()

    async def serve(self) -> None:
        await self._exit.wait()


async def test_a_stream_with_no_handlers_stops_startup_before_any_consumer_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_consumers(*_: object, **__: object) -> None:
        raise AssertionError("built a consumer for a Worker that should have refused to start")

    monkeypatch.setattr(main, "StreamConsumer", no_consumers)

    with pytest.raises(SystemExit, match="jobs:thumbnail"):
        await main.run(_settings(worker_streams="jobs:index,jobs:thumbnail"))


async def test_a_consumer_that_crashes_stops_the_health_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servers: list[_Server] = []

    def server(_config: object) -> _Server:
        servers.append(_Server())
        return servers[-1]

    class CrashingConsumer:
        def __init__(self, *_: object) -> None:
            pass

        async def run(self, stop: asyncio.Event) -> None:
            raise RuntimeError("the consumer died")

    async def index_ready(_es: object) -> None:
        return None

    monkeypatch.setattr(main.uvicorn, "Server", server)
    monkeypatch.setattr(main, "ensure_messages_index", index_ready)
    monkeypatch.setattr(main, "StreamConsumer", CrashingConsumer)

    # Without the exit, `serve` never returns and this times out instead.
    with pytest.raises(RuntimeError, match="the consumer died"):
        await asyncio.wait_for(main.run(_settings()), timeout=5)

    assert servers[0].should_exit
