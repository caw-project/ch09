"""Asset's public routes — the upload handshake (design doc 04 §3).

`upload-url` reserves a `pending` asset and returns a presigned PUT; the browser
sends the bytes **straight to object storage** (Asset never streams a blob), then
calls `confirm`, which HEADs the object and decides `ready` or `failed`.

These are the only public routes. There is no `GET /assets/{id}` and no download
route: a download is minted by Messaging, which knows who may see the message the
asset is on (register D43).

**An asset that is not the caller's is a 404**, in another user's hands or
another workspace, worded identically to one that does not exist — a 403 would
confirm it is there. Plain `require_user`: none of this is in the fail-closed set
of Conventions §5.2.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from asset import rules
from asset.db import session as db_session
from asset.models import PENDING, Asset
from asset.object_store import ObjectStore, ObjectStoreUnavailableError
from asset.settings import Settings
from shared import ProblemException, UserPrincipal, require_user, uuid7

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UploadUrlRequest(_Wire):
    """Declare a file before sending it. Every field is judged by `asset.rules`."""

    file_name: str
    content_type: str
    size_bytes: int
    #: A string, not a `Literal`, so a wrong purpose is a rule error naming the field.
    purpose: str


class UploadUrlResponse(_Wire):
    asset_id: uuid.UUID
    upload_url: str
    method: Literal["PUT"]
    #: Headers the PUT must carry. The `Content-Type` is signed: any other is refused.
    headers: dict[str, str]
    expires_at: datetime


class AssetResponse(_Wire):
    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    status: Literal["pending", "ready", "failed"]
    failure_reason: str | None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> ObjectStore:
    return request.app.state.store


def _as_response(row: Asset) -> AssetResponse:
    # Validated rather than constructed: `status` is a text column, and the
    # DTO's `Literal` is what proves it holds one of the three.
    return AssetResponse.model_validate(
        {
            "id": row.id,
            "file_name": row.file_name,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "status": row.status,
            "failure_reason": row.failure_reason,
        }
    )


@router.post("/upload-url", response_model=UploadUrlResponse, status_code=status.HTTP_201_CREATED)
async def request_upload_url(
    body: UploadUrlRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UploadUrlResponse:
    """Reserve an asset and sign a PUT for it. Nothing is stored yet."""
    settings = _settings(request)
    try:
        rules.check_upload(
            file_name=body.file_name,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            purpose=body.purpose,
            max_bytes=settings.asset_max_upload_bytes,
        )
    except rules.UploadRuleError as exc:
        raise ProblemException.validation_error(
            exc.message, errors={exc.field: [exc.message]}
        ) from exc

    asset_id = uuid7()
    key = rules.object_key(principal.workspace_id, asset_id)
    upload_url, expires_at = _store(request).presign_put(key, body.content_type)

    session.add(
        Asset(
            id=asset_id,
            # The token's `wsp`, and nothing from the request.
            workspace_id=principal.workspace_id,
            owner_id=principal.user_id,
            file_name=body.file_name,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
            purpose=body.purpose,
            bucket=settings.object_store_bucket,
            object_key=key,
            status=PENDING,
        )
    )
    await session.commit()
    return UploadUrlResponse(
        asset_id=asset_id,
        upload_url=upload_url,
        method="PUT",
        headers={"Content-Type": body.content_type},
        expires_at=expires_at,
    )


@router.post("/{asset_id}/confirm", response_model=AssetResponse)
async def confirm_upload(
    asset_id: uuid.UUID,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> AssetResponse:
    """Check what arrived and mark the asset `ready` or `failed`.

    **Idempotent.** An asset that is no longer `pending` is returned as it is,
    so a retried confirm is harmless, and a `failed` asset is never re-judged
    even if bytes show up later.

    A missing object is `failed`, not left pending: the SPA only confirms after
    its PUT succeeded, so no object means the PUT failed (an assumed decision,
    one branch to change). With the store unreachable the answer is 503 and the
    status is left alone, so the client can simply confirm again.
    """
    row = (
        await session.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.workspace_id == principal.workspace_id,
                Asset.owner_id == principal.user_id,
                Asset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProblemException.not_found("No such asset.")
    if row.status != PENDING:
        return _as_response(row)

    try:
        stored = await _store(request).head(row.object_key)
    except ObjectStoreUnavailableError as exc:
        raise ProblemException.service_unavailable(
            "File storage is unavailable right now."
        ) from exc

    outcome, reason = rules.confirm_outcome(
        declared_bytes=row.size_bytes,
        stored_bytes=stored,
        max_bytes=_settings(request).asset_max_upload_bytes,
    )
    # Guarded on `pending`, so two confirms racing cannot overwrite each other.
    await session.execute(
        update(Asset)
        .where(Asset.id == asset_id, Asset.status == PENDING)
        .values(status=outcome, failure_reason=reason, confirmed_at=datetime.now(UTC))
    )
    await session.commit()
    await session.refresh(row)
    return _as_response(row)
