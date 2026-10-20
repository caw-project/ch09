"""Display names — every rule about what a name is, in one pure module.

The application, the database's comparison key and migration 0002 all go through
here, so they cannot disagree about whether two names are one name (issue gh-3,
Req 1-4; register D46):

* `validate` is the stored form of a name, or the list of rules it breaks;
* `name_key` is what `users.display_name_key` holds and the unique index compares.
  Postgres never folds case itself: its `lower()` follows the database's
  `LC_CTYPE` and is not full case folding (`Straße` / `STRASSE`);
* `provisional`, `candidates` and `deduplicate` are how a name an identity
  provider handed over, or one the old schema allowed, becomes a valid and free one.

`Default_Ignorable_Code_Point` has no lookup in `unicodedata`, so the table below
is copied from Unicode 15.0.0's `DerivedCoreProperties.txt` — the version
`unicodedata.unidata_version` reports on Python 3.12. A newer Python can add a
code point to the property without changing this table.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime

MAX_LENGTH = 100
LENGTH_RULE = "A display name must be 1 to 100 characters."
CHARACTER_RULE = "A display name cannot contain invisible or control characters."
# Deliberately names nobody: the same text whether the holder is in the caller's
# workspace or not (D46).
TAKEN = "That name is already taken."

# Control, format, surrogate, private use, unassigned, line and paragraph separators.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Default_Ignorable_Code_Point — unicodedata has no property lookup for it.
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


class InvalidDisplayNameError(ValueError):
    """A name broke one or more rules; `messages` lists every one, length first."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


def normalise(raw: str) -> str:
    """Trim, then compose (NFC), so `Jose` + U+0301 and `José` are one name."""
    return unicodedata.normalize("NFC", raw.strip())


def is_refused(char: str) -> bool:
    """Whether a character may not appear in a name: invisible, or a control."""
    if unicodedata.category(char) in _REFUSED_CATEGORIES:
        return True
    code = ord(char)
    return any(low <= code <= high for low, high in _DEFAULT_IGNORABLE)


def validate(raw: str) -> str:
    """The stored form of `raw`, or raise with every rule it breaks.

    Length is counted in code points after trimming and composing, so padding
    never counts and a combining accent that composes away is not charged twice.
    """
    name = normalise(raw)
    messages: list[str] = []
    if not 1 <= len(name) <= MAX_LENGTH:
        messages.append(LENGTH_RULE)
    if any(is_refused(c) for c in name):
        messages.append(CHARACTER_RULE)
    if messages:
        raise InvalidDisplayNameError(messages)
    return name


def name_key(name: str) -> str:
    """What two names are compared by: full case folding, composed again.

    Folding can denormalise (a folded `ß` is `ss`, some folds produce combining
    sequences), hence the second NFC.
    """
    composed = unicodedata.normalize("NFC", name)
    return unicodedata.normalize("NFC", composed.casefold())


def _clean(raw: str) -> str:
    """Drop refused characters, then trim, compose and cut to the limit."""
    kept = "".join(c for c in unicodedata.normalize("NFC", raw) if not is_refused(c))
    return normalise(normalise(kept)[:MAX_LENGTH])


def provisional(raw: str, fallback: str) -> str:
    """A valid name for a first sign-in, made from whatever the IdP sent.

    Signing in never fails over a name (Req 3) and stored names are always valid
    (Req 1), so a bad one is cleaned rather than refused: refused characters
    dropped, cut to 100, and — when nothing is left — the same from `fallback`
    (the email's local part), then the literal `user`.
    """
    return _clean(raw) or _clean(fallback) or "user"


def candidates(base: str) -> Iterator[str]:
    """`base`, then `base 2`, `base 3`, … each at most 100 characters.

    The base is cut (and right-stripped) so that the suffix always fits.
    """
    yield base[:MAX_LENGTH]
    n = 2
    while True:
        suffix = f" {n}"
        yield base[: MAX_LENGTH - len(suffix)].rstrip() + suffix
        n += 1


@dataclass(frozen=True)
class StoredName:
    """A row of `users` as migration 0002 reads it."""

    id: uuid.UUID
    display_name: str
    email: str
    created_at: datetime


def deduplicate(rows: Iterable[StoredName]) -> dict[uuid.UUID, str]:
    """The new name of every row whose name must change, so all keys are unique.

    Each name is first normalised (an empty one takes the email's local part, as
    a first sign-in would). The oldest holder of a key — by `(created_at, id)`,
    deleted accounts included — keeps it; each later one takes the first
    candidate no one holds. A name someone keeps is reserved before any suffix
    is handed out, so a third account already named `sam 2` is never displaced.
    Rows that need nothing are absent.
    """
    ordered = sorted(rows, key=lambda r: (r.created_at, r.id))
    wanted = {
        r.id: normalise(r.display_name) or normalise(r.email.split("@")[0]) or "user"
        for r in ordered
    }

    taken: set[str] = set()
    losers: list[StoredName] = []
    for row in ordered:
        key = name_key(wanted[row.id])
        if key in taken:
            losers.append(row)
        else:
            taken.add(key)

    final = dict(wanted)
    for row in losers:
        for candidate in candidates(wanted[row.id]):
            key = name_key(candidate)
            if key not in taken:
                taken.add(key)
                final[row.id] = candidate
                break

    return {r.id: final[r.id] for r in ordered if final[r.id] != r.display_name}
