"""`worker.main.run` drains on SIGTERM (design doc 05 §2, Conventions §10).

SIGTERM stops Uvicorn, which sets `stop`; the consumer finishes the entry in hand
and returns, and anything it read but had not started stays pending in Redis for
the next consumer to reclaim.

The real `run`: a real Uvicorn on an ephemeral port, a real R3 stream, and a real
SIGTERM raised in this process. Elasticsearch is not started — the index step
is a no-op and the stream's handler is a stand-in that holds its job until the
test lets go, as the handlers in `test_consumer.py` are.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Iterator

import pytest

from contracts import JOBS_INDEX
from testkit.containers import RedisRole, RedisServer
from worker import main
from worker.settings import Settings

JOB = "test.job"


@pytest.fixture(autouse=True)
def _restore_sigterm() -> Iterator[None]:
    """`run` installs a SIGTERM handler bound to its own loop and never removes it."""
    previous = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, previous)


async def test_sigterm_finishes_the_job_in_hand_and_starts_no_other(
    monkeypatch: pytest.MonkeyPatch, redis_server: RedisServer, jobs
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    handled = []
    finished = []

    async def holds_its_job(envelope) -> None:
        handled.append(envelope.job_id)
        started.set()
        await release.wait()
        finished.append(envelope.job_id)

    async def index_ready(_es: object) -> None:
        return None

    monkeypatch.setattr(main, "ensure_messages_index", index_ready)
    monkeypatch.setattr(main, "build_handlers", lambda _es: {JOBS_INDEX: {JOB: holds_its_job}})
    monkeypatch.setattr(main, "HEALTH_PORT", 0)

    first = await jobs.enqueue(JOB, {"n": 1})
    await jobs.enqueue(JOB, {"n": 2})
    settings = Settings(
        redis_streams_url=redis_server.url(RedisRole.STREAMS),
        elasticsearch_url="http://127.0.0.1:9",
        object_store_endpoint="http://127.0.0.1:9",
        worker_streams=JOBS_INDEX,
    )

    worker = asyncio.create_task(main.run(settings))
    try:
        await asyncio.wait_for(started.wait(), timeout=15)
        signal.raise_signal(signal.SIGTERM)

        # Uvicorn stops, and `run` has to wait for the job in hand.
        await asyncio.sleep(1)
        assert not worker.done(), "run returned with a job still in hand"

        release.set()
        await asyncio.wait_for(worker, timeout=15)
    finally:
        release.set()
        if not worker.done():
            worker.cancel()

    assert finished == [first.job_id]
    assert handled == [first.job_id], "a job was started after SIGTERM"
    # The first was acked and deleted; the second was read, never started, and
    # is still pending for whichever consumer reclaims it.
    assert await jobs.client.xlen(jobs.stream) == 1
    assert await jobs.pending() == 1
