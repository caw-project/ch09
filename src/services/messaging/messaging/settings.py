"""Messaging service configuration (Conventions §8, design doc 02 §6)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    postgres_dsn: str

    # Messaging is the one service that uses all three Redis instances, and they
    # are not interchangeable: R1 caches membership, R2 is the Socket.IO
    # backplane, R3 carries index jobs.
    redis_cache_url: str
    redis_realtime_url: str
    redis_streams_url: str

    # Read-only: the Worker writes the `messages` index, this service queries it
    # for `GET /search/messages`. Not a readiness dependency — an Elasticsearch
    # outage degrades search and must not take chat out of rotation.
    elasticsearch_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_internal_audience: str = "collabhub-internal"
    auth_jwks_url: str

    # Empty installs no CORS middleware at all (Conventions §5.6). Locally the
    # SPA is a separate origin, so this is set; behind one ingress it is not.
    cors_allowed_origins: list[str] = []

    messaging_max_body_chars: int = 8000
    messaging_max_attachments: int = 10

    # Asset's internal API, and the Auth endpoint that mints the service token
    # Messaging calls it with (Conventions §5.5). Mirrors the Worker's
    # `WORKER_SERVICE_CLIENT_*`: empty means no attachment can be claimed, and a
    # send that names one answers 503 rather than the service failing to start.
    service_token_url: str = ""
    asset_internal_url: str = ""
    messaging_service_client_id: str = "messaging"
    messaging_service_client_secret: str = ""

    # Engine.IO heartbeat. python-socketio's own defaults: a dropped connection
    # is noticed within interval + timeout, ~45s. Only the BDD stack shortens
    # them, so a "connection drops" journey does not wait that long.
    messaging_socket_ping_interval_seconds: float = 25
    messaging_socket_ping_timeout_seconds: float = 20

    otel_exporter_otlp_endpoint: str | None = None
