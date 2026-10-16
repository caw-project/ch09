"""What a display name may be, and what a taken one becomes (issue gh-3, Req 1-3).

Pure rules, so they are proven here and not through a database: trimming,
length after trimming, the characters refused, how an identity provider's name
is cleaned rather than refused, and the suffix sequence a first sign-in walks.
"""

from __future__ import annotations

from itertools import islice

import pytest

from auth.names import (
    MAX_LENGTH,
    InvalidDisplayNameError,
    candidates,
    provisional_name,
    validate_display_name,
)

REQUIRED = "A display name is required."
TOO_LONG = "A display name is at most 100 characters."
INVISIBLE = "A display name cannot contain control or invisible characters."

# Built with chr() so the invisible characters are visible in the source.
ZWSP = chr(0x200B)  # zero-width space, category Cf
BELL = chr(0x07)  # category Cc
LINE_SEP = chr(0x2028)  # category Zl
PRIVATE_USE = chr(0xE000)  # category Co


def test_a_name_is_trimmed() -> None:
    """Without trimming, "  Ada L  " and "Ada L" are two names and the padding shows."""
    assert validate_display_name("  Ada L  ") == "Ada L"
    assert validate_display_name("Ada  L") == "Ada  L"


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_blank_name_is_required(raw: str) -> None:
    """Whitespace alone is nothing — a build that checks length before trimming accepts it."""
    with pytest.raises(InvalidDisplayNameError) as caught:
        validate_display_name(raw)

    assert caught.value.message == REQUIRED


def test_length_is_counted_after_trimming() -> None:
    """Padding must not push a 100-character name over, and 101 real ones must."""
    assert validate_display_name("  " + "a" * 100 + "  ") == "a" * 100
    assert MAX_LENGTH == 100

    with pytest.raises(InvalidDisplayNameError) as caught:
        validate_display_name("a" * 101)

    assert caught.value.message == TOO_LONG


@pytest.mark.parametrize(
    "raw",
    ["Ada" + ZWSP, "Ada" + BELL, "Ada" + LINE_SEP, "Ada" + PRIVATE_USE],
    ids=["zero-width space (Cf)", "bell (Cc)", "line separator (Zl)", "private use (Co)"],
)
def test_invisible_and_control_characters_are_refused(raw: str) -> None:
    """A name that looks like another's but carries a zero-width mark is an impersonation."""
    with pytest.raises(InvalidDisplayNameError) as caught:
        validate_display_name(raw)

    assert caught.value.message == INVISIBLE


@pytest.mark.parametrize("raw", ["Émile", "Ada 🚀", "李雷"])
def test_ordinary_unicode_is_kept(raw: str) -> None:
    """The positive half: refusing by category must not refuse accents, emoji or CJK."""
    assert validate_display_name(raw) == raw


def test_an_idp_name_is_cleaned_not_refused() -> None:
    """Sign-in never fails over a name (Req 3): the provider's is cleaned instead."""
    assert provisional_name(" Sam" + ZWSP + " ") == "Sam"
    assert provisional_name("a" * 120) == "a" * 100
    assert provisional_name(ZWSP) == "user"
    assert provisional_name("   ") == "user"


def test_suffixes_start_at_two() -> None:
    """The first free name is X, then X 2, X 3 — never "X 1"."""
    assert list(islice(candidates("Sam"), 3)) == ["Sam", "Sam 2", "Sam 3"]


def test_a_suffix_never_makes_a_name_too_long() -> None:
    """A 100-character base must be cut to leave room, or the suffixed name is refused."""
    found = list(islice(candidates("a" * 100), 10))

    assert found[0] == "a" * 100
    assert len(found[1]) <= MAX_LENGTH
    assert found[1].endswith(" 2")
    assert len(found[9]) <= MAX_LENGTH
    assert found[9].endswith(" 10")


def test_a_cut_stem_loses_its_trailing_space() -> None:
    """Cutting between words must not leave "a  10" with a double space."""
    base = "a" * 96 + " bcd"  # 100 chars; the cut for " 10" lands just after the space
    found = list(islice(candidates(base), 10))

    assert "  " not in found[9]
    assert found[9].endswith(" 10")
