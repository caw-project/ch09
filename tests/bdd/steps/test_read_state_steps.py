"""Step definitions for read_state.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `read_state.feature`.

Only the two phrasings this feature introduced are here; signing in, creating
channels, sending and opening are in `steps/conftest.py`. The rules behind the
badge — the read rule, the throttle, the hold — are proven in Vitest (register
D32); this journey proves that the server's marker moved, because the last step
follows a reload.

No selectors. A step says what a person saw; `pages/chat_page.py` knows where.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/read_state.feature")


@then(
    parsers.re(r'Grace sees (?P<count>\d+) unread messages? in "(?P<name>[^"]*)"'),
    converters={"count": int},
)
def grace_sees_unread(grace: ChatPage, count: int, name: str) -> None:
    assert grace.has_unread_badge(name, count)


@then(parsers.parse('Grace sees no unread messages in "{name}"'))
def grace_sees_no_unread(grace: ChatPage, name: str) -> None:
    assert grace.lacks_unread_badge(name)
