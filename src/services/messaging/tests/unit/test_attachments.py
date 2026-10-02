"""Messaging's attachment rules — the count, the refusal wording, tombstone redaction.

Pure functions over loaded values (register D32); the routes that apply them are
proven once in `tests/integration/test_attachments.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from contracts.assets import ClaimRefusal
from messaging.attachments import (
    DuplicateAttachmentError,
    TooManyAttachmentsError,
    check_attachment_ids,
    find_on,
    refusal_detail,
    visible,
)
from shared import uuid7

MAX = 10


@dataclass(frozen=True)
class Snapshot:
    """What `visible` and `find_on` need of a stored attachment: its asset id."""

    asset_id: uuid.UUID


def ids(n: int) -> list[uuid.UUID]:
    return [uuid7() for _ in range(n)]


# --- the count ----------------------------------------------------------------


def test_ten_ids_pass_eleven_fail():
    """Breaks if the bound is exclusive, off by one, or hard-coded rather than the setting."""
    check_attachment_ids(ids(10), max_attachments=MAX)
    check_attachment_ids([], max_attachments=MAX)
    with pytest.raises(TooManyAttachmentsError):
        check_attachment_ids(ids(11), max_attachments=MAX)


def test_the_limit_is_the_one_passed_in():
    """`MESSAGING_MAX_ATTACHMENTS` is configuration."""
    check_attachment_ids(ids(3), max_attachments=3)
    with pytest.raises(TooManyAttachmentsError):
        check_attachment_ids(ids(4), max_attachments=3)


def test_a_duplicate_id_fails():
    """Decision 26: breaks if a repeated id is let through (the order would be ambiguous)."""
    one, two = ids(2)
    with pytest.raises(DuplicateAttachmentError):
        check_attachment_ids([one, two, one], max_attachments=MAX)
    check_attachment_ids([one, two], max_attachments=MAX)


# --- the refusal wording ------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        (ClaimRefusal.NOT_FOUND, "An attachment could not be found."),
        (ClaimRefusal.NOT_YOURS, "An attachment was uploaded by someone else."),
        (ClaimRefusal.NOT_READY, "An attachment has not finished uploading."),
        (ClaimRefusal.ALREADY_ATTACHED, "An attachment is already on another message."),
    ],
)
def test_each_reason_has_its_wording(reason, detail):
    """Breaks if a reason code leaks to the client or maps to another reason's text."""
    only = uuid7()
    assert refusal_detail({only: reason}, [only]) == detail


def test_refusal_detail_names_the_first_in_attach_order():
    """Breaks if the dict's order (the server's) decides rather than the order attached."""
    first, second = ids(2)
    refusals = {second: ClaimRefusal.NOT_READY, first: ClaimRefusal.NOT_FOUND}

    assert refusal_detail(refusals, [first, second]) == "An attachment could not be found."
    assert refusal_detail(refusals, [second, first]) == "An attachment has not finished uploading."


# --- tombstones and lookups ---------------------------------------------------


def test_a_tombstone_shows_no_attachments(a_message):
    """R12: breaks if a deleted message keeps its attachments in any response."""
    stored = [Snapshot(uuid7()), Snapshot(uuid7())]
    live = a_message()
    from datetime import UTC, datetime

    dead = a_message(deleted_at=datetime(2026, 10, 1, tzinfo=UTC))

    assert visible(live, stored) == stored
    assert visible(dead, stored) == []


def test_find_on_hits_an_asset_on_the_message(a_message):
    """The positive for the two misses below."""
    mine = Snapshot(uuid7())
    assert find_on(a_message(), [Snapshot(uuid7()), mine], mine.asset_id) == mine


def test_find_on_misses_another_messages_asset(a_message):
    """R10: an asset id from elsewhere must not mint a URL through this message."""
    assert find_on(a_message(), [Snapshot(uuid7())], uuid7()) is None


def test_find_on_misses_on_a_tombstone(a_message):
    """R10: a deleted message answers 404 even for an asset it once carried."""
    from datetime import UTC, datetime

    mine = Snapshot(uuid7())
    dead = a_message(deleted_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert find_on(dead, [mine], mine.asset_id) is None
