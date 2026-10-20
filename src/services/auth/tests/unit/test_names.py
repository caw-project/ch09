"""The display-name rules (issue gh-3, Req 1-4), as pure functions.

One module owns them so the application, the database's comparison key and the
migration can never disagree about what a name is. Every invisible character is
a named constant below, so a reader can see which one a test means.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from auth import names

LENGTH = "A display name must be 1 to 100 characters."
CHARACTERS = "A display name cannot contain invisible or control characters."

ZWSP = chr(0x200B)  # zero-width space, Cf and default-ignorable
HANGUL_FILLER = chr(0x3164)  # default-ignorable, not Cf
CGJ = chr(0x034F)  # combining grapheme joiner, default-ignorable, not Cf
NBSP = chr(0x00A0)  # whitespace to str.strip()
ARABIC_NUMBER_SIGN = chr(0x0600)  # Cf, and not default-ignorable
SURROGATE = chr(0xD800)  # Cs
PRIVATE_USE = chr(0xE000)  # Co
UNASSIGNED = chr(0x0378)  # Cn
LINE_SEPARATOR = chr(0x2028)  # Zl
PARAGRAPH_SEPARATOR = chr(0x2029)  # Zp
VARIATION_SELECTOR_16 = chr(0xFE0F)  # default-ignorable, not Cf
HANGUL_CHOSEONG_FILLER = chr(0x115F)  # default-ignorable, not Cf
BRAILLE_BLANK = chr(0x2800)  # a visible symbol to Unicode, so allowed
E_ACUTE = chr(0x00E9)  # precomposed e-acute
COMBINING_ACUTE = chr(0x0301)
E_DIAERESIS = chr(0x00EB)
SHARP_S = chr(0x00DF)
CAPITAL_E_ACUTE = chr(0x00C9)

JOSE = "Jos" + E_ACUTE
JOSE_COMBINING = "Jose" + COMBINING_ACUTE

T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = T1 + timedelta(days=1)
T3 = T1 + timedelta(days=2)


def stored(name: str, created_at: datetime, email: str = "x@example.com", id_=None):
    return names.StoredName(
        id=id_ or uuid.uuid4(), display_name=name, email=email, created_at=created_at
    )


# --------------------------------------------------------------------------
# Req 1 - what a stored name is
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Grace" + ZWSP, CHARACTERS),
        ("Grace" + HANGUL_FILLER, CHARACTERS),
        ("Gr" + CGJ + "ace", CHARACTERS),
        ("Grace\x07", CHARACTERS),
        (NBSP, LENGTH),
        (" ", LENGTH),
    ],
)
def test_the_issues_refused_examples_are_refused(raw: str, message: str) -> None:
    """Each example Req 1 names is refused with its own rule's text."""
    with pytest.raises(names.InvalidDisplayNameError) as caught:
        names.validate(raw)

    assert caught.value.messages == [message]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (JOSE, JOSE),
        (JOSE_COMBINING, JOSE),
        ("Zo" + E_DIAERESIS, "Zo" + E_DIAERESIS),
        ("李小龍", "李小龍"),
        ("O'Brien", "O'Brien"),
        ("Ada  Lovelace", "Ada  Lovelace"),
    ],
)
def test_the_issues_accepted_examples_are_stored_normalised(raw: str, expected: str) -> None:
    """Precomposed and combining José both store precomposed; inner spaces stay."""
    assert names.validate(raw) == expected


def test_surrounding_whitespace_is_trimmed() -> None:
    """`str.strip()` - tabs and newlines as well as spaces, and Unicode spaces."""
    assert names.validate("\t Ada \n") == "Ada"
    assert names.normalise(NBSP + "Ada" + NBSP) == "Ada"


@pytest.mark.parametrize(
    "char",
    [
        "\x07",  # Cc
        ARABIC_NUMBER_SIGN,  # Cf
        SURROGATE,  # Cs
        PRIVATE_USE,  # Co
        UNASSIGNED,  # Cn
        LINE_SEPARATOR,  # Zl
        PARAGRAPH_SEPARATOR,  # Zp
        HANGUL_FILLER,  # default-ignorable only
        CGJ,  # default-ignorable only
        VARIATION_SELECTOR_16,  # default-ignorable only
        HANGUL_CHOSEONG_FILLER,  # default-ignorable only
    ],
)
def test_each_refused_category_alone(char: str) -> None:
    """Each refused class on its own, in an otherwise fine name: no other class covers it."""
    with pytest.raises(names.InvalidDisplayNameError) as caught:
        names.validate(f"Ab{char}c")

    assert caught.value.messages == [CHARACTERS]
    assert names.is_refused(char)


def test_braille_blank_stays_allowed() -> None:
    """DA 5: Unicode counts U+2800 a visible symbol, so it is the positive beside the table."""
    assert names.validate(f"Ab{BRAILLE_BLANK}c") == f"Ab{BRAILLE_BLANK}c"
    assert not names.is_refused(BRAILLE_BLANK)
    assert not names.is_refused("a")


def test_length_is_counted_after_trimming_and_nfc() -> None:
    """100 passes and 101 fails; padding is not counted; NFC shortens before the count."""
    assert names.validate("a" * 100) == "a" * 100
    with pytest.raises(names.InvalidDisplayNameError) as caught:
        names.validate("a" * 101)
    assert caught.value.messages == [LENGTH]

    assert names.validate(" " + "a" * 100 + " ") == "a" * 100
    # 99 a's + "e" + a combining accent is 101 code points raw, 100 once composed.
    assert names.validate("a" * 99 + "e" + COMBINING_ACUTE) == "a" * 99 + E_ACUTE


def test_a_name_breaking_both_rules_lists_both() -> None:
    """Every broken rule is reported, length first."""
    with pytest.raises(names.InvalidDisplayNameError) as caught:
        names.validate("a" * 100 + ZWSP)

    assert caught.value.messages == [LENGTH, CHARACTERS]


def test_the_rule_texts_are_the_ones_the_spa_will_show() -> None:
    assert names.LENGTH_RULE == LENGTH
    assert names.CHARACTER_RULE == CHARACTERS
    assert names.TAKEN == "That name is already taken."
    assert names.MAX_LENGTH == 100


# --------------------------------------------------------------------------
# Req 2 - the comparison key
# --------------------------------------------------------------------------


def test_the_key_ignores_case_and_normalisation() -> None:
    """Full case folding, not `lower()`: the sharp s and `STRASSE` are one name."""
    assert names.name_key(JOSE) == names.name_key("JOS" + CAPITAL_E_ACUTE)
    assert names.name_key(JOSE) == names.name_key("jos" + E_ACUTE)
    assert names.name_key("Stra" + SHARP_S + "e") == names.name_key("STRASSE")
    assert names.name_key("Ada") != names.name_key("Ada 2")


# --------------------------------------------------------------------------
# Req 3 - names handed over by an identity provider
# --------------------------------------------------------------------------


def test_provisional_cleans_cuts_and_falls_back() -> None:
    """A sign-in never refuses over a name, so a bad one is cleaned rather than rejected."""
    assert names.provisional("Sam" + ZWSP, "fallback") == "Sam"
    assert names.provisional("a" * 150, "fallback") == "a" * 100
    assert names.provisional(ZWSP, "sam") == "sam"
    assert names.provisional(ZWSP, ZWSP) == "user"


def test_candidates_are_the_name_then_numbered_suffixes() -> None:
    """`X`, `X 2`, `X 3` - and a long base is cut so the suffix still fits in 100."""
    first = names.candidates("X")
    assert [next(first) for _ in range(3)] == ["X", "X 2", "X 3"]

    long = names.candidates("a" * 100)
    got = [next(long) for _ in range(10)]
    assert got[0] == "a" * 100
    assert all(len(c) <= 100 for c in got)
    assert got[1] == "a" * 98 + " 2"
    assert got[9] == "a" * 97 + " 10"


# --------------------------------------------------------------------------
# Req 4 - existing duplicates
# --------------------------------------------------------------------------


def test_deduplicate_keeps_the_oldest() -> None:
    """Input newest first, so keeping "the first row" would keep the wrong one."""
    newest, middle, oldest = stored("Sam", T3), stored("Sam", T2), stored("Sam", T1)

    renamed = names.deduplicate([newest, middle, oldest])

    assert renamed == {middle.id: "Sam 2", newest.id: "Sam 3"}


def test_deduplicate_breaks_a_created_at_tie_by_id() -> None:
    """The lower id keeps the name when two accounts were created at one instant."""
    low = stored("Sam", T1, id_=uuid.UUID(int=1))
    high = stored("Sam", T1, id_=uuid.UUID(int=2))

    assert names.deduplicate([high, low]) == {high.id: "Sam 2"}
    assert names.deduplicate([low, high]) == {high.id: "Sam 2"}


def test_deduplicate_finds_duplicates_only_normalising_reveals() -> None:
    """` José ` and `JOSÉ` differ raw and collide once trimmed and folded."""
    older = stored(" " + JOSE + " ", T1)
    newer = stored("JOS" + CAPITAL_E_ACUTE, T2)

    renamed = names.deduplicate([newer, older])

    assert renamed == {older.id: JOSE, newer.id: "JOS" + CAPITAL_E_ACUTE + " 2"}


def test_deduplicate_leaves_clean_unique_names_out() -> None:
    """Unchanged rows are absent, so the migration touches only what it must."""
    assert names.deduplicate([stored("Ada", T1), stored("Grace", T2)]) == {}


def test_deduplicate_skips_a_suffix_someone_holds() -> None:
    """A third account already named `sam 2` is not displaced, so the new Sam takes `Sam 3`."""
    holder = stored("sam 2", T3)
    first = stored("Sam", T1)
    second = stored("Sam", T2)

    renamed = names.deduplicate([holder, second, first])

    assert renamed == {second.id: "Sam 3"}
    assert holder.id not in renamed


def test_deduplicate_gives_an_empty_name_the_email_local_part() -> None:
    """`"   "` normalises to nothing; the sign-in fallback names it instead."""
    blank = stored("   ", T1, email="grace@x.example")

    assert names.deduplicate([blank]) == {blank.id: "grace"}
