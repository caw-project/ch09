"""Step definitions for direct_messages.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module. The shared phrases (`Ada is signed in`,
`Ada has created a public channel…`, `Grace is looking at…`, `Ada sends "…"`,
`Grace sees "…" in the channel`) live in `steps/conftest.py`; only what this feature
introduced is here.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import ADA_NAME, GRACE_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/direct_messages.feature")


# --- when -----------------------------------------------------------------


@when("Ada starts a direct message with Grace")
def ada_starts_dm(ada: ChatPage) -> None:
    ada.start_dm(GRACE_NAME)


@when("Grace opens her direct message with Ada")
def grace_opens_dm(grace: ChatPage) -> None:
    grace.open_dm(ADA_NAME)


#: `parsers.re` for the reason `Ada sends "…"` in `conftest.py` gives.
@when(parsers.re(r'Grace sends "(?P<body>[^"]*)"'))
def grace_sends(grace: ChatPage, body: str) -> None:
    grace.send_message_and_wait(body)


# --- then -----------------------------------------------------------------


@then(
    parsers.parse(
        "Ada appears in Grace's direct messages with {count:d} unread message without reloading"
    )
)
def ada_in_graces_dms(grace: ChatPage, count: int) -> None:
    """Grace's page never navigates, so only `channel_added` can have put the row there."""
    assert grace.has_dm_unread_badge(ADA_NAME, count)


@then(parsers.parse('Ada sees "{body}" in the channel without reloading'))
def ada_sees_live(ada: ChatPage, body: str) -> None:
    ada.wait_for_message(body)
