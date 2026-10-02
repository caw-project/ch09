"""Asset service entry point.

`create_app` builds everything from a `Settings` object and hangs it on
`app.state`, so a test can point an app at a throwaway database and a throwaway
Garage without patching module globals. Like Messaging, Asset verifies tokens
against Auth's published JWKS (Conventions §5.1); tests pass a `StaticKeySource`.

Two routers: the public upload handshake (`routers/assets.py`) and the internal
claim and download-url routes Messaging calls (`routers/internal.py`).

Readiness covers Postgres and R3 only. Object storage is not probed, for the same
reason Messaging leaves Elasticsearch out: a Garage blip makes `confirm` answer
503 rather than taking Asset out of rotation, and `/health/ready` going red would
stop every other route working too.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from asset.db import build_engine, build_sessions
from asset.object_store import S3ObjectStore
from asset.routers import assets as asset_routes
from asset.routers import internal as internal_routes
from asset.settings import Settings
from shared import (
    Denylist,
    JwksClient,
    KeySource,
    SecurityConfig,
    build_health_router,
    install_cors,
    install_problem_handlers,
    install_security,
    postgres_check,
    redis_check,
)


def create_app(settings: Settings, *, key_source: KeySource | None = None) -> FastAPI:
    """Build the app. `key_source` defaults to Auth's published JWKS."""
    engine = build_engine(settings.postgres_dsn)
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    keys = key_source or JwksClient(settings.auth_jwks_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        # Only close what this function opened; an injected source is the
        # caller's to dispose of.
        if key_source is None and isinstance(keys, JwksClient):
            await keys.aclose()
        await engine.dispose()
        await redis_client.aclose()

    app = FastAPI(title="CollabHub Asset", version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.sessions = build_sessions(engine)
    app.state.denylist = Denylist(redis_client)
    app.state.store = S3ObjectStore(
        endpoint=settings.object_store_endpoint,
        public_endpoint=settings.object_store_public_endpoint,
        access_key=settings.object_store_access_key,
        secret_key=settings.object_store_secret_key,
        bucket=settings.object_store_bucket,
        presign_ttl_seconds=settings.object_store_presign_ttl_seconds,
    )

    install_cors(app, origins=settings.cors_allowed_origins)
    install_problem_handlers(app)
    install_security(
        app,
        key_source=keys,
        config=SecurityConfig(
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            internal_audience=settings.auth_internal_audience,
        ),
        denylist=app.state.denylist,
    )

    app.include_router(
        build_health_router(
            {
                "postgres": postgres_check(settings.postgres_dsn),
                "redis-streams": redis_check(settings.redis_streams_url),
            }
        )
    )
    app.include_router(asset_routes.router)
    app.include_router(internal_routes.router)
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn asset.main:app_factory --factory`."""
    return create_app(Settings())
