"""The display-name rules, as pure functions (issue gh-3, Req 1 to 4).

Nothing here touches a database: the rules are over strings, and the migration and
the routes call these same functions, so what is proven here is proven for both.

Every character that is invisible or awkward to read is built with `chr()` from a
named constant: the lint hook rewrites a `\\u` escape into the raw character, which
would leave a file nobody can read and an editor can swallow.
"""

from __future__ import annotations

import uuid

import pytest

from auth.names import (
    MAX_LENGTH,
    InvalidDisplayNameError,
    candidates,
    dedupe,
    from_idp,
    name_key,
    normalise,
    normalise_display_name,
)

REQUIRED = "A display name is required."
TOO_LONG = "A display name is at most 100 characters."
INVISIBLE = "A display name cannot contain invisible or control characters."

# Characters, by what they are rather than how they look.
NBSP = chr(0x00A0)
ZWSP = chr(0x200B)  # Cf
HANGUL_FILLER = chr(0x3164)  # Lo, default-ignorable
CGJ = chr(0x034F)  # Mn, default-ignorable
BELL = chr(0x07)  # Cc
LRM = chr(0x200E)  # Cf
SURROGATE = chr(0xD800)  # Cs
PRIVATE_USE = chr(0xE000)  # Co
UNASSIGNED = chr(0x0378)  # Cn
LINE_SEP = chr(0x2028)  # Zl
PARA_SEP = chr(0x2029)  # Zp
CHOSEONG_FILLER = chr(0x115F)  # Lo, default-ignorable
HALFWIDTH_FILLER = chr(0xFFA0)  # Lo, default-ignorable
VS16 = chr(0xFE0F)  # Mn, default-ignorable
BRAILLE_BLANK = chr(0x2800)  # So: visible, so allowed (Decided 5)
E_ACUTE = chr(0x00E9)
COMBINING_ACUTE = chr(0x0301)
E_DIAERESIS = chr(0x00EB)
SHARP_S = chr(0x00DF)
E_ACUTE_UPPER = chr(0x00C9)

JOSE = "Jos" + E_ACUTE  # precomposed
JOSE_DECOMPOSED = "Jose" + COMBINING_ACUTE
CJK = "".join(chr(c) for c in (0x674E, 0x5C0F, 0x9F8D))


def row(n: int, name: str) -> tuple[uuid.UUID, str]:
    return (uuid.UUID(int=n), name)


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


# --------------------------------------------------------------------------
# What is refused, and what is kept (Req 1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param("Grace" + ZWSP, INVISIBLE, id="zero-width-space-Cf"),
        pytest.param("Grace" + HANGUL_FILLER, INVISIBLE, id="hangul-filler-default-ignorable"),
        pytest.param("Gr" + CGJ + "ace", INVISIBLE, id="combining-grapheme-joiner"),
        pytest.param("Grace" + BELL, INVISIBLE, id="bell-Cc"),
        pytest.param(NBSP, REQUIRED, id="no-break-space-empty-after-trim"),
    ],
)
def test_the_issues_refused_examples_are_refused(raw: str, message: str) -> None:
    with pytest.raises(InvalidDisplayNameError) as caught:
        normalise_display_name(raw)

    assert str(caught.value) == message


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        pytest.param(JOSE, JOSE, id="precomposed"),
        pytest.param(JOSE_DECOMPOSED, JOSE, id="e-plus-combining-acute"),
        pytest.param("Zo" + E_DIAERESIS, "Zo" + E_DIAERESIS, id="diaeresis"),
        pytest.param(CJK, CJK, id="cjk"),
        pytest.param("O'Brien", "O'Brien", id="apostrophe"),
        pytest.param("Ada  Lovelace", "Ada  Lovelace", id="inner-spaces-kept"),
    ],
)
def test_the_issues_accepted_examples_are_stored_as_given(raw: str, stored: str) -> None:
    assert normalise_display_name(raw) == stored


@pytest.mark.parametrize(
    "refused",
    [
        pytest.param(BELL, id="Cc"),
        pytest.param(LRM, id="Cf"),
        pytest.param(SURROGATE, id="Cs"),
        pytest.param(PRIVATE_USE, id="Co"),
        pytest.param(UNASSIGNED, id="Cn"),
        pytest.param(LINE_SEP, id="Zl"),
        pytest.param(PARA_SEP, id="Zp"),
    ],
)
def test_each_refused_category_on_its_own(refused: str) -> None:
    """Between two letters, so trimming can't remove it before the check sees it."""
    with pytest.raises(InvalidDisplayNameError) as caught:
        normalise_display_name(f"A{refused}B")

    assert str(caught.value) == INVISIBLE
    # The same name without the character is fine: the character is what refused it.
    assert normalise_display_name("AB") == "AB"


@pytest.mark.parametrize(
    "ignorable",
    [
        pytest.param(CHOSEONG_FILLER, id="hangul-choseong-filler-Lo"),
        pytest.param(HALFWIDTH_FILLER, id="halfwidth-hangul-filler-Lo"),
        pytest.param(VS16, id="variation-selector-16-Mn"),
    ],
)
def test_default_ignorables_outside_those_categories_are_refused(ignorable: str) -> None:
    """Not Cc/Cf/...: only the `Default_Ignorable_Code_Point` property catches these."""
    with pytest.raises(InvalidDisplayNameError) as caught:
        normalise_display_name(f"A{ignorable}B")

    assert str(caught.value) == INVISIBLE


def test_visible_blank_symbols_are_allowed() -> None:
    """Decided 5: Braille blank is a symbol Unicode counts as visible, so it stays allowed."""
    assert normalise_display_name(BRAILLE_BLANK) == BRAILLE_BLANK
    assert normalise_display_name(f"A{BRAILLE_BLANK}B") == f"A{BRAILLE_BLANK}B"


def test_whitespace_is_trimmed_from_both_ends_only() -> None:
    assert normalise_display_name("  Ada\n") == "Ada"
    assert normalise_display_name("\n\tAda  L ") == "Ada  L"
    assert normalise_display_name("Ada  L") == "Ada  L"


def test_normalise_composes_and_trims_but_checks_nothing() -> None:
    assert normalise(" " + JOSE_DECOMPOSED + " ") == JOSE
    assert normalise("Gr" + CGJ + "ace") == "Gr" + CGJ + "ace"


def test_length_is_counted_after_normalising() -> None:
    assert MAX_LENGTH == 100
    decomposed = ("e" + COMBINING_ACUTE) * 100  # 200 code points raw, 100 once composed
    assert len(decomposed) == 200
    assert normalise_display_name(decomposed) == E_ACUTE * 100

    assert normalise_display_name("x" * 100) == "x" * 100
    assert normalise_display_name(" " + "x" * 100 + " ") == "x" * 100
    with pytest.raises(InvalidDisplayNameError) as caught:
        normalise_display_name("x" * 101)
    assert str(caught.value) == TOO_LONG


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_after_trimming_is_required(raw: str) -> None:
    with pytest.raises(InvalidDisplayNameError) as caught:
        normalise_display_name(raw)

    assert str(caught.value) == REQUIRED


# --------------------------------------------------------------------------
# The key the database compares (Decisions 14 and 15)
# --------------------------------------------------------------------------


def test_the_key_ignores_case_and_form() -> None:
    assert name_key(JOSE) == name_key("JOS" + E_ACUTE_UPPER)
    assert name_key(JOSE) == name_key(JOSE_DECOMPOSED)
    assert name_key("Stra" + SHARP_S + "e") == name_key("STRASSE")


def test_the_key_keeps_different_names_apart() -> None:
    assert name_key("Ada") != name_key("Ada L")
    assert name_key("Ada Lovelace") != name_key("Ada  Lovelace")


# --------------------------------------------------------------------------
# First sign-in (Req 3)
# --------------------------------------------------------------------------


def test_candidates_count_from_two() -> None:
    it = candidates("Sam")

    assert [next(it) for _ in range(3)] == ["Sam", "Sam 2", "Sam 3"]


def test_a_suffix_never_makes_a_name_too_long() -> None:
    it = candidates("x" * 100)
    first, second = next(it), next(it)

    assert first == "x" * 100
    assert second == "x" * 98 + " 2"
    assert len(second) == 100


def test_a_cut_that_ends_in_a_space_has_it_stripped_before_the_suffix() -> None:
    base = "x" * 97 + " yy"  # 100 characters; cutting to 98 leaves "x"*97 + " "
    assert len(base) == 100

    it = candidates(base)
    assert next(it) == base
    assert next(it) == "x" * 97 + " 2"


def test_an_idp_name_is_cleaned_not_refused() -> None:
    assert from_idp("Grace" + ZWSP, "grace@x.dev") == "Grace"
    assert from_idp("x" * 150, "grace@x.dev") == "x" * 100


def test_an_idp_name_is_composed_after_dropping() -> None:
    """Dropping the CGJ lets `e` + U+0301 compose; the first NFC could not."""
    assert from_idp("e" + CGJ + COMBINING_ACUTE, "e@x.dev") == E_ACUTE
    # ...and the positive: `normalise` alone leaves the CGJ in place.
    assert CGJ in normalise("e" + CGJ + COMBINING_ACUTE)


def test_an_unusable_idp_name_falls_back_to_the_email_then_user() -> None:
    assert from_idp(ZWSP, "zed@x.dev") == "zed"
    assert from_idp(ZWSP, ZWSP + "@x.dev") == "user"


# --------------------------------------------------------------------------
# The migration's de-duplication (Req 4, Decisions 21 and 22)
# --------------------------------------------------------------------------


def test_dedupe_keeps_the_oldest_and_suffixes_the_rest() -> None:
    rows = [row(1, "Sam"), row(2, "sam"), row(3, "SAM")]

    assert dedupe(rows) == {uid(2): "sam 2", uid(3): "SAM 3"}


def test_dedupe_finds_duplicates_only_normalising_reveals() -> None:
    rows = [row(1, JOSE), row(2, " jose" + COMBINING_ACUTE)]

    assert dedupe(rows) == {uid(2): "jos" + E_ACUTE + " 2"}


def test_dedupe_skips_a_suffix_another_row_holds() -> None:
    rows = [row(1, "Sam"), row(2, "Sam"), row(3, "Sam 2")]

    assert dedupe(rows) == {uid(2): "Sam 3"}


def test_dedupe_reports_a_trimmed_name_that_collides_with_nothing() -> None:
    assert dedupe([row(1, " Ada ")]) == {uid(1): "Ada"}
    assert dedupe([row(1, "Ada")]) == {}


def test_dedupe_gives_an_empty_name_the_word_user() -> None:
    assert dedupe([row(1, "   ")]) == {uid(1): "user"}
