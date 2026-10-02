"""Cross-cutting helpers shared by every CollabHub backend service.

What lives here is the platform's shared contract, implemented once so five
services cannot drift: RFC 7807 Problem Details, UUID v7 keys, JWKS-backed token
verification with `require_user` / `require_service`, the Redis token denylist,
the health router, the job envelope and queue (Conventions §7), which
arrived with message search, and `ServiceTokenSource`, a service's own cached
client-credentials token (Conventions §5.5), which arrived with attachments.

Still to arrive with the services that need them: structlog + OpenTelemetry
setup. (The `ObjectStore` protocol lives in Asset, the only service that
speaks to object storage.)
See docs/design/00-platform-conventions.md.
"""

from shared.cors import install_cors, socket_allowed_origins
from shared.denylist import Denylist, TokenState
from shared.health import HealthCheck, build_health_router, http_check, postgres_check, redis_check
from shared.ids import uuid7
from shared.jobs import JOB_DATA_FIELD, JobEnvelope, JobQueue
from shared.keys import (
    JwksClient,
    KeySource,
    KeySourceUnavailableError,
    StaticKeySource,
    UnknownKeyError,
    jwks_document,
)
from shared.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CursorPart,
    Page,
    PageParams,
    PageRequest,
    build_page,
    decode_cursor,
    encode_cursor,
    page_request,
    page_request_for,
)
from shared.problems import (
    PROBLEM_MEDIA_TYPE,
    ProblemException,
    install_problem_handlers,
    problem_body,
    problem_response,
    trace_id,
)
from shared.security import (
    SecurityConfig,
    SecurityContext,
    ServicePrincipal,
    UserPrincipal,
    install_security,
    require_service,
    require_user,
    require_user_sensitive,
    verify_user_token,
)
from shared.service_tokens import ServiceTokenSource, ServiceTokenUnavailableError

__all__ = [
    "DEFAULT_LIMIT",
    "JOB_DATA_FIELD",
    "MAX_LIMIT",
    "PROBLEM_MEDIA_TYPE",
    "CursorPart",
    "Denylist",
    "HealthCheck",
    "JobEnvelope",
    "JobQueue",
    "JwksClient",
    "KeySource",
    "KeySourceUnavailableError",
    "Page",
    "PageParams",
    "PageRequest",
    "ProblemException",
    "SecurityConfig",
    "SecurityContext",
    "ServicePrincipal",
    "ServiceTokenSource",
    "ServiceTokenUnavailableError",
    "StaticKeySource",
    "TokenState",
    "UnknownKeyError",
    "UserPrincipal",
    "build_health_router",
    "build_page",
    "decode_cursor",
    "encode_cursor",
    "http_check",
    "install_cors",
    "install_problem_handlers",
    "install_security",
    "jwks_document",
    "page_request",
    "page_request_for",
    "postgres_check",
    "problem_body",
    "problem_response",
    "redis_check",
    "require_service",
    "require_user",
    "require_user_sensitive",
    "socket_allowed_origins",
    "trace_id",
    "uuid7",
    "verify_user_token",
]
