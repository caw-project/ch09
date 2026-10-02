"""Message body rules (doc 02 §3.1.3) — every rule, with no database.

`tests/integration/test_messages.py` keeps one example per rule per route, and
the test that the *configured* limit reaches the route. The rule itself is here.
"""

from __future__ import annotations

import pytest

from messaging.messages import BodyRequiredError, BodyTooLongError, validate_body

LIMIT = 8000


@pytest.mark.parametrize("raw", ["", " ", "   ", "\n\t  \n"])
def test_an_empty_or_whitespace_only_body_is_refused(raw):
    """Breaks if emptiness is judged on the raw string rather than the stripped one."""
    with pytest.raises(BodyRequiredError):
        validate_body(raw, max_chars=LIMIT)


def test_an_empty_body_passes_when_allowed():
    """R6: a message may be only attachments. Breaks if `allow_empty` is ignored."""
    assert validate_body("", max_chars=LIMIT, allow_empty=True) == ""


def test_whitespace_passes_as_empty_when_allowed():
    """Decision 38: a blank body and an empty one read the same, and are stored as `""`."""
    assert validate_body("  \n\t ", max_chars=LIMIT, allow_empty=True) == ""


def test_whitespace_still_fails_when_not_allowed():
    """The guard for the two above: `allow_empty` defaults to refusing."""
    with pytest.raises(BodyRequiredError):
        validate_body("   ", max_chars=LIMIT, allow_empty=False)


def test_a_non_empty_body_is_still_returned_verbatim_when_empty_is_allowed():
    """Breaks if `allow_empty` switches on stripping for every body."""
    assert validate_body("  hi  ", max_chars=LIMIT, allow_empty=True) == "  hi  "


def test_a_body_over_the_limit_is_refused():
    with pytest.raises(BodyTooLongError):
        validate_body("a" * (LIMIT + 1), max_chars=LIMIT)


def test_a_body_of_exactly_the_limit_is_accepted():
    """Breaks if the limit is off by one."""
    assert validate_body("a" * LIMIT, max_chars=LIMIT) == "a" * LIMIT


def test_the_body_is_returned_verbatim():
    """Markdown is whitespace-sensitive: breaks if the body is trimmed like a channel name."""
    raw = "    indented code\ntrailing  "
    assert validate_body(raw, max_chars=LIMIT) == raw


def test_length_is_judged_on_the_raw_body():
    """Breaks if surrounding whitespace is stripped before the length check."""
    with pytest.raises(BodyTooLongError):
        validate_body(" " + "a" * 10, max_chars=10)


def test_the_configured_limit_is_the_one_applied():
    """`MESSAGING_MAX_BODY_CHARS` is configuration: breaks if a constant replaces it."""
    assert validate_body("a" * 10, max_chars=10) == "a" * 10
    with pytest.raises(BodyTooLongError):
        validate_body("a" * 11, max_chars=10)
