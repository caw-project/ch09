"""Parsing a preferences patch (issue gh-3, Req 6-7), before any database is involved.

The server validates the keys (D28), so the rules live in one pure function the
route calls and the tests can reach without a session.
"""

from __future__ import annotations

import pytest

from auth import preferences

UNKNOWN = "Unknown preference."
BAD_CLOCK = 'Must be "12h", "24h" or null.'


@pytest.mark.parametrize("value", ["12h", "24h"])
def test_clock_takes_12h_and_24h(value: str) -> None:
    """The two settings; absent (Automatic) is the third."""
    patch = preferences.parse_patch({"clock": value})

    assert patch.set == {"clock": value}
    assert patch.remove == frozenset()


def test_null_removes_a_key() -> None:
    """`null` is how a user goes back to Automatic — it removes, it does not store None."""
    patch = preferences.parse_patch({"clock": None})

    assert patch.set == {}
    assert patch.remove == frozenset({"clock"})


@pytest.mark.parametrize("value", ["12", "24H", 24, True, ""])
def test_bad_clock_values_are_refused(value: object) -> None:
    """Each wrong shape alone: a near-miss string, a number, a bool, an empty string."""
    with pytest.raises(preferences.InvalidPreferencesError) as caught:
        preferences.parse_patch({"clock": value})

    assert caught.value.errors == {"clock": [BAD_CLOCK]}


def test_an_unknown_key_is_refused_by_name() -> None:
    with pytest.raises(preferences.InvalidPreferencesError) as caught:
        preferences.parse_patch({"theme": "dark"})

    assert caught.value.errors == {"theme": [UNKNOWN]}


def test_every_bad_key_is_reported_at_once() -> None:
    """A client fixing one error at a time would loop; both come back together."""
    with pytest.raises(preferences.InvalidPreferencesError) as caught:
        preferences.parse_patch({"clock": "x", "theme": 1})

    assert caught.value.errors == {"clock": [BAD_CLOCK], "theme": [UNKNOWN]}


def test_an_empty_patch_is_empty() -> None:
    patch = preferences.parse_patch({})

    assert patch.set == {}
    assert patch.remove == frozenset()


def test_the_constants_are_the_texts_the_spa_shows() -> None:
    assert preferences.UNKNOWN == UNKNOWN
    assert preferences.BAD_CLOCK == BAD_CLOCK
    assert set(preferences.KEYS) == {"clock"}
