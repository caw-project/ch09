"""The display-name rules (issue gh-3, Req 1 to 4; register D46).

Pure functions over strings, so every rule is proven here and the integration
tests only prove that the routes and the index use them. Characters are built
with `chr()` and named: a literal zero-width space in a test file is invisible
to the next person reading it, which is the very thing the rules refuse.
"""

from __future__ import annotations

import unicodedata
import uuid

import pytest

from auth.names import (
    InvalidNameError,
    dedupe,
    first_free,
    name_key,
    normalise_display_name,
    provision_name,
    stored_form,
    with_suffix,
)

E_ACUTE = chr(0xE9)
COMBINING_ACUTE = chr(0x301)
NFC_JOSE = "Jos" + E_ACUTE
NFD_JOSE = "Jose" + COMBINING_ACUTE

ZERO_WIDTH_SPACE = chr(0x200B)  # Cf
HANGUL_FILLER = chr(0x3164)  # default-ignorable, not Cf
GRAPHEME_JOINER = chr(0x34F)  # default-ignorable, not Cf
NO_BREAK_SPACE = chr(0xA0)  # whitespace: trimmed away
BRAILLE_BLANK = chr(0x2800)  # a visible symbol, accepted (Decided already 5)

_REFUSED_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


@pytest.mark.parametrize(
    "raw",
    [
        "Grace" + ZERO_WIDTH_SPACE,
        "Grace" + HANGUL_FILLER,
        "Gr" + GRAPHEME_JOINER + "ace",
        "Grace\x07",
        " ",
        NO_BREAK_SPACE,
    ],
)
def test_refused_examples(raw: str) -> None:
    """Each example the issue lists is refused — an invisible name is an impersonation."""
    with pytest.raises(InvalidNameError):
        normalise_display_name(raw)


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        (NFC_JOSE, NFC_JOSE),
        (NFD_JOSE, NFC_JOSE),
        ("Zo" + chr(0xEB), "Zo" + chr(0xEB)),
        ("李小龍", "李小龍"),
        ("O'Brien", "O'Brien"),
        ("Ada  Lovelace", "Ada  Lovelace"),
        (" ada ", "ada"),
        (BRAILLE_BLANK, BRAILLE_BLANK),
    ],
)
def test_accepted_examples(raw: str, stored: str) -> None:
    """Valid names are kept, composed to NFC and trimmed; inner spaces stay."""
    assert normalise_display_name(raw) == stored


@pytest.mark.parametrize(
    "char",
    [
        chr(0x1F),  # Cc
        chr(0x2066),  # Cf
        chr(0xD800),  # Cs
        chr(0xE000),  # Co
        chr(0x378),  # Cn
        chr(0x2028),  # Zl
        chr(0x2029),  # Zp
    ],
    ids=["Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"],
)
def test_each_refused_category_alone(char: str) -> None:
    """Every general category the rule lists refuses on its own.

    The character sits inside the name: `str.strip()` would remove a trailing
    line separator and the test would prove only the trim.
    """
    # The fixture must really be in the category it claims, or this proves nothing.
    assert unicodedata.category(char) in _REFUSED_CATEGORIES

    with pytest.raises(InvalidNameError):
        normalise_display_name(f"Ab{char}cd")

    assert normalise_display_name("Abcd") == "Abcd"


@pytest.mark.parametrize("code", [0x115F, 0xFE0F, 0xE0100, 0x17B4])
def test_default_ignorables_outside_cf(code: int) -> None:
    """Characters that are default-ignorable but not Cf are refused too.

    A build that tests only the general category lets these through.
    """
    char = chr(code)
    assert unicodedata.category(char) not in _REFUSED_CATEGORIES

    with pytest.raises(InvalidNameError):
        normalise_display_name(f"Ab{char}cd")


def test_length_after_trim_and_nfc() -> None:
    """1 to 100 code points, counted after trimming and composing, at both ends."""
    assert normalise_display_name("a" * 100) == "a" * 100
    assert normalise_display_name(f"  {'a' * 100}  ") == "a" * 100
    # 99 letters + e + combining acute = 101 code points before NFC, 100 after.
    decomposed = "a" * 99 + "e" + COMBINING_ACUTE
    assert len(decomposed) == 101
    assert normalise_display_name(decomposed) == "a" * 99 + E_ACUTE

    with pytest.raises(InvalidNameError):
        normalise_display_name("a" * 101)
    with pytest.raises(InvalidNameError):
        normalise_display_name("")


def test_stored_form_trims_and_composes_without_validating() -> None:
    """The migration's step and the no-op check: tidy the name, never refuse it."""
    assert stored_form(f" {NFD_JOSE} ") == NFC_JOSE
    assert stored_form(f" Ada{ZERO_WIDTH_SPACE} ") == f"Ada{ZERO_WIDTH_SPACE}"
    assert stored_form("a" * 150) == "a" * 150


def test_key_ignores_case_and_form() -> None:
    """One key for names that differ only in case or Unicode form — and only those."""
    assert name_key(NFC_JOSE) == name_key(NFD_JOSE) == name_key("JOS" + chr(0xC9))
    # Full case folding, not `lower()`: eszett is "ss".
    assert name_key("Strau" + chr(0xDF)) == name_key("STRAUSS")
    assert name_key("Ada") != name_key("Adb")


def test_first_free() -> None:
    """The first free of X, X 2, X 3 — `taken` holds keys, so case never matters."""
    assert first_free("X", set()) == "X"
    assert first_free("X", {"x"}) == "X 2"
    assert first_free("X", {"x", "x 2"}) == "X 3"
    assert first_free("X", {"x 2"}) == "X"
    assert first_free("Sam", {"sam", "sam 2", "sam 4"}) == "Sam 3"


def test_first_free_keeps_the_name_inside_the_limit() -> None:
    """A suffix never pushes a generated name past 100 code points."""
    base = "a" * 100

    second = first_free(base, {name_key(base)})
    assert second == "a" * 98 + " 2"

    third = first_free(base, {name_key(base), name_key(second)})
    assert third == "a" * 98 + " 3"
    assert with_suffix(base, 10) == "a" * 97 + " 10"


def test_provision_name() -> None:
    """A first sign-in's name is cleaned, never refused (Req 3)."""
    assert provision_name("Gr" + ZERO_WIDTH_SPACE + "ace", "grace@x.dev") == "Grace"
    assert provision_name(ZERO_WIDTH_SPACE, "ada@x.dev") == "ada"
    assert provision_name("  ", "@x.dev") == "user"
    assert provision_name("a" * 150, "a@x.dev") == "a" * 100


def _row(name: str, email: str = "u@x.dev") -> tuple[uuid.UUID, str, str]:
    return (uuid.uuid4(), name, email)


def test_dedupe_keeps_the_oldest_and_suffixes_in_order() -> None:
    """The oldest keeps the name; the others take 2, 3 … in age order."""
    first, second, third = _row("Sam"), _row("sam"), _row("SAM ")

    renamed = dedupe([first, second, third])

    assert renamed[first[0]] == "Sam"
    assert renamed[second[0]] == "sam 2"
    assert renamed[third[0]] == "SAM 3"


def test_dedupe_never_takes_a_kept_name() -> None:
    """`X, X, X 2`: the second X skips 2 because the real "X 2" is kept."""
    first, second, third = _row("X"), _row("X"), _row("X 2")

    renamed = dedupe([first, second, third])

    assert renamed[first[0]] == "X"
    assert renamed[second[0]] == "X 3"
    assert renamed[third[0]] == "X 2"


def test_dedupe_finds_duplicates_only_normalising_reveals() -> None:
    """Two names that are the same only once trimmed and composed are duplicates."""
    first, second = _row(NFC_JOSE), _row(f" {NFD_JOSE}")

    renamed = dedupe([first, second])

    assert renamed[first[0]] == NFC_JOSE
    assert renamed[second[0]] == f"{NFC_JOSE} 2"


def test_dedupe_names_an_empty_name() -> None:
    """NOT NULL and a unique key need a name: the email's local part, else "user"."""
    blank_with_email, blank_without = _row("   ", "bob@x.dev"), _row("", "@x.dev")

    renamed = dedupe([blank_with_email, blank_without])

    assert renamed[blank_with_email[0]] == "bob"
    assert renamed[blank_without[0]] == "user"


def test_dedupe_returns_every_row_trimmed() -> None:
    """Every row comes back, tidied, whether or not it was a duplicate."""
    alone = _row(f"  {NFD_JOSE} ")

    assert dedupe([alone]) == {alone[0]: NFC_JOSE}
