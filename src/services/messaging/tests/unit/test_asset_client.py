"""`AssetClient` — how Asset's internal answers map to Messaging's own errors.

An httpx `MockTransport` plays both Asset and Auth's token endpoint, so the
client and the real `ServiceTokenSource` run unmodified and no socket opens. The
claim's *wire shape* is `contracts.assets`; that Asset's real routes honour it is
proven in `asset/tests/integration/test_internal.py`.

`claim` and `download_url` take keyword arguments named for the contract's
fields: `workspace_id`, `user_id`, `message_id`, `asset_ids` / `asset_id`.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from messaging.assets import (
    AssetClient,
    AssetUnavailableError,
    AttachmentNotFoundError,
    ClaimRefusedError,
)
from shared.service_tokens import ServiceTokenSource

WORKSPACE = uuid.uuid4()
USER = uuid.uuid4()
MESSAGE = uuid.uuid4()
ASSET = uuid.uuid4()
OTHER = uuid.uuid4()


class Backend:
    """Asset and Auth in one handler: `asset` is a queue of scripted answers."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.answers = list(answers)
        self.token_calls = 0
        self.asset_requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "auth.test":
            self.token_calls += 1
            return httpx.Response(
                200, json={"accessToken": f"token-{self.token_calls}", "expiresIn": 900}
            )
        self.asset_requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def client(self) -> AssetClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self))
        tokens = ServiceTokenSource(
            token_url="http://auth.test/token",
            client_id="messaging",
            client_secret="s",
            http=http,
        )
        return AssetClient(base_url="http://asset.test", tokens=tokens, http=http)


def meta(asset_id: uuid.UUID) -> dict:
    return {
        "assetId": str(asset_id),
        "fileName": "a.png",
        "contentType": "image/png",
        "sizeBytes": 9,
    }


async def claim(client: AssetClient):
    return await client.claim(
        workspace_id=WORKSPACE, user_id=USER, message_id=MESSAGE, asset_ids=[ASSET]
    )


async def test_a_claim_sends_the_contract_body_with_a_bearer_token():
    """Breaks if the workspace or message id is not the one passed, or the token is missing."""
    backend = Backend(httpx.Response(200, json={"items": [meta(ASSET)]}))

    items = await claim(backend.client())

    request = backend.asset_requests[0]
    assert request.url.path == "/api/v1/internal/assets/claim"
    assert request.headers["authorization"] == "Bearer token-1"
    assert json.loads(request.content) == {
        "workspaceId": str(WORKSPACE),
        "userId": str(USER),
        "messageId": str(MESSAGE),
        "assetIds": [str(ASSET)],
    }
    assert [i.model_dump(by_alias=True, mode="json") for i in items] == [meta(ASSET)]


async def test_a_409_becomes_claim_refused_with_reasons():
    """R7: breaks if a refusal is treated as 'unavailable' (503) or loses its reason."""
    problem = {"title": "Conflict", "status": 409, "errors": {str(ASSET): ["not-ready"]}}
    backend = Backend(httpx.Response(409, json=problem))

    with pytest.raises(ClaimRefusedError) as refused:
        await claim(backend.client())

    assert {str(k): str(v) for k, v in refused.value.refusals.items()} == {str(ASSET): "not-ready"}


async def test_a_5xx_becomes_unavailable():
    """R7: breaks if Asset's failure is shown as a refusal or escapes as an httpx error."""
    with pytest.raises(AssetUnavailableError):
        await claim(Backend(httpx.Response(503, json={})).client())


async def test_a_connect_error_becomes_unavailable():
    backend = Backend(httpx.ConnectError("no route"))
    with pytest.raises(AssetUnavailableError):
        await claim(backend.client())


async def test_a_401_refetches_the_token_once_then_succeeds():
    """Conventions §5.5: breaks if a rotated key leaves every send failing until expiry."""
    backend = Backend(httpx.Response(401, json={}), httpx.Response(200, json={"items": []}))

    await claim(backend.client())

    assert backend.token_calls == 2
    assert [r.headers["authorization"] for r in backend.asset_requests] == [
        "Bearer token-1",
        "Bearer token-2",
    ]


async def test_a_second_401_is_unavailable():
    """Breaks if the retry loops: one refetch, then give up."""
    backend = Backend(httpx.Response(401, json={}), httpx.Response(401, json={}))
    with pytest.raises(AssetUnavailableError):
        await claim(backend.client())
    assert backend.token_calls == 2


async def test_download_url_returns_the_url_for_the_message_and_asset():
    backend = Backend(
        httpx.Response(200, json={"url": "http://s3.test/x", "expiresAt": "2026-10-01T09:15:00Z"})
    )

    result = await backend.client().download_url(
        workspace_id=WORKSPACE, message_id=MESSAGE, asset_id=ASSET
    )

    request = backend.asset_requests[0]
    assert request.url.path == f"/api/v1/internal/assets/{ASSET}/download-url"
    assert json.loads(request.content) == {
        "workspaceId": str(WORKSPACE),
        "messageId": str(MESSAGE),
    }
    assert result.model_dump(by_alias=True, mode="json")["url"] == "http://s3.test/x"


async def test_download_404_is_not_found():
    """R10: breaks if Asset's 404 becomes a 503 or an unhandled error."""
    backend = Backend(httpx.Response(404, json={"title": "Not Found"}))
    with pytest.raises(AttachmentNotFoundError):
        await backend.client().download_url(
            workspace_id=WORKSPACE, message_id=MESSAGE, asset_id=OTHER
        )
