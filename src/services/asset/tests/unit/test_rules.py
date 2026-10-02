"""The Asset rules — upload limits, confirm's size check, the claim decision, the key.

Pure functions over values that are already loaded (register D32): no session, no
boto3, no Garage. That a route *applies* each rule is proven in
`tests/integration/test_uploads.py` and `test_internal.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import pytest

from asset.models import Asset
from asset.rules import (
    ATTACHMENT_CONTENT_TYPES,
    MAX_FILE_NAME_CHARS,
    UploadRuleError,
    check_upload,
    claim_refusal,
    confirm_outcome,
    content_disposition,
    object_key,
)
from contracts.assets import ClaimRefusal

MAX = 52_428_800
WORKSPACE = uuid.uuid4()
USER = uuid.uuid4()
MESSAGE = uuid.uuid4()
AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def upload(**overrides: Any) -> None:
    """`check_upload` with a valid file, and whichever input the test flips."""
    values: dict[str, Any] = {
        "file_name": "diagram.png",
        "content_type": "image/png",
        "size_bytes": 1000,
        "purpose": "attachment",
        "max_bytes": MAX,
    }
    check_upload(**(values | overrides))


def refusal_of(**overrides: Any) -> UploadRuleError:
    with pytest.raises(UploadRuleError) as raised:
        upload(**overrides)
    return raised.value


# --- the allow-list ---------------------------------------------------------


@pytest.mark.parametrize("content_type", ATTACHMENT_CONTENT_TYPES)
def test_each_allowed_type_passes(content_type):
    """Breaks if the tuple and the check disagree about what is in the set."""
    upload(content_type=content_type)


def test_the_allow_list_is_exactly_the_five_types():
    """The list is the whole mitigation for D15: breaks if a type is added without a decision."""
    assert set(ATTACHMENT_CONTENT_TYPES) == {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
    }


def test_svg_is_refused():
    """SVG runs script when opened: breaks if the allow-list admits it."""
    refused = refusal_of(content_type="image/svg+xml")
    assert refused.field == "contentType"
    assert refused.message == "Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached."


def test_a_type_with_parameters_is_refused():
    """Exact match only: breaks if the check splits on `;` and lets a parameter through."""
    assert refusal_of(content_type="image/png; x=1").field == "contentType"


# --- size -------------------------------------------------------------------


def test_the_limit_itself_passes_and_one_more_byte_fails():
    """Breaks if the bound is exclusive, or off by one the other way."""
    upload(size_bytes=MAX)
    refused = refusal_of(size_bytes=MAX + 1)
    assert refused.field == "sizeBytes"
    assert refused.message == "Files must be 50 MB or smaller."


def test_zero_bytes_is_refused():
    refused = refusal_of(size_bytes=0)
    assert refused.field == "sizeBytes"
    assert refused.message == "This file is empty."


def test_one_byte_passes():
    """Breaks if the lower bound is `> 1` rather than `>= 1`."""
    upload(size_bytes=1)


def test_the_limit_is_the_one_passed_in():
    """`ASSET_MAX_UPLOAD_BYTES` is configuration: breaks if a constant replaces it."""
    upload(size_bytes=100, max_bytes=100)
    assert refusal_of(size_bytes=101, max_bytes=100).field == "sizeBytes"


# --- name and purpose ---------------------------------------------------------


def test_255_characters_pass_and_256_fail():
    """Breaks if the name bound is off by one, either way."""
    assert MAX_FILE_NAME_CHARS == 255
    upload(file_name="a" * 255)
    refused = refusal_of(file_name="a" * 256)
    assert refused.field == "fileName"
    assert refused.message == "File names must be 1 to 255 characters."


def test_an_empty_name_fails():
    assert refusal_of(file_name="").field == "fileName"


def test_a_purpose_other_than_attachment_fails():
    """Avatars and exports are not this issue: breaks if any purpose is accepted."""
    refused = refusal_of(purpose="avatar")
    assert refused.field == "purpose"
    assert refused.message == "Only attachments can be uploaded."


# --- the key ----------------------------------------------------------------


def test_the_object_key_has_no_file_name():
    """Decided 4: breaks if a user-chosen name reaches the key."""
    workspace, asset = uuid.uuid4(), uuid.uuid4()
    assert object_key(workspace, asset) == f"{workspace}/attachment/{asset}"


# --- confirm ----------------------------------------------------------------


def test_confirm_ready_when_sizes_match():
    assert confirm_outcome(declared_bytes=500, stored_bytes=500, max_bytes=MAX) == ("ready", None)


def test_confirm_failed_when_missing():
    assert confirm_outcome(declared_bytes=500, stored_bytes=None, max_bytes=MAX) == (
        "failed",
        "The upload did not arrive.",
    )


@pytest.mark.parametrize("stored", [499, 501])
def test_confirm_failed_when_one_byte_short_or_over(stored):
    """Breaks if the comparison is `<` or `>` rather than equality."""
    assert confirm_outcome(declared_bytes=500, stored_bytes=stored, max_bytes=MAX) == (
        "failed",
        "The file stored is not the size it was declared to be.",
    )


def test_confirm_failed_over_the_limit_even_when_declared():
    """A client can declare a huge size honestly: breaks if matching sizes alone make it ready."""
    assert confirm_outcome(declared_bytes=MAX + 1, stored_bytes=MAX + 1, max_bytes=MAX) == (
        "failed",
        "Files must be 50 MB or smaller.",
    )


def test_confirm_at_the_limit_is_ready():
    """The other side of the bound above."""
    assert confirm_outcome(declared_bytes=MAX, stored_bytes=MAX, max_bytes=MAX) == ("ready", None)


# --- the claim --------------------------------------------------------------


def an_asset(**overrides: Any) -> Asset:
    """A ready asset in Ada's workspace, uploaded by Ada, claimed by nobody."""
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": WORKSPACE,
        "owner_id": USER,
        "file_name": "diagram.png",
        "content_type": "image/png",
        "size_bytes": 1000,
        "purpose": "attachment",
        "bucket": "collabhub-assets",
        "object_key": "k",
        "status": "ready",
        "message_id": None,
        "created_at": AT,
    }
    return Asset(**(values | overrides))


def refusal(asset: Asset | None, **overrides: Any) -> ClaimRefusal | None:
    values: dict[str, Any] = {"workspace_id": WORKSPACE, "user_id": USER, "message_id": MESSAGE}
    return claim_refusal(asset, **(values | overrides))


def test_a_clean_asset_is_not_refused():
    """The positive that every refusal below is a single flip of."""
    assert refusal(an_asset()) is None


@pytest.mark.parametrize(
    ("asset", "expected"),
    [
        pytest.param(None, ClaimRefusal.NOT_FOUND, id="missing"),
        pytest.param(an_asset(owner_id=uuid.uuid4()), ClaimRefusal.NOT_YOURS, id="not-yours"),
        pytest.param(an_asset(status="pending"), ClaimRefusal.NOT_READY, id="pending"),
        pytest.param(an_asset(status="failed"), ClaimRefusal.NOT_READY, id="failed"),
        pytest.param(
            an_asset(message_id=uuid.uuid4()), ClaimRefusal.ALREADY_ATTACHED, id="attached"
        ),
    ],
)
def test_claim_refusals_in_order(asset, expected):
    """Each row breaks exactly one check; breaks if a check is dropped or answers wrongly."""
    assert refusal(asset) == expected


def test_the_checks_run_in_order():
    """An asset failing every check reports the first: workspace, owner, status, claim."""
    everything_wrong = an_asset(
        workspace_id=uuid.uuid4(), owner_id=uuid.uuid4(), status="pending", message_id=uuid.uuid4()
    )
    assert refusal(everything_wrong) == ClaimRefusal.NOT_FOUND
    not_yours_and_more = an_asset(owner_id=uuid.uuid4(), status="pending", message_id=uuid.uuid4())
    assert refusal(not_yours_and_more) == ClaimRefusal.NOT_YOURS
    not_ready_and_attached = an_asset(status="pending", message_id=uuid.uuid4())
    assert refusal(not_ready_and_attached) == ClaimRefusal.NOT_READY


def test_claimed_by_this_message_is_no_refusal():
    """Idempotency: the same (asset, message) claimed twice is fine; another message is not."""
    assert refusal(an_asset(message_id=MESSAGE)) is None
    assert refusal(an_asset(message_id=MESSAGE), message_id=uuid.uuid4()) == (
        ClaimRefusal.ALREADY_ATTACHED
    )


def test_another_workspace_reads_as_not_found():
    """A resource the caller may not see is a 404, never `not-yours` (CLAUDE.md)."""
    other = an_asset(workspace_id=uuid.uuid4())
    assert refusal(other) == ClaimRefusal.NOT_FOUND


# --- Content-Disposition ----------------------------------------------------


def test_pdf_downloads_as_attachment():
    header = content_disposition("application/pdf", "notes.pdf")
    assert header == "attachment; filename*=UTF-8''notes.pdf"


@pytest.mark.parametrize("content_type", ["image/png", "image/jpeg", "image/gif", "image/webp"])
def test_images_open_inline(content_type):
    """Breaks if every type is forced to download, or every type is shown inline."""
    assert content_disposition(content_type, "a.png").startswith("inline;")


def test_a_non_ascii_name_is_percent_encoded():
    """Breaks if a raw non-ASCII name or a quote reaches the header."""
    header = content_disposition("application/pdf", 'Résumé "v2".pdf')
    assert header == f"attachment; filename*=UTF-8''{quote('Résumé "v2".pdf', safe='')}"
    assert header.isascii()
    assert '"' not in header
