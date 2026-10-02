"""The public handshake — `upload-url` then `confirm` (issue 4 R1, R2).

Against real Postgres, Redis and Garage: the bytes really are PUT to the
presigned URL, and `confirm` really HEADs them. What a rule *is* lives in
`tests/unit/test_rules.py`; each route's use of it is shown once here.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import text

PROBLEM = "application/problem+json"


async def stored(engine, asset_id: str) -> dict:
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT status, failure_reason, object_key, workspace_id, owner_id,"
                        " size_bytes, purpose FROM assets WHERE id = :id AND deleted_at IS NULL"
                    ),
                    {"id": uuid.UUID(asset_id)},
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


async def test_upload_url_reserves_a_pending_asset(client, ada, tokens, engine, garage_server):
    response = await client.post(
        "/api/v1/assets/upload-url",
        json={
            "fileName": "diagram.png",
            "contentType": "image/png",
            "sizeBytes": 1000,
            "purpose": "attachment",
        },
        headers=ada,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["method"] == "PUT"
    assert body["headers"] == {"Content-Type": "image/png"}
    assert body["uploadUrl"].startswith(garage_server.endpoint)
    assert body["expiresAt"]
    row = await stored(engine, body["assetId"])
    assert row["status"] == "pending"
    assert row["owner_id"] == tokens.ADA
    assert row["workspace_id"] == tokens.WORKSPACE
    assert row["size_bytes"] == 1000
    assert row["purpose"] == "attachment"


async def test_upload_url_refuses_svg_with_the_field(client, ada, engine):
    """The route's mapping, once: a rule error is a 400 naming the field, and reserves nothing."""
    response = await client.post(
        "/api/v1/assets/upload-url",
        json={
            "fileName": "logo.svg",
            "contentType": "image/svg+xml",
            "sizeBytes": 100,
            "purpose": "attachment",
        },
        headers=ada,
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM
    problem = response.json()
    assert problem["type"] == "https://collabhub.dev/problems/validation-error"
    assert problem["errors"]["contentType"] == [
        "Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached."
    ]
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM assets")) == 0


async def test_upload_url_needs_a_user_token(client, tokens):
    """The public routes are `require_user`: a service token is the wrong audience."""
    response = await client.post(
        "/api/v1/assets/upload-url",
        json={
            "fileName": "a.png",
            "contentType": "image/png",
            "sizeBytes": 1,
            "purpose": "attachment",
        },
        headers={"Authorization": f"Bearer {tokens.service('messaging')}"},
    )

    assert response.status_code == 401


async def test_confirm_marks_ready_after_the_put(reserve, client, ada, engine):
    reserved = await reserve(put=True)

    response = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert response.status_code == 200
    assert response.json() == {
        "id": reserved.id,
        "fileName": "diagram.png",
        "contentType": "image/png",
        "sizeBytes": reserved.size,
        "status": "ready",
        "failureReason": None,
    }
    assert (await stored(engine, reserved.id))["status"] == "ready"


async def test_confirm_fails_a_short_upload(reserve, client, ada, engine):
    """Declared 10 000, stored far fewer: breaks if confirm trusts the declared size."""
    reserved = await reserve(put=True, declared=10_000)

    response = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failureReason"] == (
        "The file stored is not the size it was declared to be."
    )
    assert (await stored(engine, reserved.id))["status"] == "failed"


async def test_confirm_fails_a_missing_object(reserve, client, ada):
    """Decision 15 (assumed): no PUT happened, so the asset fails with its reason."""
    reserved = await reserve(put=False)

    response = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failureReason"] == "The upload did not arrive."


async def test_confirm_twice_is_unchanged(reserve, client, ada):
    """Decision 14: breaks if a retried confirm re-evaluates, fails, or answers an error."""
    reserved = await reserve(put=True)
    first = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    second = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert first.json()["status"] == "ready"
    assert second.status_code == 200
    assert second.json() == first.json()


async def test_confirm_does_not_re_judge_a_failed_asset(reserve, client, ada):
    """The other branch of 'unchanged': a failed asset stays failed even once the bytes arrive."""
    reserved = await reserve(put=False)
    failed = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)
    async with httpx.AsyncClient() as garage:
        await garage.put(
            reserved.upload["uploadUrl"], content=b"x" * 1000, headers=reserved.upload["headers"]
        )

    again = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert failed.json()["status"] == "failed"
    assert again.json() == failed.json()


async def test_another_users_asset_is_404(reserve, client, grace):
    reserved = await reserve(put=True)

    response = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=grace)

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["detail"] == "No such asset."


async def test_another_workspaces_asset_is_404(reserve, client, other_workspace):
    reserved = await reserve(put=True)

    response = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=other_workspace)

    assert response.status_code == 404
    assert response.json()["detail"] == "No such asset."


async def test_an_unknown_asset_reads_the_same_as_someone_elses(reserve, client, ada, grace):
    """Breaks if 'not yours' and 'not there' are told apart (the CH004 leak)."""
    reserved = await reserve(put=True)

    theirs = await client.post(f"/api/v1/assets/{reserved.id}/confirm", headers=grace)
    nothing = await client.post(f"/api/v1/assets/{uuid.uuid4()}/confirm", headers=ada)

    assert theirs.status_code == nothing.status_code == 404
    assert theirs.json()["detail"] == nothing.json()["detail"]


async def test_the_object_key_is_workspace_attachment_id(reserve, engine, tokens):
    """Decided 4: breaks if the file name, or anything else the user chose, is in the key."""
    reserved = await reserve(file_name="secret plans.png")

    row = await stored(engine, reserved.id)

    assert row["object_key"] == f"{tokens.WORKSPACE}/attachment/{reserved.id}"


async def test_garage_down_is_503_and_changes_nothing(client_for, ada, reserve, engine):
    """Decision 14: confirm with the store unreachable answers 503 and leaves the status alone."""
    reserved = await reserve(put=True)

    async with client_for(
        object_store_endpoint="http://garage.invalid:3900",
    ) as broken:
        response = await broken.post(f"/api/v1/assets/{reserved.id}/confirm", headers=ada)

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM
    assert (await stored(engine, reserved.id))["status"] == "pending"
