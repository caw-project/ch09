"""`python -m asset.openapi` — print this service's OpenAPI document.

The SPA generates its types from this (register D23), so the schema has to be
obtainable without a database, a Redis or a Garage: the app is built from
placeholder settings, and `create_app` only *describes* its dependencies —
nothing connects until a request arrives.
"""

from __future__ import annotations

import json

from asset.main import create_app
from asset.settings import Settings

#: Syntactically valid and deliberately unreachable. Nothing dials them.
_PLACEHOLDERS = {
    "postgres_dsn": "postgresql+asyncpg://openapi/openapi",
    "redis_cache_url": "redis://openapi/0",
    "redis_streams_url": "redis://openapi/0",
    "auth_issuer": "https://auth.invalid",
    "auth_jwks_url": "https://auth.invalid/.well-known/jwks.json",
    "object_store_endpoint": "http://openapi.invalid:3900",
    "object_store_public_endpoint": "http://openapi.invalid:3900",
}


def document() -> dict:
    return create_app(Settings(**_PLACEHOLDERS)).openapi()


def main() -> None:
    print(json.dumps(document(), indent=2, sort_keys=True))  # noqa: T201 — this is the output


if __name__ == "__main__":
    main()
