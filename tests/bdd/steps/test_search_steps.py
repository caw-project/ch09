"""Step definitions for search.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `search.feature`.

Only the four phrasings this feature introduced are here; signing in, creating
channels, sending and "is looking at" are in `steps/conftest.py`. The rows, the
paging, the jump's cap and its races are proven in Vitest (register D32); this
journey proves the whole chain — a message posted, indexed by the Worker, found
through Messaging, and opened highlighted in its channel.

No selectors. A step says what a person did or saw; `pages/chat_page.py` knows
where.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/search.feature")


@when(parsers.re(r'Ada searches for "(?P<query>[^"]*)"'))
def ada_searches(ada: ChatPage, query: str) -> None:
    ada.search(query)


@then(parsers.re(r'Ada sees "(?P<body>[^"]*)" in the search results'))
def ada_sees_in_results(ada: ChatPage, body: str) -> None:
    assert ada.has_search_result(body)


@when(parsers.re(r'Ada opens the search result "(?P<body>[^"]*)"'))
def ada_opens_result(ada: ChatPage, body: str) -> None:
    ada.open_search_result(body)


@then(parsers.re(r'Ada sees "(?P<body>[^"]*)" highlighted'))
def ada_sees_highlighted(ada: ChatPage, body: str) -> None:
    assert ada.has_highlighted(body)
