"""Step definitions for profile.feature.

Named `test_*` so pytest collects the scenarios `scenarios()` generates into this
module. This is the **only** module that calls `scenarios()` on `profile.feature`.

Alan is the third person in the suite, and is used by no other scenario: Auth's
tables survive between scenarios, so a rename is not undone afterwards, and a
name no one else relies on is the only kind that can be left changed. Saving the
name he already has is a no-op, so a rerun against a kept stack still passes.

The rules about names - what is refused, what collides, the race - are proven
lower down (register D32); this journey shows only that a rename made in one
browser is what another browser reads after a reload.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/profile.feature")


# --- given ----------------------------------------------------------------


@given(parsers.parse('Alan has sent "{body}" in "{channel}"'))
def alan_has_sent(alan: ChatPage, body: str, channel: str) -> None:
    alan.open()
    alan.open_channel(channel)
    alan.send_message_and_wait(body)


# --- when -----------------------------------------------------------------


@when(parsers.parse('Alan changes his display name to "{name}"'))
def alan_renames(alan: ChatPage, name: str) -> None:
    alan.change_display_name(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Alan\'s own name reads "{name}"'))
def alans_own_name(alan: ChatPage, name: str) -> None:
    assert alan.has_own_name(name), alan.own_name()


#: The quotes around the name keep this from matching `test_message_steps.py`'s
#: `written by Ada`, and that phrase from matching this one.
@then(parsers.parse('Grace sees "{body}" written by "{name}"'))
def grace_sees_author_named(grace: ChatPage, body: str, name: str) -> None:
    assert grace.has_author(body, name), grace.author_of(body)
