"""The Asset rules — upload limits, confirm's size check, the claim decision, the key.

Pure functions over values that are already loaded (register D32): no session, no
boto3. The routes fetch and write; what a rule *is* lives here, where a unit test
can reach it.
"""

from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import quote

from asset.models import FAILED, READY, Asset
from contracts.assets import ClaimRefusal

#: Exactly these, compared whole. **There is no SVG** — it runs script when
#: opened — and that allow-list is the entire mitigation for register D15 (no
#: virus scan), so it is a constant here and not a setting someone can widen.
ATTACHMENT_CONTENT_TYPES = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
)

MAX_FILE_NAME_CHARS = 255

PURPOSE_ATTACHMENT = "attachment"

#: Which of these a browser may show inline. Everything else downloads.
_INLINE_PREFIX = "image/"


class UploadRuleError(Exception):
    """An upload request breaks a rule. `field` is the request field it is against."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def check_upload(
    *,
    file_name: str,
    content_type: str,
    size_bytes: int,
    purpose: str,
    max_bytes: int,
) -> None:
    """Raise `UploadRuleError` for the first rule the request breaks.

    `max_bytes` is configuration (`ASSET_MAX_UPLOAD_BYTES`), so it is passed in.
    The content type is an exact match: `image/png; x=1` is not `image/png`.
    """
    if purpose != PURPOSE_ATTACHMENT:
        raise UploadRuleError("purpose", "Only attachments can be uploaded.")
    if content_type not in ATTACHMENT_CONTENT_TYPES:
        raise UploadRuleError(
            "contentType", "Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached."
        )
    if size_bytes < 1:
        raise UploadRuleError("sizeBytes", "This file is empty.")
    if size_bytes > max_bytes:
        raise UploadRuleError("sizeBytes", "Files must be 50 MB or smaller.")
    if not 1 <= len(file_name) <= MAX_FILE_NAME_CHARS:
        raise UploadRuleError("fileName", "File names must be 1 to 255 characters.")


def object_key(workspace_id: uuid.UUID, asset_id: uuid.UUID) -> str:
    """Where an attachment's bytes live. **No file name**: nothing a user chose is in a key."""
    return f"{workspace_id}/{PURPOSE_ATTACHMENT}/{asset_id}"


def confirm_outcome(
    *, declared_bytes: int, stored_bytes: int | None, max_bytes: int
) -> tuple[Literal["ready", "failed"], str | None]:
    """What `confirm` makes of an asset, given what the store says it holds.

    `stored_bytes` is `None` when there is no object. A client can declare a
    huge size honestly, so matching sizes alone are not enough: the limit applies
    to what was stored.
    """
    if stored_bytes is None:
        return FAILED, "The upload did not arrive."
    if stored_bytes != declared_bytes:
        return FAILED, "The file stored is not the size it was declared to be."
    if stored_bytes > max_bytes:
        return FAILED, "Files must be 50 MB or smaller."
    return READY, None


def claim_refusal(
    asset: Asset | None,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
) -> ClaimRefusal | None:
    """Why this asset cannot go on this message, or `None` if it can.

    Checked in this order, and the order matters. Another workspace's asset is
    `NOT_FOUND` and never `NOT_YOURS`: a resource the caller cannot see does not
    exist for them. An asset already claimed by *this* message is fine, which
    makes a retried claim idempotent.
    """
    if asset is None or asset.workspace_id != workspace_id:
        return ClaimRefusal.NOT_FOUND
    if asset.owner_id != user_id:
        return ClaimRefusal.NOT_YOURS
    if asset.status != READY:
        return ClaimRefusal.NOT_READY
    if asset.message_id is not None and asset.message_id != message_id:
        return ClaimRefusal.ALREADY_ATTACHED
    return None


def content_disposition(content_type: str, file_name: str) -> str:
    """The `Content-Disposition` a download is signed with.

    Images open inline; everything else (a PDF) downloads. The name is
    percent-encoded as an RFC 5987 `filename*`, so a quote, a space or a
    non-ASCII character can never break out of the header.
    """
    disposition = "inline" if content_type.startswith(_INLINE_PREFIX) else "attachment"
    return f"{disposition}; filename*=UTF-8''{quote(file_name, safe='')}"
