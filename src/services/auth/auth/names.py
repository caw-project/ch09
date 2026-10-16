"""What a display name may be, and what a taken one becomes (register D46).

Pure rules with no database, so the route, first-sign-in provisioning and
migration `0002` all apply the very same ones. The unique index on
`lower(display_name)` is the only arbiter of uniqueness; this module guarantees
what the index cannot see — that every stored name is already trimmed and free
of characters nobody can see. (The index does not `btrim()`: that trims only
spaces, while `str.strip()` trims all Unicode whitespace, and two trims that
disagree are worse than one.)
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from itertools import count

MAX_LENGTH = 100

# Control, invisible format (zero-width and bidi marks), surrogate, private-use,
# unassigned, and the invisible line and paragraph separators.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

_REQUIRED = "A display name is required."
_TOO_LONG = f"A display name is at most {MAX_LENGTH} characters."
_INVISIBLE = "A display name cannot contain control or invisible characters."


class InvalidDisplayNameError(ValueError):
    """A name the rules refuse; `message` is safe to show the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _refused(char: str) -> bool:
    return unicodedata.category(char) in _REFUSED_CATEGORIES


def validate_display_name(raw: str) -> str:
    """The trimmed name, or `InvalidDisplayNameError` saying why not.

    Length is counted in code points after trimming, so padding never costs a
    character of the 100.
    """
    name = raw.strip()
    if not name:
        raise InvalidDisplayNameError(_REQUIRED)
    if len(name) > MAX_LENGTH:
        raise InvalidDisplayNameError(_TOO_LONG)
    if any(_refused(char) for char in name):
        raise InvalidDisplayNameError(_INVISIBLE)
    return name


def provisional_name(raw: str) -> str:
    """A name an identity provider supplied, cleaned rather than refused.

    Sign-in must never fail over a name, so a bad one is trimmed, stripped of
    refused characters and cut to length; `"user"` stands in when nothing is left.
    """
    kept = "".join(char for char in raw.strip() if not _refused(char))
    return kept.strip()[:MAX_LENGTH].strip() or "user"


def candidates(base: str) -> Iterator[str]:
    """`base`, then `base 2`, `base 3`… — each cut so it stays within 100.

    Lazy and unbounded: the caller stops at the first free one.
    """
    yield base
    for number in count(2):
        suffix = f" {number}"
        stem = base[: MAX_LENGTH - len(suffix)].rstrip()
        yield f"{stem}{suffix}"
