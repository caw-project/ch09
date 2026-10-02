"""Fixtures for the Asset integration tests: real Postgres, real Redis, real Garage.

The Garage is `testkit.garage`'s, bootstrapped by the real script, so a presigned
URL minted here is PUT to and fetched from the store the service will meet. The
Asset code (`asset.*`) is imported **inside the fixtures**, so each test file
fails on its own import at red rather than the whole directory failing to collect.
Tokens come from `testkit.tokens`, as in Messaging's conftest.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from testkit.apps import asgi_client
from testkit.containers import RedisRole, RedisServer
from testkit.databases import PostgresServer, service_database
from testkit.db import truncate
from testkit.garage import GarageServer
from testkit.tokens import ISSUER, USER_AUDIENCE, Tokens

TABLES = ("assets",)

#: A valid 1x1 PNG, so the bytes under test are a real image and not a placeholder.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


@pytest.fixture(scope="session")
def postgres_dsn(postgres_server: PostgresServer) -> str:
    from asset.migrations import upgrade_to_head

    return service_database(postgres_server, "asset", upgrade_to_head)


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    await truncate(engine, TABLES)
    yield engine
    await engine.dispose()


def build_settings(postgres_dsn: str, redis: RedisServer, garage: GarageServer, **overrides: Any):
    from asset.settings import Settings

    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis.url(RedisRole.CACHE),
        "redis_streams_url": redis.url(RedisRole.STREAMS),
        "auth_issuer": ISSUER,
        "auth_audience": USER_AUDIENCE,
        "auth_jwks_url": "https://auth.test/.well-known/jwks.json",
        "object_store_endpoint": garage.endpoint,
        # The test is on the host, so the browser-facing and internal endpoints coincide.
        "object_store_public_endpoint": garage.endpoint,
        "object_store_access_key": garage.access_key,
        "object_store_secret_key": garage.secret_key,
        "object_store_bucket": garage.bucket,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
async def client(
    postgres_dsn: str,
    redis_server: RedisServer,
    garage_server: GarageServer,
    tokens: Tokens,
    engine,
) -> AsyncIterator[httpx.AsyncClient]:
    """The Asset app on an ASGI transport, against the real containers."""
    from asset.main import create_app

    settings = build_settings(postgres_dsn, redis_server, garage_server)
    async with asgi_client(create_app(settings, key_source=tokens.key_source())) as c:
        yield c


@pytest.fixture
def client_for(
    postgres_dsn: str,
    redis_server: RedisServer,
    garage_server: GarageServer,
    tokens: Tokens,
    engine,
) -> Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]:
    """A client against an app built with one or two settings changed."""
    from asset.main import create_app

    @asynccontextmanager
    async def build(**overrides: Any) -> AsyncIterator[httpx.AsyncClient]:
        settings = build_settings(postgres_dsn, redis_server, garage_server, **overrides)
        async with asgi_client(create_app(settings, key_source=tokens.key_source())) as c:
            yield c

    return build


@pytest.fixture
def ada(tokens: Tokens) -> dict[str, str]:
    return tokens.header()


@pytest.fixture
def grace(tokens: Tokens) -> dict[str, str]:
    return tokens.header(user_id=tokens.GRACE, name="Grace Hopper", email="grace@collabhub.dev")


@pytest.fixture
def other_workspace(tokens: Tokens) -> dict[str, str]:
    """Ada's own user id, in another workspace: only the workspace differs."""
    return tokens.header(workspace_id=tokens.OTHER_WORKSPACE)


@pytest.fixture
def messaging(tokens: Tokens) -> dict[str, str]:
    """Messaging's service token, with both scopes it is granted."""
    token = tokens.service("messaging", scopes=("assets:claim", "assets:download"))
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class Reserved:
    """What `reserve` and `upload` return: the handshake's answers, side by side."""

    id: str
    upload: dict[str, Any]
    size: int
    confirmed: dict[str, Any] | None = None


@pytest.fixture
def reserve(client: httpx.AsyncClient, ada: dict[str, str]) -> Callable[..., Any]:
    """Reserve an asset through the public route, and optionally PUT and confirm it.

    Everything goes through the real routes and the real store — nothing is
    inserted behind the service's back — so an asset is `ready` only because the
    whole handshake made it so.
    """

    async def make(
        *,
        headers: dict[str, str] | None = None,
        content: bytes = PNG,
        content_type: str = "image/png",
        file_name: str = "diagram.png",
        declared: int | None = None,
        put: bool = False,
        confirm: bool = False,
    ) -> Reserved:
        headers = headers or ada
        response = await client.post(
            "/api/v1/assets/upload-url",
            json={
                "fileName": file_name,
                "contentType": content_type,
                "sizeBytes": len(content) if declared is None else declared,
                "purpose": "attachment",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        upload = response.json()
        if put:
            async with httpx.AsyncClient() as garage:
                stored = await garage.put(
                    upload["uploadUrl"], content=content, headers=upload["headers"]
                )
            assert stored.status_code == 200, stored.text
        confirmed = None
        if confirm:
            result = await client.post(
                f"/api/v1/assets/{upload['assetId']}/confirm", headers=headers
            )
            assert result.status_code == 200, result.text
            confirmed = result.json()
        size = len(content) if declared is None else declared
        return Reserved(id=upload["assetId"], upload=upload, size=size, confirmed=confirmed)

    return make


@pytest.fixture
def a_ready_asset(reserve: Callable[..., Any]) -> Callable[..., Any]:
    """A `ready` asset: reserved, PUT to Garage and confirmed."""

    async def make(**kwargs: Any) -> Reserved:
        reserved = await reserve(put=True, confirm=True, **kwargs)
        assert reserved.confirmed is not None
        assert reserved.confirmed["status"] == "ready", reserved.confirmed
        return reserved

    return make


@pytest.fixture
def an_object_key() -> Callable[[], str]:
    return lambda: f"{uuid.uuid4()}/attachment/{uuid.uuid4()}"
