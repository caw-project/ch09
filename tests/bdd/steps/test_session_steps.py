"""Step definitions for session.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `session.feature`.

**`ada` is overridden here**, and that is the whole trick of this module. Every
other feature shares one signed-in browser for Ada for the entire run, and these
scenarios would wreck it: signing out revokes its refresh token, and switching
workspace changes which workspace its cookie restores into. So the `ada` fixture
below replaces the shared one for this module only, with a browser that signs in
on its own (`ada_own_context`). The shared steps in `steps/conftest.py` — signing
in, creating a channel, reading the sidebar — resolve `ada` from the test that
requested them, so they drive this browser without knowing it is a different one.

Refresh rotation, reuse detection and the workspace a refresh restores are proven
lower down (register D32), in Auth's integration tests and the Vitest session
tests. What is here is what only a real browser shows: the cookie really is
gone, and the route guard really does send a stranger to sign in.

No selectors. A step says what a person did; the page objects know what to click.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import BrowserContext
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.pages.sign_in_page import SignInPage

pytestmark = pytest.mark.bdd

scenarios("../features/session.feature")


# --- fixtures -------------------------------------------------------------


@pytest.fixture
def ada(ada_own_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    """Ada in a browser of her own — see the module docstring."""
    page = ada_own_context.new_page()
    yield ChatPage(page, base_url)
    page.close()


@pytest.fixture
def stranger(signed_out_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    """Someone with a link and no session."""
    page = signed_out_context.new_page()
    yield ChatPage(page, base_url)
    page.close()


# --- when -----------------------------------------------------------------


@when("Ada signs out")
def ada_signs_out(ada: ChatPage) -> None:
    ada.sign_out()


@when(parsers.parse('Ada switches to the "{name}" workspace'))
def ada_switches_workspace(ada: ChatPage, name: str) -> None:
    ada.switch_workspace(name)


@when("someone who is not signed in opens the link to that channel")
def stranger_opens_the_link(ada: ChatPage, stranger: ChatPage) -> None:
    """Ada's URL, pasted into a browser that has never signed in."""
    stranger.open_channel_by_id(ada.current_channel_id())


# --- then -----------------------------------------------------------------


@then("Ada is asked to sign in")
def ada_is_asked_to_sign_in(ada: ChatPage, base_url: str) -> None:
    assert SignInPage(ada.page, base_url).is_shown(), ada.page.url


@then("they are asked to sign in")
def stranger_is_asked_to_sign_in(stranger: ChatPage, base_url: str) -> None:
    assert SignInPage(stranger.page, base_url).is_shown(), stranger.page.url
