"""Asset service configuration (Conventions §8, design doc 04 §6)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    postgres_dsn: str

    # R1: `require_user` checks the token denylist there (Conventions §5.2).
    redis_cache_url: str

    # Asset produces thumbnail jobs onto R3. It has no real-time need.
    redis_streams_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_internal_audience: str = "collabhub-internal"
    auth_jwks_url: str

    # Empty installs no CORS middleware at all (Conventions §5.6). In Compose the
    # SPA is another origin and calls `upload-url` and `confirm` directly.
    cors_allowed_origins: list[str] = []

    # S3-compatible, and only the S3 subset Garage implements — these values
    # point at Azure Blob just as happily.
    object_store_endpoint: str
    # What a browser can reach. URLs are signed for this host, because the host
    # is part of the signature; `object_store_endpoint` is for the service's own
    # calls (HEAD) and is often a cluster-internal name.
    object_store_public_endpoint: str
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_bucket: str = "collabhub-assets"
    object_store_presign_ttl_seconds: int = 900

    # 50 MiB. The allow-list of content types is deliberately not a setting: it
    # is the whole mitigation for register D15 (no virus scan), and not a value
    # to widen in an env file. See `asset.rules.ATTACHMENT_CONTENT_TYPES`.
    asset_max_upload_bytes: int = 52_428_800

    otel_exporter_otlp_endpoint: str | None = None
