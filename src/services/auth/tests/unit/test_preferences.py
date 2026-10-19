"""Validating a preferences patch (issue gh-3, Req 6; Decisions 10, 26).

The I/O half — `read` and `merge` — is proven against Postgres in
`tests/integration`; this is the pure half that decides what a patch may say.
"""

from __future__ import annotations

import pytest

from auth.preferences import InvalidPreferencesError, PreferencesPatch, parse_patch

BAD_CLOCK = ['Must be "12h" or "24h".']


@pytest.mark.parametrize("value", ["12h", "24h"])
def test_each_clock_value_is_set(value: str) -> None:
    patch = parse_patch({"clock": value})

    assert patch == PreferencesPatch({"clock": value}, [])


def test_null_removes_the_key() -> None:
    patch = parse_patch({"clock": None})

    assert patch.remove == ["clock"]
    assert patch.set == {}


def test_an_unknown_key_is_refused_by_name() -> None:
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"theme": "dark"})

    assert caught.value.errors == {"theme": ["Unknown preference."]}


@pytest.mark.parametrize("value", ["25h", 24, "", True], ids=["25h", "int", "empty", "bool"])
def test_a_bad_clock_is_refused(value: object) -> None:
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": value})

    assert caught.value.errors == {"clock": BAD_CLOCK}


def test_one_bad_key_refuses_the_whole_patch() -> None:
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": "24h", "theme": "x"})

    # The good key is not reported, and nothing is returned to apply.
    assert caught.value.errors == {"theme": ["Unknown preference."]}


def test_every_bad_key_is_reported_not_only_the_first() -> None:
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": "25h", "theme": "x"})

    assert set(caught.value.errors) == {"clock", "theme"}


def test_an_empty_patch_is_empty() -> None:
    assert parse_patch({}) == PreferencesPatch({}, [])
