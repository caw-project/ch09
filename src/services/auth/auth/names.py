"""Display-name rules, as pure functions (issue gh-3; register D46).

Nothing here does I/O. The routes, first sign-in and migration `0002` all call
these same functions, so the rule a user is held to, the rule a stored name was
cleaned by and the rule the unique index compares by cannot drift apart.

A name is stored in one form — trimmed and NFC-composed — and compared through
`name_key`, a case-folded form computed *here* rather than by Postgres: the
database's `lower()` follows its locale and provider, which differ between the
Compose image, testcontainers and a managed Postgres.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator, Sequence
from uuid import UUID

MAX_LENGTH = 100

_REQUIRED = "A display name is required."
_TOO_LONG = f"A display name is at most {MAX_LENGTH} characters."
_INVISIBLE = "A display name cannot contain invisible or control characters."

# What a name may not contain: control, format, surrogate, private-use, unassigned,
# and the line and paragraph separators.
_REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Unicode 15.0 `Default_Ignorable_Code_Point` (DerivedCoreProperties.txt). Python's
# `unicodedata` has no such property, and these characters render as nothing while
# many of them sit outside the categories above (a Hangul filler is a letter).
# Braille blank U+2800 is deliberately absent: it is a visible symbol (Decided 5).
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
    """A name the rules refuse; `str(exc)` is the message for `errors.displayName`."""


def normalise(raw: str) -> str:
    """Trim and compose to NFC. Checks nothing."""
    return unicodedata.normalize("NFC", raw.strip())


def is_refused(ch: str) -> bool:
    """Whether a name may not contain this character."""
    if unicodedata.category(ch) in _REFUSED_CATEGORIES:
        return True
    code = ord(ch)
    return any(low <= code <= high for low, high in _DEFAULT_IGNORABLE)


def normalise_display_name(raw: str) -> str:
    """The stored form of a name a user typed, or raise why it is refused.

    Length is counted in code points of the *stored* form, after trimming and
    NFC — which is why this is not a Pydantic constraint (it would count the raw
    input).
    """
    name = normalise(raw)
    if not name:
        raise InvalidDisplayNameError(_REQUIRED)
    if len(name) > MAX_LENGTH:
        raise InvalidDisplayNameError(_TOO_LONG)
    if any(is_refused(ch) for ch in name):
        raise InvalidDisplayNameError(_INVISIBLE)
    return name


def name_key(name: str) -> str:
    """What the unique index compares: full Unicode case folding, then NFC.

    Folding rather than `lower()` makes `Straße` collide with `STRASSE`; the
    second NFC is because folding can leave a string uncomposed.
    """
    return unicodedata.normalize("NFC", name.casefold())


def candidates(base: str) -> Iterator[str]:
    """`base`, then `base 2`, `base 3`, … — each still a valid name.

    The base is cut so that the suffix never takes the name past `MAX_LENGTH`,
    and right-stripped so the cut cannot leave a space before the suffix.
    """
    yield base
    n = 2
    while True:
        suffix = f" {n}"
        yield f"{base[: MAX_LENGTH - len(suffix)].rstrip()}{suffix}"
        n += 1


def _cleaned(raw: str) -> str:
    """Normalise, drop refused characters, normalise again, cut to the limit.

    The second pass matters: dropping a joiner can leave `e` and a combining
    accent side by side, which only now compose.
    """
    kept = "".join(ch for ch in normalise(raw) if not is_refused(ch))
    return normalise(normalise(kept)[:MAX_LENGTH])


def from_idp(raw: str, email: str) -> str:
    """A usable name from whatever an identity provider sent.

    Sign-in never refuses over a name: refused characters are dropped, and a
    name left empty falls back to the email's local part, then to "user".
    """
    return _cleaned(raw) or _cleaned(email.partition("@")[0]) or "user"


def dedupe(rows: Sequence[tuple[UUID, str]]) -> dict[UUID, str]:
    """Migration 0002: the new stored name of every row whose name must change.

    `rows` are `(id, display_name)`, oldest first. Each name is normalised (and
    an empty one becomes "user"); the oldest holder of a key keeps it, and a
    later one takes the first candidate that no row's own name holds and that
    was not handed out earlier. Only changed rows are returned.
    """
    own = {user_id: normalise(name) or "user" for user_id, name in rows}
    held = {name_key(name) for name in own.values()}
    claimed: set[str] = set()
    changed: dict[UUID, str] = {}

    for user_id, name in rows:
        base = own[user_id]
        if name_key(base) in claimed:
            base = next(c for c in candidates(base) if name_key(c) not in held | claimed)
        claimed.add(name_key(base))
        if base != name:
            changed[user_id] = base
    return changed
