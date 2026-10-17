"""Every rule about a display name, in one place (gh-3; register D46).

Normalising and validating a name, the key two names are compared by, the first
free suffix and the renaming of duplicates all live here, so that the route, the
first sign-in and the migration cannot disagree about what "the same name" means.

The comparison key is computed here, once, and *stored* (`users.display_name_key`).
The database never folds case itself: a `lower()` index would be a second,
different case rule, which is exactly the drift this module exists to prevent.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

MAX_LENGTH = 100

# General categories whose characters are invisible or structural: control,
# format, surrogate, private use, unassigned, line and paragraph separators.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Python has no accessor for Default_Ignorable_Code_Point, and several of its
# members (the Hangul fillers, the variation selectors) are not format characters.
_DEFAULT_IGNORABLE = (  # DerivedCoreProperties.txt, Default_Ignorable_Code_Point
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

_FALLBACK = "user"


class InvalidNameError(ValueError):
    """A display name the rules refuse; the message is safe to show the user."""


def _refused(char: str) -> bool:
    if unicodedata.category(char) in _REFUSED_CATEGORIES:
        return True
    code = ord(char)
    return any(low <= code <= high for low, high in _DEFAULT_IGNORABLE)


def stored_form(raw: str) -> str:
    """Trim and compose to NFC; never refuse.

    The migration's step, and the comparison that lets a user save the name they
    already have even when it holds a character the rules now refuse.
    """
    return unicodedata.normalize("NFC", raw.strip())


def normalise_display_name(raw: str) -> str:
    """The name to store for `raw`, or `InvalidNameError`.

    Length is counted in code points after trimming and composing, so a name that
    is 101 code points only before NFC is accepted.
    """
    name = stored_form(raw)
    if not name:
        raise InvalidNameError("A display name is required.")
    if len(name) > MAX_LENGTH:
        raise InvalidNameError(f"A display name can be at most {MAX_LENGTH} characters.")
    if any(_refused(char) for char in name):
        raise InvalidNameError("A display name cannot contain invisible or control characters.")
    return name


def name_key(name: str) -> str:
    """What two names are compared by: full case folding, then NFC.

    Folding rather than `lower()`, so `Strauß` and `STRAUSS` collide.
    """
    return unicodedata.normalize("NFC", name.casefold())


def with_suffix(base: str, n: int) -> str:
    """`base` with ` n` appended, cut so the result stays within the limit."""
    suffix = f" {n}"
    return base[: MAX_LENGTH - len(suffix)] + suffix


def first_free(base: str, taken: AbstractSet[str]) -> str:
    """The first of `base`, `base 2`, `base 3` … whose key is not in `taken`."""
    if name_key(base) not in taken:
        return base
    n = 2
    while True:
        candidate = with_suffix(base, n)
        if name_key(candidate) not in taken:
            return candidate
        n += 1


def _clean(raw: str) -> str:
    """`raw` with every refused character dropped, trimmed, cut to the limit."""
    kept = "".join(char for char in stored_form(raw) if not _refused(char))
    return stored_form(kept)[:MAX_LENGTH].strip()


def provision_name(raw: str, email: str) -> str:
    """A valid base name for a first sign-in, which is never refused over a name.

    The identity provider's name with the refused characters dropped; failing
    that the email's local part; failing that "user".
    """
    return _clean(raw) or _clean(email.split("@", 1)[0]) or _FALLBACK


def dedupe(rows: Sequence[tuple[uuid.UUID, str, str]]) -> dict[uuid.UUID, str]:
    """The stored name for every row, with duplicates suffixed.

    `rows` are `(id, display_name, email)` already in `(created_at, id)` order.
    The oldest of each key keeps its name. The key of every kept name is reserved
    before anything is suffixed, so a duplicate never takes a name that another
    account really holds (`X, X, X 2` renames the second `X` to `X 3`).
    """
    tidied: list[tuple[uuid.UUID, str]] = []
    for user_id, name, email in rows:
        tidy = stored_form(name)
        if not tidy:
            tidy = _clean(email.split("@", 1)[0]) or _FALLBACK
        tidied.append((user_id, tidy))

    result: dict[uuid.UUID, str] = {}
    taken: set[str] = set()
    duplicates: list[tuple[uuid.UUID, str]] = []
    for user_id, name in tidied:
        key = name_key(name)
        if key in taken:
            duplicates.append((user_id, name))
        else:
            taken.add(key)
            result[user_id] = name

    for user_id, name in duplicates:
        renamed = first_free(name, taken)
        taken.add(name_key(renamed))
        result[user_id] = renamed
    return result
