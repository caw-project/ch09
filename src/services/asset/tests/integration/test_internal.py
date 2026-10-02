"""Asset's internal routes — the claim and the download URL (issue 4 R7, R10, D43).

Called only by Messaging, with a service token. The request and response shapes
are `contracts.assets` (camelCase on the wire); the stub Messaging's own tests
run against is built from the same models, and these tests prove the *real*
routes honour them. Real Postgres, Redis and Garage throughout.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

CLAIM = "/api/v1/internal/assets/claim"


def claim_body(tokens, message_id: uuid.UUID, *asset_ids: str, **overrides) -> dict:
    body = {
        "workspaceId": str(tokens.WORKSPACE),
        "userId": str(tokens.ADA),
        "messageId": str(message_id),
        "assetIds": list(asset_ids),
    }
    return body | overrides


def download_body(tokens, message_id: uuid.UUID, **overrides) -> dict:
    return {"workspaceId": str(tokens.WORKSPACE), "messageId": str(message_id)} | overrides


async def test_claim_returns_metadata_in_request_order(a_ready_asset, client, messaging, tokens):
    """Breaks if the answer follows the database's order (or id order) rather than the request's."""
    png = await a_ready_asset(file_name="diagram.png")
    pdf = await a_ready_asset(
        file_name="notes.pdf", content_type="application/pdf", content=b"%PDF-1.4 notes"
    )

    response = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), pdf.id, png.id), headers=messaging
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "assetId": pdf.id,
            "fileName": "notes.pdf",
            "contentType": "application/pdf",
            "sizeBytes": len(b"%PDF-1.4 notes"),
        },
        {
            "assetId": png.id,
            "fileName": "diagram.png",
            "contentType": "image/png",
            "sizeBytes": png.size,
        },
    ]


async def test_claim_is_all_or_nothing(a_ready_asset, reserve, client, messaging, tokens):
    """One ready + one pending: 409 keyed by the pending asset, and the ready one is not claimed."""
    ready = await a_ready_asset()
    pending = await reserve(put=False)

    refused = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), ready.id, pending.id), headers=messaging
    )

    assert refused.status_code == 409
    assert refused.headers["content-type"] == "application/problem+json"
    assert refused.json()["errors"] == {pending.id: ["not-ready"]}
    # The proof that nothing was claimed: another message can still have it.
    later = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), ready.id), headers=messaging
    )
    assert later.status_code == 200


async def test_each_reason_is_reported_against_its_asset(
    a_ready_asset, reserve, client, messaging, tokens, grace
):
    """not-found, not-yours and already-attached together: every asset gets its own code."""
    attached = await a_ready_asset()
    first_message = uuid.uuid4()
    await client.post(CLAIM, json=claim_body(tokens, first_message, attached.id), headers=messaging)
    theirs = await a_ready_asset(headers=grace)
    missing = str(uuid.uuid4())

    response = await client.post(
        CLAIM,
        json=claim_body(tokens, uuid.uuid4(), attached.id, theirs.id, missing),
        headers=messaging,
    )

    assert response.status_code == 409
    assert response.json()["errors"] == {
        attached.id: ["already-attached"],
        theirs.id: ["not-yours"],
        missing: ["not-found"],
    }


async def test_another_workspaces_asset_claims_as_not_found(
    a_ready_asset, client, messaging, tokens, other_workspace
):
    """CLAUDE.md: a resource in another workspace is 'not found', never 'not yours'."""
    elsewhere = await a_ready_asset(headers=other_workspace)

    response = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), elsewhere.id), headers=messaging
    )

    assert response.status_code == 409
    assert response.json()["errors"] == {elsewhere.id: ["not-found"]}


async def test_claim_again_for_the_same_message_is_ok(a_ready_asset, client, messaging, tokens):
    """Idempotent for the same (asset, message): the lost-ack retry of the insert."""
    asset = await a_ready_asset()
    message = uuid.uuid4()
    first = await client.post(CLAIM, json=claim_body(tokens, message, asset.id), headers=messaging)

    again = await client.post(CLAIM, json=claim_body(tokens, message, asset.id), headers=messaging)
    other = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), asset.id), headers=messaging
    )

    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    assert other.status_code == 409


@pytest.mark.parametrize("swap", [False, True], ids=["m1-first", "m2-first"])
async def test_two_messages_claiming_one_asset_at_once_one_wins(
    swap, a_ready_asset, client, messaging, tokens
):
    """Decision 9: the row lock serialises the two claims. Both orders, so neither is favoured."""
    asset = await a_ready_asset()
    m1, m2 = uuid.uuid4(), uuid.uuid4()
    messages = [m2, m1] if swap else [m1, m2]

    responses = await asyncio.gather(
        *(
            client.post(CLAIM, json=claim_body(tokens, m, asset.id), headers=messaging)
            for m in messages
        )
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["errors"] == {asset.id: ["already-attached"]}


async def test_a_user_token_cannot_claim(client, ada, tokens):
    """Never `require_user` on an internal route (CLAUDE.md): the audience is wrong."""
    response = await client.post(CLAIM, json=claim_body(tokens, uuid.uuid4()), headers=ada)

    assert response.status_code == 401


async def test_the_wrong_scope_is_403(a_ready_asset, client, tokens):
    asset = await a_ready_asset()
    download_only = {
        "Authorization": f"Bearer {tokens.service('messaging', scopes=('assets:download',))}"
    }

    response = await client.post(
        CLAIM, json=claim_body(tokens, uuid.uuid4(), asset.id), headers=download_only
    )

    assert response.status_code == 403


async def test_the_claim_scope_cannot_download(a_ready_asset, client, tokens):
    """One scope per route (decision 10): `assets:claim` does not open `download-url`."""
    asset = await a_ready_asset()
    message = uuid.uuid4()
    claim_only = {
        "Authorization": f"Bearer {tokens.service('messaging', scopes=('assets:claim',))}"
    }
    await client.post(CLAIM, json=claim_body(tokens, message, asset.id), headers=claim_only)

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, message),
        headers=claim_only,
    )

    assert response.status_code == 403


# --- download-url -----------------------------------------------------------


async def claimed(a_ready_asset, client, messaging, tokens, **asset_kwargs):
    asset = await a_ready_asset(**asset_kwargs)
    message = uuid.uuid4()
    response = await client.post(
        CLAIM, json=claim_body(tokens, message, asset.id), headers=messaging
    )
    assert response.status_code == 200, response.text
    return asset, message


async def test_download_url_for_the_claiming_message(a_ready_asset, client, messaging, tokens):
    """The URL really serves Ada's bytes, inline for an image."""
    asset, message = await claimed(a_ready_asset, client, messaging, tokens)

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, message),
        headers=messaging,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["expiresAt"]
    async with httpx.AsyncClient() as garage:
        fetched = await garage.get(body["url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-disposition"].startswith("inline;")
    assert len(fetched.content) == asset.size


async def test_a_pdf_downloads_as_an_attachment(a_ready_asset, client, messaging, tokens):
    """R10: breaks if the disposition is chosen by the user's content type claim, not the rule."""
    asset, message = await claimed(
        a_ready_asset,
        client,
        messaging,
        tokens,
        file_name="notes.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 notes",
    )

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, message),
        headers=messaging,
    )

    async with httpx.AsyncClient() as garage:
        fetched = await garage.get(response.json()["url"])
    assert fetched.headers["content-disposition"] == "attachment; filename*=UTF-8''notes.pdf"


async def test_download_url_for_another_message_is_404(a_ready_asset, client, messaging, tokens):
    asset, _ = await claimed(a_ready_asset, client, messaging, tokens)

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, uuid.uuid4()),
        headers=messaging,
    )

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_download_url_for_another_workspace_is_404(a_ready_asset, client, messaging, tokens):
    asset, message = await claimed(a_ready_asset, client, messaging, tokens)

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, message, workspaceId=str(tokens.OTHER_WORKSPACE)),
        headers=messaging,
    )

    assert response.status_code == 404


async def test_download_url_for_an_unclaimed_asset_is_404(a_ready_asset, client, messaging, tokens):
    """Ready but on no message: a download is only ever through a message."""
    asset = await a_ready_asset()

    response = await client.post(
        f"/api/v1/internal/assets/{asset.id}/download-url",
        json=download_body(tokens, uuid.uuid4()),
        headers=messaging,
    )

    assert response.status_code == 404
