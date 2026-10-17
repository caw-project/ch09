"""Step definitions for settings.feature.

The only module that calls `scenarios()` on this feature. The name rules, the
409, the clock and the cache writes are proven lower down (register D32): unit
`test_names`, Auth's integration tests and the Vitest `SettingsPage` tests. The
journey is the one thing they cannot show: a rename made in one browser is what
a second browser reads from the server after a reload.

Shared phrases — `Ada is signed in`, creating a channel, `Grace reloads
CollabHub`, `Grace opens the "…" channel` — live in `steps/conftest.py`.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/settings.feature")


@given(parsers.parse('Alan has sent "{body}" in "{channel}"'))
def alan_has_sent(alan: ChatPage, body: str, channel: str) -> None:
    alan.open()
    alan.open_channel(channel)
    alan.send_message_and_wait(body)


@when(parsers.parse('Alan changes his display name to "{name}"'))
def alan_renames(alan: ChatPage, name: str) -> None:
    alan.open_settings()
    alan.change_display_name(name)


@then(parsers.parse('Alan\'s sidebar shows him as "{name}"'))
def alans_sidebar(alan: ChatPage, name: str) -> None:
    assert alan.shows_current_user(name)


# Quoted, because the name is a value rather than a persona; it lives in this
# module so it cannot collide with `written by Ada` in test_message_steps.py.
@then(parsers.parse('Grace sees "{body}" written by "{name}"'))
def grace_sees_written_by(grace: ChatPage, body: str, name: str) -> None:
    assert grace.has_author(body, name), grace.author_of(body)
