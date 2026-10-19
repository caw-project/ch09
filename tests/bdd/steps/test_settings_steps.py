"""Step definitions for settings.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module. This is the **only** module that calls
`scenarios()` on `settings.feature`.

The name rules, uniqueness, the 409 and its races, preferences and the clock are
proven lower down (register D32): `test_names.py`, `test_display_names.py` and the
Vitest `SettingsPage`, `useProfile` and `usePreferences` tests. What a journey
alone can show is that a rename made in one browser is what the *server* holds —
so the last step is another person's window after a reload, not the renamer's own.

Alan is the third person (`ALAN` in the harness conftest): nobody else's scenario
uses him, so his new name disturbs none of them.

No selectors. A step says what a person did; `pages/` knows what to click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.pages.settings_page import SettingsPage

pytestmark = pytest.mark.bdd

scenarios("../features/settings.feature")


# --- given ----------------------------------------------------------------


@given(parsers.parse('Alan has sent "{body}" in "{channel}"'))
def alan_has_sent(alan: ChatPage, body: str, channel: str) -> None:
    """Alan opens the app, opens the channel Ada made, and sends — waiting for the server's copy."""
    alan.open()
    alan.open_channel(channel)
    alan.send_message_and_wait(body)


# --- when -----------------------------------------------------------------


@when(parsers.parse('Alan changes his name to "{name}"'))
def alan_changes_his_name(alan: ChatPage, name: str) -> None:
    alan.open_settings()
    SettingsPage(alan.page).rename_to(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Alan sees his name as "{name}"'))
def alan_sees_his_name(alan: ChatPage, name: str) -> None:
    assert alan.has_own_name(name), alan.own_name()


@then(parsers.parse('Grace sees "{body}" written by "{name}"'))
def grace_sees_author_named(grace: ChatPage, body: str, name: str) -> None:
    """Grace resolves Alan's name from the directory she fetched on her reload.

    Quoted, so it cannot bind the existing `written by Ada` step in messages.feature.
    """
    assert grace.has_author(body, name), grace.author_of(body)
