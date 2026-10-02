"""Attachments on a message — the rules, what is stored, and the claim at send time.

The pure half is rules over loaded values (register D32): the count, the wording
of a refusal, and which attachments a message may show. The rest is the one query
that loads a page's attachments and the helper both transports use to claim a
send's assets before the message is inserted.

**Claim, then insert.** A send chooses the message's id first, claims the assets
for that id with Asset, and only then writes the message and its
`message_attachments` rows. A refused or unreachable claim therefore leaves
nothing behind. The cost is the one-way hole it opens: a claim that succeeds
followed by an insert that fails strands the asset on a message that never
existed — nothing sweeps it (register D16, still open).

**A tombstone shows no attachments** (`visible`) and mints no download URL
(`find_on`): deleting a message removes its files from view even though the
blobs stay in storage.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts.assets import AttachmentMeta, ClaimRefusal
from messaging.assets import AssetClient, AssetUnavailableError, ClaimRefusedError
from messaging.models import Message, MessageAttachment
from shared import ProblemException

#: What the 409's `detail` says for each reason. The reason codes are Asset's wire
#: vocabulary and never reach a client; these are the words.
_REFUSAL_DETAIL: dict[ClaimRefusal, str] = {
    ClaimRefusal.NOT_FOUND: "An attachment could not be found.",
    ClaimRefusal.NOT_YOURS: "An attachment was uploaded by someone else.",
    ClaimRefusal.NOT_READY: "An attachment has not finished uploading.",
    ClaimRefusal.ALREADY_ATTACHED: "An attachment is already on another message.",
}

UNAVAILABLE_DETAIL = "Attachments can't be checked right now. Nothing was sent."


class _HasAssetId(Protocol):
    asset_id: uuid.UUID


class TooManyAttachmentsError(Exception):
    """More ids than `MESSAGING_MAX_ATTACHMENTS`."""


class DuplicateAttachmentError(Exception):
    """The same asset listed twice in one send — the order would be ambiguous."""


def check_attachment_ids(ids: Sequence[uuid.UUID], *, max_attachments: int) -> None:
    """Raise unless the ids are few enough and all different.

    `max_attachments` is configuration, so it is passed in. A repeated id is a
    refusal rather than a silent de-duplication, which would make the order the
    sender chose ambiguous (an assumed decision, one rule to change).
    """
    if len(ids) > max_attachments:
        raise TooManyAttachmentsError
    if len(set(ids)) != len(ids):
        raise DuplicateAttachmentError


def ids_problem(exc: Exception, *, max_attachments: int) -> ProblemException:
    """The 400 for a send whose attachment ids break a rule, against `attachmentIds`.

    The same shape the body rules use, so the composer reads one error format.
    """
    if isinstance(exc, TooManyAttachmentsError):
        message = f"A message can have at most {max_attachments} attachments."
    else:
        message = "An attachment is listed twice."
    return ProblemException.validation_error(message, errors={"attachmentIds": [message]})


def refusal_detail(refusals: dict[uuid.UUID, ClaimRefusal], order: Sequence[uuid.UUID]) -> str:
    """The sentence for the first refused asset **in attach order**.

    Asset's answer is a dictionary and its order is Asset's; the one the sender
    sees first is the first one they attached.
    """
    for asset_id in order:
        if asset_id in refusals:
            return _REFUSAL_DETAIL[refusals[asset_id]]
    # Asset refused an id this send did not name: still a refusal, and the
    # first reason it gave is the best words there are.
    return _REFUSAL_DETAIL[next(iter(refusals.values()))]


def visible[T](message: Message, attachments: list[T]) -> list[T]:
    """What a message shows: its attachments, or none once it is deleted."""
    return [] if message.deleted_at is not None else attachments


def find_on[T: _HasAssetId](
    message: Message, attachments: Sequence[T], asset_id: uuid.UUID
) -> T | None:
    """The attachment with this asset id **on this message**, or `None`.

    Messaging's own record decides, never Asset's: an asset id from another
    message must not mint a URL through this one, and a deleted message's files
    are gone as far as any client can tell.
    """
    if message.deleted_at is not None:
        return None
    return next((a for a in attachments if a.asset_id == asset_id), None)


async def for_messages(
    session: AsyncSession, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[MessageAttachment]]:
    """The attachments of a whole page of messages in one query, in attach order.

    Page-wide, as reactions are: one grouped query for the page and never one per
    message. Messages with none are absent from the result.
    """
    if not message_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(MessageAttachment)
                .where(MessageAttachment.message_id.in_(message_ids))
                .order_by(MessageAttachment.message_id, MessageAttachment.position)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[uuid.UUID, list[MessageAttachment]] = {}
    for row in rows:
        grouped.setdefault(row.message_id, []).append(row)
    return grouped


def add(
    session: AsyncSession, *, message_id: uuid.UUID, metas: Sequence[AttachmentMeta]
) -> list[MessageAttachment]:
    """Stage a message's attachment rows, in the order Asset answered (the attach order)."""
    rows = [
        MessageAttachment(
            message_id=message_id,
            position=position,
            asset_id=meta.asset_id,
            file_name=meta.file_name,
            content_type=meta.content_type,
            size_bytes=meta.size_bytes,
        )
        for position, meta in enumerate(metas)
    ]
    session.add_all(rows)
    return rows


async def claim_for_send(
    assets: AssetClient,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
    asset_ids: Sequence[uuid.UUID],
) -> list[AttachmentMeta]:
    """Claim a send's assets, or raise the Problem that refuses the whole send.

    No call at all for a send with no attachments: every send would otherwise pay
    a round trip, and a token fetch, to Asset. A refusal is a 409 whose `detail`
    names the first refused asset in attach order; an unreachable Asset is a 503.
    Both transports call this, so they cannot disagree.
    """
    if not asset_ids:
        return []
    try:
        return await assets.claim(
            workspace_id=workspace_id,
            user_id=user_id,
            message_id=message_id,
            asset_ids=asset_ids,
        )
    except ClaimRefusedError as exc:
        raise ProblemException.conflict(refusal_detail(exc.refusals, asset_ids)) from exc
    except AssetUnavailableError as exc:
        raise ProblemException.service_unavailable(UNAVAILABLE_DETAIL) from exc
