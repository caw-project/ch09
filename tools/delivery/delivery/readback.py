"""The read-back: does the issue a backend holds say what the draft said?

Compared after normalising what a backend may change on the way in without
changing the meaning — line endings, trailing whitespace, blank lines at the
ends. Anything else is a difference, named so the skill can say what went wrong.
"""

from __future__ import annotations

from delivery.model import Issue


def normalise(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def differences(title: str, body: str, issue: Issue) -> list[str]:
    """One line per difference between the draft and the issue; empty when they match."""
    found = []
    if title.strip() != issue.title.strip():
        found.append(f"title: drafted {title.strip()!r}, the issue has {issue.title.strip()!r}")
    drafted = normalise(body).split("\n")
    held = normalise(issue.body).split("\n")
    for number, (want, got) in enumerate(zip(drafted, held, strict=False), start=1):
        if want != got:
            found.append(f"body line {number}: drafted {want!r}, the issue has {got!r}")
            break
    else:
        if len(drafted) != len(held):
            found.append(
                f"body: drafted {len(drafted)} lines, the issue has {len(held)}"
                f" — it differs from line {min(len(drafted), len(held)) + 1}"
            )
    return found
