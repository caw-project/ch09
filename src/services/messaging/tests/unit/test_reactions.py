"""The reaction rules — the allowlist, the tombstone, and the shape of a summary.

Pure functions over values that are already loaded (register D32), so none of
this needs a session and nothing is faked. That a route *applies* each rule, and
which status it maps to, is proven once in `tests/integration/test_reactions.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from messaging.models import Message
from messaging.reactions import (
    REACTION_EMOJI,
    Summary,
    UnknownEmojiError,
    may_react,
    summarise,
    validate,
)

DELETED_AT = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
ONE = uuid.uuid4()
TWO = uuid.uuid4()


# --- the allowlist ---------------------------------------------------------


@pytest.mark.parametrize("emoji", REACTION_EMOJI)
def test_every_listed_shortcode_is_accepted(emoji):
    """Breaks if the tuple and the validator ever disagree about what is in the set."""
    assert validate(emoji) == emoji


@pytest.mark.parametrize(
    "emoji",
    [
        pytest.param("shrug", id="not-in-the-set"),
        pytest.param("", id="empty"),
        pytest.param("THUMBSUP", id="uppercase"),
        pytest.param("thumbsup ", id="trailing-space"),
        pytest.param("x" * 33, id="longer-than-the-column"),
        pytest.param("👍", id="the-character-rather-than-the-shortcode"),
    ],
)
def test_anything_else_is_refused(emoji):
    """Breaks if validation is loosened to "any short string" — the column would take it."""
    with pytest.raises(UnknownEmojiError):
        validate(emoji)


def test_the_allowlist_has_no_duplicates_and_fits_the_column():
    """The tuple is the whole rule, so it has to stay well-formed."""
    assert len(set(REACTION_EMOJI)) == len(REACTION_EMOJI)
    assert all(len(emoji) <= 32 for emoji in REACTION_EMOJI)


# --- the tombstone ---------------------------------------------------------


def test_a_live_message_may_be_reacted_to():
    assert may_react(Message(id=ONE, deleted_at=None)) is True


def test_a_deleted_message_may_not_be_reacted_to():
    """Breaks if the state check is dropped — a tombstone would collect reactions."""
    assert may_react(Message(id=ONE, deleted_at=DELETED_AT)) is False


# --- the summary shape -----------------------------------------------------


def test_summaries_are_grouped_by_message():
    rows = [(ONE, "heart", 2, True), (TWO, "heart", 1, False)]

    assert summarise(rows) == {
        ONE: [Summary(emoji="heart", count=2, reacted=True)],
        TWO: [Summary(emoji="heart", count=1, reacted=False)],
    }


def test_summaries_are_ordered_by_the_allowlist_and_not_by_count():
    """Chips must not swap places under the pointer as counts change.

    Breaks if the order is taken from the query, which groups in whatever order
    Postgres finds convenient.
    """
    rows = [(ONE, "check", 1, False), (ONE, "thumbsup", 9, False), (ONE, "heart", 5, False)]

    assert [s.emoji for s in summarise(rows)[ONE]] == ["thumbsup", "heart", "check"]


def test_reacted_is_carried_through_per_emoji():
    """The caller's own state is per emoji, not per message."""
    rows = [(ONE, "thumbsup", 3, True), (ONE, "heart", 1, False)]

    assert summarise(rows)[ONE] == [
        Summary(emoji="thumbsup", count=3, reacted=True),
        Summary(emoji="heart", count=1, reacted=False),
    ]


def test_a_shortcode_no_longer_in_the_allowlist_is_dropped():
    """Widening the set is easy; narrowing it strands rows, and those must not render.

    Breaks if `summarise` trusts whatever the table holds — the sort would then
    raise a KeyError on a retired shortcode instead of ignoring it.
    """
    rows = [(ONE, "retired", 4, True), (ONE, "heart", 1, False)]

    assert summarise(rows)[ONE] == [Summary(emoji="heart", count=1, reacted=False)]


def test_no_rows_is_an_empty_mapping():
    """A message with no reactions gets `[]` from the router, never a missing key."""
    assert summarise([]) == {}
