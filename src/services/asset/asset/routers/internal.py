"""Asset's internal routes — called only by Messaging, with a service token.

Guarded by `require_service(scope)` and never `require_user` (CH002/CH003): the
audience is `collabhub-internal`, so a user token cannot reach these.

**The workspace is in the body**, set by Messaging from the *caller's* `wsp`
claim, because a service token carries none. That is the one place a workspace
id is read from a request in this service, and it is why CH001 is waived on those
lines: it is trusted because the caller is a service holding the scope, not
because anyone typed it.

`claim` is what puts an asset on a message, atomically and all-or-nothing;
`download-url` is the only thing that ever mints a read URL, and only for the
message that holds the claim.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from asset import rules
from asset.db import session as db_session
from asset.models import READY, Asset
from asset.object_store import ObjectStore
from contracts.assets import (
    SCOPE_CLAIM,
    SCOPE_DOWNLOAD,
    AttachmentMeta,
    ClaimRequest,
    ClaimResponse,
    DownloadUrlRequest,
    DownloadUrlResponse,
)
from shared import ProblemException, ServicePrincipal, require_service

router = APIRouter(prefix="/api/v1/internal/assets", tags=["internal"])


@router.post("/claim", response_model=ClaimResponse)
async def claim_assets(
    body: ClaimRequest,
    _caller: ServicePrincipal = Depends(require_service(SCOPE_CLAIM)),
    session: AsyncSession = Depends(db_session),
) -> ClaimResponse:
    """Put these assets on a message, or refuse them all and change nothing.

    The rows are locked `FOR UPDATE` in id order, then every one is judged with
    `rules.claim_refusal` before any is written. Two sends racing for one asset
    serialize on the lock (the loser reads the winner's committed claim and is
    refused `already-attached`), and id order means two sends naming the same
    assets in different orders cannot deadlock.
    """
    ids = list(dict.fromkeys(body.asset_ids))
    rows = (
        (
            await session.execute(
                select(Asset)
                .where(Asset.id.in_(ids), Asset.deleted_at.is_(None))
                .order_by(Asset.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rows}

    refusals: dict[str, list[str]] = {}
    for asset_id in ids:
        reason = rules.claim_refusal(
            by_id.get(asset_id),
            # Set by Messaging from the caller's `wsp`; a service token carries none.
            workspace_id=body.workspace_id,
            user_id=body.user_id,
            message_id=body.message_id,
        )
        if reason is not None:
            refusals[str(asset_id)] = [reason.value]
    if refusals:
        raise ProblemException.conflict("Some assets cannot be attached.", errors=refusals)

    await session.execute(
        update(Asset)
        .where(Asset.id.in_(ids), Asset.message_id.is_(None))
        .values(message_id=body.message_id, claimed_at=datetime.now(UTC))
    )
    await session.commit()
    return ClaimResponse(
        items=[
            AttachmentMeta(
                asset_id=asset_id,
                file_name=by_id[asset_id].file_name,
                content_type=by_id[asset_id].content_type,
                size_bytes=by_id[asset_id].size_bytes,
            )
            for asset_id in body.asset_ids
        ]
    )


@router.post("/{asset_id}/download-url", response_model=DownloadUrlResponse)
async def download_url(
    asset_id: uuid.UUID,
    body: DownloadUrlRequest,
    request: Request,
    _caller: ServicePrincipal = Depends(require_service(SCOPE_DOWNLOAD)),
    session: AsyncSession = Depends(db_session),
) -> DownloadUrlResponse:
    """A short-lived read URL, if this asset is `ready` and on exactly this message.

    One 404 for every miss (another workspace, another message, unclaimed, not
    ready), so the answer says nothing about which.
    """
    row = (
        await session.execute(
            select(Asset).where(
                Asset.id == asset_id,
                # Set by Messaging from the caller's `wsp`; a service token carries none.
                Asset.workspace_id == body.workspace_id,
                Asset.message_id == body.message_id,
                Asset.status == READY,
                Asset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProblemException.not_found("No such asset.")

    store: ObjectStore = request.app.state.store
    url, expires_at = store.presign_get(
        row.object_key, rules.content_disposition(row.content_type, row.file_name)
    )
    return DownloadUrlResponse(url=url, expires_at=expires_at)
