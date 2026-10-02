"""The thread rules: what a reply is and which root a reply is filed under (doc 02 §3.1, issue 3).

Pure functions over loaded rows. The reply's root is always a different id from
the reply's own, so "returns the row's id" and "returns its root" cannot coincide.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from messaging import threads


def test_a_root_is_its_own_thread(a_message):
    """Breaks if a top-level row is refused or mapped to something else."""
    root = a_message()

    assert threads.root_for(root, channel_id=root.channel_id) == root.id


def test_a_reply_is_filed_under_its_root(a_message):
    """R2: a `threadRootId` naming a reply files under that reply's root, not under the reply."""
    root_id = uuid.uuid4()
    reply = a_message(thread_root_id=root_id)

    chosen = threads.root_for(reply, channel_id=reply.channel_id)

    assert chosen == root_id
    assert chosen != reply.id


def test_a_deleted_reply_still_names_its_root(a_message):
    """Decision 21: a tombstoned reply is normalised like any other."""
    root_id = uuid.uuid4()
    reply = a_message(thread_root_id=root_id, deleted_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC))

    assert threads.root_for(reply, channel_id=reply.channel_id) == root_id


def test_a_deleted_root_still_takes_replies(a_message):
    """R10: a tombstone is a valid root."""
    root = a_message(deleted_at=datetime(2026, 9, 15, 10, 0, tzinfo=UTC))

    assert threads.root_for(root, channel_id=root.channel_id) == root.id


def test_an_unknown_root_is_refused():
    with pytest.raises(threads.NoSuchThreadError):
        threads.root_for(None, channel_id=uuid.uuid4())


def test_a_root_in_another_channel_is_refused(a_message):
    """Same row accepted for its own channel, refused for any other — only the channel differs."""
    root = a_message()

    assert threads.root_for(root, channel_id=root.channel_id) == root.id
    with pytest.raises(threads.NoSuchThreadError):
        threads.root_for(root, channel_id=uuid.uuid4())


def test_is_reply(a_message):
    assert threads.is_reply(a_message(thread_root_id=uuid.uuid4())) is True
    assert threads.is_reply(a_message()) is False


def test_no_replies_is_zero_and_never():
    assert threads.Summary(0, None) == threads.NO_REPLIES
