"""Step definitions for display_names.feature.

Named `test_*` for the reason the other step modules give, and the **only**
module that calls `scenarios()` on this feature. The shared vocabulary — Grace
reloading, Grace opening a channel — lives in `steps/conftest.py`; what is here
is what this journey introduced: Alan, and a name quoted in the sentence.

The rules for a name — trimming, length, characters, case-insensitive
uniqueness, the 409 — are proven below the browser (register D32): unit
`auth.names`, Auth's integration tests, and the Vitest `SettingsPage` tests.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/display_names.feature")


# --- given ----------------------------------------------------------------


@given("Alan is signed in")
def alan_is_signed_in(alan: ChatPage) -> None:
    # The context is signed in for the whole session; this loads the app fresh.
    alan.open()


@given(parsers.parse('Alan has created a public channel named "{name}"'))
def alan_has_created(alan: ChatPage, name: str) -> None:
    alan.create_channel_and_wait(name)


@given(parsers.parse('Alan has sent "{body}" in "{channel}"'))
def alan_has_sent(alan: ChatPage, body: str, channel: str) -> None:
    alan.open_channel(channel)
    alan.send_message_and_wait(body)


# --- when -----------------------------------------------------------------


@when(parsers.parse('Alan renames himself to "{name}" on Settings'))
def alan_renames(alan: ChatPage, name: str) -> None:
    alan.rename_self(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Alan sees his own name as "{name}"'))
def alan_sees_his_name(alan: ChatPage, name: str) -> None:
    assert alan.has_own_name(name), alan.own_name()


#: `parsers.re` with `[^"]*`, as `steps/conftest.py` does for sending: `parse`'s
#: `{body}` can swallow a closing quote, and this phrase has two quoted parts.
#: It is distinct from `written by Ada` (`test_message_steps.py`), which takes no
#: quoted name.
@then(parsers.re(r'Grace sees "(?P<body>[^"]*)" written by "(?P<name>[^"]*)"'))
def grace_sees_author_named(grace: ChatPage, body: str, name: str) -> None:
    """Grace's window after a reload: the name Auth holds, not Alan's own cache."""
    assert grace.has_author(body, name), grace.author_of(body)
