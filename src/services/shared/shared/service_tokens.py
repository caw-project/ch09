"""A service's own access token, fetched from Auth and reused until it is nearly spent.

Conventions §5.5: a service calling another service's internal API holds a
`client_credentials` token and caches it until shortly before expiry. Fetching
one per call would make Auth the hot path of every send; keeping one past its
expiry would make every send fail until someone noticed.

**One fetch in flight at a time.** Callers that arrive while a grant is
outstanding wait for it rather than starting their own, so a burst of sends
after a restart is one request to Auth.

**A failure is never cached.** A refused or unreachable grant raises
`ServiceTokenUnavailableError` and the next call tries again; the caller turns
that into its own "dependency down" answer.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx


class ServiceTokenUnavailableError(Exception):
    """Auth could not give this service a token: unreachable, refused or malformed."""


class ServiceTokenSource:
    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        http: httpx.AsyncClient,
        margin_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._margin = margin_seconds
        self._clock = clock
        self._token: str | None = None
        self._refresh_at = 0.0
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        return self._token is not None and self._clock() < self._refresh_at

    async def token(self) -> str:
        if self._token is not None and self._fresh():
            return self._token
        async with self._lock:
            # Whoever held the lock before us may have fetched while we waited.
            if self._token is not None and self._fresh():
                return self._token
            return await self._fetch()

    def invalidate(self) -> None:
        """Forget the cached token: the audience said it is no good (a 401)."""
        self._token = None

    async def _fetch(self) -> str:
        try:
            response = await self._http.post(
                self._token_url,
                json={
                    "grantType": "client_credentials",
                    "clientId": self._client_id,
                    "clientSecret": self._client_secret,
                },
            )
            response.raise_for_status()
            body = response.json()
            token = str(body["accessToken"])
            expires_in = float(body["expiresIn"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ServiceTokenUnavailableError("The service token could not be obtained.") from exc

        self._token = token
        self._refresh_at = self._clock() + expires_in - self._margin
        return token
