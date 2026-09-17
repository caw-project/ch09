"""Cross-origin access for the SPA, configured once for every service.

Locally the SPA and the services are separate origins — the browser loads the
app from `localhost:5173` and it calls `localhost:8001`, `:8002` and so on — so
without this every request from the app is blocked before it is sent.

Deployed, they are usually one origin behind a single ingress and none of this
is needed. That is why the default is **no origins and no middleware at all**:
an empty `CORS_ALLOWED_ORIGINS` installs nothing, so a service that does not
need cross-origin access does not quietly advertise that it allows it.

Two choices worth stating:

* **Origins are listed, never `*`.** A wildcard is easy and means any page on the
  internet can call these APIs from a victim's browser. The list is short and
  lives in configuration. With credentials allowed, browsers reject a wildcard
  outright anyway — which is the right instinct made mandatory.
* **Credentials are allowed**, because the refresh token is an `HttpOnly` cookie
  (register D22) and a cross-origin `fetch` will not attach it otherwise. Access
  tokens are still a Bearer header (Conventions §5.1); the cookie is only ever
  sent to `/api/v1/auth`, so the other services receive no ambient credential at
  all even though they permit them here.

Allowing credentials is what makes CSRF a question, and it is answered by the
cookie rather than here: `SameSite=Strict` means no cross-site request carries
the refresh cookie, so there is nothing for a forged request to ride on. That
also means the SPA and the API must stay **same-site** — see `auth/cookies.py`,
which owns that constraint.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# Only what the platform actually uses. `traceparent` is on the list because
# browser requests carry it for distributed tracing (Conventions §9), and a
# header the browser sends but the preflight does not allow fails the request.
ALLOWED_HEADERS = ["Authorization", "Content-Type", "traceparent", "X-Correlation-Id"]
ALLOWED_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]


def install_cors(app: FastAPI, *, origins: list[str]) -> None:
    """Allow the configured origins to call this service from a browser.

    A no-op when no origins are configured, which is the deployed case.
    """
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        max_age=600,
    )


def socket_allowed_origins(
    origins: list[str],
) -> list[str] | Callable[[str, dict[str, Any]], bool]:
    """engine.io's own origin check for the `/messaging` socket — separate from,
    and stricter than, `install_cors`'s middleware.

    Configured origins come back unchanged: engine.io accepts a list exactly as
    `CORSMiddleware` does. The interesting case is the deployed one, where
    Conventions §5.6 says an empty `CORS_ALLOWED_ORIGINS` means "same origin",
    not "allow nothing" — but engine.io's own idea of "same origin" is built
    from `X-Forwarded-Proto`, and a proxy reports that header verbatim from the
    request it received. Traefik's WebSocket upgrades carry
    `X-Forwarded-Proto: ws`, so engine.io's default check compares the browser's
    `Origin: http://host` against a `ws://host` it built for itself, and refuses
    every handshake behind the proxy.

    So an empty list returns a predicate instead of `None`: it rebuilds the
    origin the same way, but treats `ws`/`wss` as naming the same origin as
    `http`/`https` — a WebSocket scheme is not a different site, only the
    upgraded form of the one the browser already trusted. Everything else is
    exact: no wildcard, no port or scheme leniency beyond that one mapping, and
    a chain of forwarded hosts uses only the first — the client-facing hop.
    """
    if origins:
        return origins

    def same_origin(origin: str, environ: dict[str, Any]) -> bool:
        forwarded_host = environ.get("HTTP_X_FORWARDED_HOST")
        host = (
            forwarded_host.split(",")[0].strip() if forwarded_host else environ.get("HTTP_HOST", "")
        )

        forwarded_proto = environ.get("HTTP_X_FORWARDED_PROTO")
        scheme = (
            forwarded_proto.split(",")[0].strip()
            if forwarded_proto
            else environ.get("wsgi.url_scheme", "http")
        )
        scheme = {"ws": "http", "wss": "https"}.get(scheme, scheme)

        return origin == f"{scheme}://{host}"

    return same_origin
