"""The read-back: does the issue the backend holds say what the draft said?"""

from __future__ import annotations

from delivery.model import Issue
from delivery.readback import differences, normalise

BODY = "## Summary\n\nPins a message.\n\n## Requirements\n\n1. At most one pin.\n"


def issue(title: str = "Pin a message", body: str = BODY) -> Issue:
    return Issue(key="gh-5", number=5, title=title, body=body, url="", labels=[])


def test_normalise_turns_crlf_into_lf():
    assert normalise("a\r\nb\r\n") == "a\nb"


def test_normalise_strips_trailing_whitespace_per_line():
    assert normalise("a  \nb\t\n") == "a\nb"


def test_normalise_strips_leading_and_trailing_blank_lines():
    assert normalise("\n\n a\n\nb\n\n\n") == " a\n\nb"


def test_normalise_keeps_blank_lines_and_indentation_inside():
    """Markdown means something by both."""
    assert normalise("- a\n\n    code\n") == "- a\n\n    code"


def test_an_identical_issue_has_no_differences():
    assert differences("Pin a message", BODY, issue()) == []


def test_line_endings_and_trailing_whitespace_are_not_differences():
    """What GitHub does to a body on the way in."""
    fetched = BODY.replace("\n", "\r\n").replace("message.", "message.   ")

    assert differences("Pin a message", BODY, issue(body=fetched)) == []


def test_title_whitespace_at_the_ends_is_not_a_difference():
    assert differences("Pin a message", BODY, issue(title=" Pin a message ")) == []


def test_a_changed_title_is_named():
    found = differences("Pin a message", BODY, issue(title="Pin messages"))

    assert len(found) == 1
    assert "title" in found[0]
    assert "Pin messages" in found[0]


def test_a_changed_body_line_is_named_with_its_line_number():
    fetched = BODY.replace("At most one pin.", "At most two pins.")

    found = differences("Pin a message", BODY, issue(body=fetched))

    assert len(found) == 1
    assert "body line 7" in found[0]
    assert "At most two pins." in found[0]


def test_a_truncated_body_is_a_difference():
    """A body cut short on the way in — the read-back exists for this."""
    found = differences("Pin a message", BODY, issue(body=BODY.split("## Requirements")[0]))

    assert found != []
    assert "body" in found[0]


def test_title_and_body_differences_are_both_reported():
    found = differences("Pin a message", BODY, issue(title="Other", body="## Summary\n"))

    assert len(found) == 2
