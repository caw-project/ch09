"""Messaging's client for Asset's internal API — claim, and download URL.

Messaging is Asset's only caller. It authenticates with a service token it keeps
in a `ServiceTokenSource` (Conventions §5.5), and turns every answer Asset can
give into one of four outcomes the routes understand:

* a result;
* `ClaimRefusedError` — Asset said no to some asset, with a reason for each;
* `AttachmentNotFoundError` — a download URL for something that is not there;
* `AssetUnavailableError` — **anything else**: Asset down, slow, 5xx, a token
  that cannot be had, a body that is not the contract. Messaging's routes answer
  503 and save nothing, so no failure mode here can leave a half-sent message.

**A 401 is retried once with a fresh token.** A rotated signing key or a token
that expired between the cache check and the call would otherwise fail every
send until the cache turned over. A second 401 is `AssetUnavailableError`:
one refetch, then give up, never a loop.

No file name or URL is logged: a file name is user content.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import httpx
from pydantic import ValidationError

from contracts.assets import (
    AttachmentMeta,
    ClaimRefusal,
    ClaimRequest,
    ClaimResponse,
    DownloadUrlRequest,
    DownloadUrlResponse,
)
from shared import ServiceTokenSource, ServiceTokenUnavailableError

_CLAIM = "/api/v1/internal/assets/claim"


class AssetUnavailableError(Exception):
    """Asset could not be asked, or could not answer. Nothing was changed."""


class ClaimRefusedError(Exception):
    """Asset refused the claim. `refusals` maps each refused asset to its reason."""

    def __init__(self, refusals: dict[uuid.UUID, ClaimRefusal]) -> None:
        super().__init__("The claim was refused.")
        self.refusals = refusals


class AttachmentNotFoundError(Exception):
    """Asset has no such asset on this message."""


class AssetClient:
    def __init__(
        self, *, base_url: str, tokens: ServiceTokenSource, http: httpx.AsyncClient
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._tokens = tokens
        self._http = http

    async def _post(self, path: str, body: dict) -> httpx.Response:
        """POST with a bearer token, refetching the token once on a 401."""
        for attempt in (1, 2):
            try:
                token = await self._tokens.token()
            except ServiceTokenUnavailableError as exc:
                raise AssetUnavailableError from exc
            try:
                response = await self._http.post(
                    f"{self._base_url}{path}",
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise AssetUnavailableError from exc
            if response.status_code != httpx.codes.UNAUTHORIZED:
                return response
            if attempt == 1:
                self._tokens.invalidate()
        raise AssetUnavailableError

    async def claim(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        message_id: uuid.UUID,
        asset_ids: Sequence[uuid.UUID],
    ) -> list[AttachmentMeta]:
        """Put these assets on this message, all or none; metadata in `asset_ids` order."""
        request = ClaimRequest(
            workspace_id=workspace_id,
            user_id=user_id,
            message_id=message_id,
            asset_ids=list(asset_ids),
        )
        response = await self._post(_CLAIM, request.model_dump(mode="json", by_alias=True))

        if response.status_code == httpx.codes.CONFLICT:
            raise ClaimRefusedError(_refusals(response))
        if response.status_code != httpx.codes.OK:
            raise AssetUnavailableError
        try:
            return ClaimResponse.model_validate(response.json()).items
        except (ValueError, ValidationError) as exc:
            raise AssetUnavailableError from exc

    async def download_url(
        self, *, workspace_id: uuid.UUID, message_id: uuid.UUID, asset_id: uuid.UUID
    ) -> DownloadUrlResponse:
        request = DownloadUrlRequest(workspace_id=workspace_id, message_id=message_id)
        response = await self._post(
            f"/api/v1/internal/assets/{asset_id}/download-url",
            request.model_dump(mode="json", by_alias=True),
        )

        if response.status_code == httpx.codes.NOT_FOUND:
            raise AttachmentNotFoundError
        if response.status_code != httpx.codes.OK:
            raise AssetUnavailableError
        try:
            return DownloadUrlResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise AssetUnavailableError from exc


def _refusals(response: httpx.Response) -> dict[uuid.UUID, ClaimRefusal]:
    """The 409's `errors` (`{assetId: [reason]}`), or `AssetUnavailableError` if it isn't one."""
    try:
        errors = response.json()["errors"]
        return {
            uuid.UUID(asset_id): ClaimRefusal(reasons[0]) for asset_id, reasons in errors.items()
        }
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AssetUnavailableError from exc
