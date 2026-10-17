"""The preferences patch rules (issue gh-3, Req 6; register D28).

`parse_patch` is the only place a body is validated: the route hands it the raw
JSON object and the store takes what it returns.
"""

from __future__ import annotations

import pytest

from auth.preferences import InvalidPreferencesError, PreferencesPatch, parse_patch


def test_a_known_key_is_set() -> None:
    """A valid value lands in `set`, and nothing is removed."""
    assert parse_patch({"clock": "24h"}) == PreferencesPatch(
        set={"clock": "24h"}, remove=frozenset()
    )
    assert parse_patch({"clock": "12h"}).set == {"clock": "12h"}


def test_null_removes_the_key() -> None:
    """`null` is "back to automatic": the key goes, it is not stored as null."""
    patch = parse_patch({"clock": None})

    assert patch.remove == frozenset({"clock"})
    assert patch.set == {}


def test_an_empty_body_changes_nothing() -> None:
    """`{}` parses to an empty patch — the route answers with the current keys."""
    assert parse_patch({}) == PreferencesPatch(set={}, remove=frozenset())


def test_an_unknown_key_is_refused() -> None:
    """Only the server's keys exist; anything else is `errors.<key>`."""
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"theme": "dark"})

    assert caught.value.errors == {"theme": ["Unknown preference."]}


@pytest.mark.parametrize("value", ["13h", "", "24H", 12, True, ["24h"]])
def test_a_bad_value_is_refused(value: object) -> None:
    """A value outside the key's set is refused — including ones that merely look right."""
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": value})

    assert caught.value.errors == {"clock": ['Must be "12h", "24h" or null.']}


def test_every_error_is_reported_at_once() -> None:
    """A bad value and an unknown key are both named, so the client fixes them in one go."""
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": "13h", "theme": 1})

    assert set(caught.value.errors) == {"clock", "theme"}


def test_a_valid_key_beside_an_invalid_one_is_not_applied() -> None:
    """Nothing is half-parsed: the error, not a patch holding the good key, comes back."""
    with pytest.raises(InvalidPreferencesError) as caught:
        parse_patch({"clock": "24h", "theme": "dark"})

    assert set(caught.value.errors) == {"theme"}
