"""Step definitions for threads.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module. The shared phrases (`Ada is signed in`,
`Ada has created a public channel…`, `Ada has sent…`, `Grace is looking at…`)
live in `steps/conftest.py`; only what this feature introduced is here.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/threads.feature")


# --- when -----------------------------------------------------------------


@when(parsers.parse('Ada replies "{reply}" in the thread on "{body}"'))
def ada_replies(ada: ChatPage, reply: str, body: str) -> None:
    ada.reply_in_thread(body, reply)


@when(parsers.parse('Grace opens the thread on "{body}"'))
def grace_opens_thread(grace: ChatPage, body: str) -> None:
    grace.open_thread(body)


# --- then -----------------------------------------------------------------


#: `parsers.re`, so "1 reply" and "2 replies" are one phrase and `[^"]*` cannot
#: swallow a closing quote.
@then(parsers.re(r'Grace sees (?P<count>\d+) repl(?:y|ies) on "(?P<body>[^"]*)" without reloading'))
def grace_sees_count(grace: ChatPage, count: str, body: str) -> None:
    assert grace.has_reply_count(body, int(count))


@then(parsers.parse('Grace sees "{text}" in the thread'))
def grace_sees_in_thread(grace: ChatPage, text: str) -> None:
    assert grace.thread_has_message(text)
