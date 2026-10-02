"""Fixtures for the Messaging integration tests.

Real Postgres and Redis, not mocks (Conventions §11) — a keyset cursor, a
partial unique index and a case-folded collision are all things only a real
database can tell you the truth about. The servers are the session's shared
ones from `testkit.containers` (register D34): Messaging gets its own database,
`messaging`, and — as the one service that uses all three Redis roles — a
separate index for each.

Tokens come from `testkit.tokens` rather than from Auth. Messaging verifies
signatures against a JWKS it does not own, so the only thing a real Auth would
add is a second container and a slower suite; what matters is that the token is
a genuine RS256 JWT with the right claims, and a local key gives that.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from messaging.main import build_asgi_app, create_app
from messaging.migrations import upgrade_to_head
from messaging.settings import Settings
from testkit.apps import asgi_client, serve
from testkit.containers import RedisRole, RedisServer
from testkit.databases import PostgresServer, service_database
from testkit.db import truncate
from testkit.tokens import ISSUER, USER_AUDIENCE, Tokens

#: Child tables first — `message_reactions` references `messages`, and `messages`
#: and `channel_members` both reference `channels`. `CASCADE` would reach them
#: anyway; being explicit is what stops the next person wondering whether the
#: order matters.
#: `message_attachments` is not listed: it references `messages`, and `truncate`
#: runs `CASCADE`, so emptying `messages` empties it. Listing it would make every
#: test in this directory error until the table exists, not only the new ones.
TABLES = ("message_reactions", "messages", "channel_reads", "channel_members", "channels")


@pytest.fixture(scope="session")
def postgres_dsn(postgres_server: PostgresServer) -> str:
    return service_database(postgres_server, "messaging", upgrade_to_head)


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    await truncate(engine, TABLES)
    yield engine
    await engine.dispose()


def build_settings(postgres_dsn: str, redis: RedisServer, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis.url(RedisRole.CACHE),
        "redis_realtime_url": redis.url(RedisRole.REALTIME),
        "redis_streams_url": redis.url(RedisRole.STREAMS),
        # Unreachable unless a test asks for the real one: only the search tests
        # start Elasticsearch, and they pass `elasticsearch_url` to `client_for`.
        "elasticsearch_url": "http://elasticsearch.invalid:9200",
        "auth_issuer": ISSUER,
        "auth_audience": USER_AUDIENCE,
        "auth_jwks_url": "https://auth.test/.well-known/jwks.json",
        # Unreachable unless a test points the app at `asset_stub`. Settings take
        # extra keys silently until the real ones exist, so every test that sends
        # no attachment builds the app as before.
        "asset_internal_url": "http://asset.invalid",
        "service_token_url": "http://auth.invalid/token",
        "messaging_service_client_secret": "test-secret",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_server: RedisServer) -> Settings:
    return build_settings(postgres_dsn, redis_server)


@pytest.fixture
async def client(
    app_settings: Settings, tokens: Tokens, engine
) -> AsyncIterator[httpx.AsyncClient]:
    """The Messaging app on an ASGI transport, against the real containers."""
    async with asgi_client(create_app(app_settings, key_source=tokens.key_source())) as c:
        yield c


@pytest.fixture
def client_for(
    postgres_dsn: str, redis_server: RedisServer, tokens: Tokens, engine
) -> Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]:
    """A client against an app built with one or two settings changed.

    For the rules that *are* the configuration — the body limit — and for
    pointing one app at a real or an unreachable store: Elasticsearch for the
    search tests, a dead R3 for the fire-and-forget producer.

    A fixture rather than an import, deliberately. Every service in this repo
    has a `tests` package with no `__init__.py`, so `tests` is one namespace
    package spanning all of them; ruff bans `from tests.conftest import
    build_settings` outright (TID251) rather than let it bind to whichever
    service sorts first. Shared helpers go in `testkit`; a service's own go
    through fixtures like this one.
    """

    @asynccontextmanager
    async def build(**overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
        settings = build_settings(postgres_dsn, redis_server, **overrides)
        async with asgi_client(create_app(settings, key_source=tokens.key_source())) as c:
            yield c

    return build


@pytest.fixture
async def realtime_url(app_settings: Settings, tokens: Tokens, engine) -> AsyncIterator[str]:
    """A real uvicorn serving the Socket.IO app — see `testkit.apps.serve` for why.

    In `conftest.py` rather than in a test module because the inbound-event
    tests need the same server, and neither test module owns the other's
    fixtures.
    """
    async with serve(build_asgi_app(app_settings, key_source=tokens.key_source())) as url:
        yield url


@pytest.fixture
def realtime_url_for(
    postgres_dsn: str, redis_server: RedisServer, tokens: Tokens, engine
) -> Callable[..., AbstractAsyncContextManager[str]]:
    """`client_for`'s shape for the socket: a served app with settings changed.

    `realtime_url` builds from `app_settings` and cannot be pointed at a stub
    Asset; the attachment tests need the socket and REST both to meet it.
    """

    @asynccontextmanager
    async def build(**overrides: Any) -> AsyncIterator[str]:
        settings = build_settings(postgres_dsn, redis_server, **overrides)
        async with serve(build_asgi_app(settings, key_source=tokens.key_source())) as url:
            yield url

    return build


class AssetStub:
    """Asset's internal API as Messaging meets it, with the calls it received.

    Built from `contracts.assets` — the same models the real service answers
    with — so a drifted field name fails here and in Asset's own integration
    tests alike. `ready()` registers an asset the stub will claim; `refuse`
    scripts a refusal for one; `down` makes both routes answer 503.
    """

    def __init__(self) -> None:
        self.url = ""
        self.token_calls = 0
        self.claims: list[dict[str, Any]] = []
        self.downloads: list[dict[str, Any]] = []
        self.down = False
        self.metadata: dict[str, dict[str, Any]] = {}
        self.refusals: dict[str, str] = {}
        #: asset id -> the message that claimed it, as the real service records it
        self.claimed_by: dict[str, str] = {}

    def refused(self, ids: list[str], message_id: str) -> dict[str, list[str]]:
        """The 409's `errors`: scripted refusals, unknown ids, and ids on another message."""
        errors: dict[str, list[str]] = {}
        for asset_id in ids:
            if asset_id in self.refusals:
                errors[asset_id] = [self.refusals[asset_id]]
            elif asset_id not in self.metadata:
                errors[asset_id] = ["not-found"]
            elif self.claimed_by.get(asset_id, message_id) != message_id:
                errors[asset_id] = ["already-attached"]
        return errors

    @property
    def token_url(self) -> str:
        return f"{self.url}/token"

    def ready(
        self, file_name: str = "diagram.png", content_type: str = "image/png", size: int = 1234
    ) -> str:
        """Register an asset this stub will claim; returns its id."""
        import uuid

        asset_id = str(uuid.uuid4())
        self.metadata[asset_id] = {
            "assetId": asset_id,
            "fileName": file_name,
            "contentType": content_type,
            "sizeBytes": size,
        }
        return asset_id


def _asset_stub_app(stub: AssetStub):
    from datetime import UTC, datetime, timedelta

    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from contracts.assets import (
        AttachmentMeta,
        ClaimRequest,
        ClaimResponse,
        DownloadUrlRequest,
        DownloadUrlResponse,
    )

    def problem(status: int, **extra: Any) -> JSONResponse:
        return JSONResponse(
            {"title": "stub", "status": status, **extra},
            status_code=status,
            media_type="application/problem+json",
        )

    async def token(request: Request) -> JSONResponse:
        stub.token_calls += 1
        return JSONResponse(
            {
                "accessToken": f"stub-token-{stub.token_calls}",
                "tokenType": "Bearer",
                "expiresIn": 900,
            }
        )

    async def claim(request: Request) -> JSONResponse:
        body = ClaimRequest.model_validate(await request.json())
        stub.claims.append(
            {
                "workspaceId": str(body.workspace_id),
                "userId": str(body.user_id),
                "messageId": str(body.message_id),
                "assetIds": [str(i) for i in body.asset_ids],
                "authorization": request.headers.get("authorization"),
            }
        )
        if stub.down:
            return problem(503)
        ids = [str(i) for i in body.asset_ids]
        errors = stub.refused(ids, str(body.message_id))
        if errors:
            return problem(409, type="https://collabhub.dev/problems/conflict", errors=errors)
        for asset_id in ids:
            stub.claimed_by[asset_id] = str(body.message_id)
        items = [AttachmentMeta.model_validate(stub.metadata[i]) for i in ids]
        return JSONResponse(ClaimResponse(items=items).model_dump(by_alias=True, mode="json"))

    async def download(request: Request) -> JSONResponse:
        asset_id = request.path_params["asset_id"]
        body = DownloadUrlRequest.model_validate(await request.json())
        stub.downloads.append(
            {
                "assetId": asset_id,
                "workspaceId": str(body.workspace_id),
                "messageId": str(body.message_id),
            }
        )
        if stub.down:
            return problem(503)
        if stub.claimed_by.get(asset_id) != str(body.message_id):
            return problem(404)
        answer = DownloadUrlResponse(
            url=f"http://garage.test/{asset_id}?sig=stub",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        return JSONResponse(answer.model_dump(by_alias=True, mode="json"))

    return Starlette(
        routes=[
            Route("/token", token, methods=["POST"]),
            Route("/api/v1/internal/assets/claim", claim, methods=["POST"]),
            Route("/api/v1/internal/assets/{asset_id}/download-url", download, methods=["POST"]),
        ]
    )


@pytest.fixture
async def asset_stub() -> AsyncIterator[AssetStub]:
    """A served stub of Asset's internal API and Auth's token endpoint.

    `contracts.assets` is imported **inside** `_asset_stub_app`, so at red only
    the tests that ask for this fixture error, with `No module named
    'contracts.assets'`; the ones that need no stub run and show their own red.
    """
    stub = AssetStub()
    async with serve(_asset_stub_app(stub)) as url:
        stub.url = url
        yield stub


@pytest.fixture
def ada(tokens: Tokens) -> dict[str, str]:
    return tokens.header()


@pytest.fixture
def grace(tokens: Tokens) -> dict[str, str]:
    return tokens.header(user_id=tokens.GRACE, name="Grace Hopper", email="grace@collabhub.dev")
