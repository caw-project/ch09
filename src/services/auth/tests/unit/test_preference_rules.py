"""What a preferences patch may say (issue gh-3, Req 6; register D28).

`split` is the one decision the PATCH route makes before SQL: which keys to set
and which to remove. Absent means "leave alone" and `null` means "remove" — the
same distinction `PATCH /users/me` draws for the avatar.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auth.preferences import PreferencesPatch, split


def test_a_patch_sets_a_known_key() -> None:
    """The ordinary case: a valid clock is a key to set and nothing to remove."""
    patch = PreferencesPatch.model_validate({"clock": "24h"})

    assert split(patch) == ({"clock": "24h"}, [])


def test_null_removes_a_key_and_absence_leaves_it() -> None:
    """A build that treats None as "not sent" can never return to Automatic."""
    assert split(PreferencesPatch.model_validate({"clock": None})) == ({}, ["clock"])
    assert split(PreferencesPatch.model_validate({})) == ({}, [])


def test_an_unknown_key_is_refused_by_name() -> None:
    """The error must say which key, so the 400's `errors.<key>` has a field."""
    with pytest.raises(ValidationError) as caught:
        PreferencesPatch.model_validate({"theme": "dark"})

    assert [e["loc"] for e in caught.value.errors()] == [("theme",)]


def test_a_bad_value_is_refused_by_key() -> None:
    """Only "12h" and "24h" are clocks."""
    with pytest.raises(ValidationError) as caught:
        PreferencesPatch.model_validate({"clock": "13h"})

    assert [e["loc"] for e in caught.value.errors()] == [("clock",)]


def test_the_wire_name_is_the_key_itself() -> None:
    """camelCase and snake_case coincide for `clock`; the alias must not rename it."""
    assert split(PreferencesPatch.model_validate({"clock": "12h"}))[0] == {"clock": "12h"}
