"""Step definitions for attachments.feature.

The one journey a browser is needed for: the picked files go from Ada's browser
to Garage over a presigned URL, Messaging claims them from Asset, Grace's open
channel receives the message over the socket, her browser fetches a URL through
Messaging and the download returns Ada's bytes. The limits, the claim rules, paste,
URL freshness and restore are proven lower down (register D32).

Shared phrases — signing in, creating the channel, `Ada sends`, `Grace sees … in
the channel without reloading`, `… appears in Ada's channel exactly once` — are in
`steps/conftest.py` and `test_realtime_steps.py`, and are reused as they are.
What is here is only what attachments introduce. The bytes are built in this
module, so the assertion that Grace downloaded "the file Ada attached" compares
against something the scenario made and the stack never saw first.
"""

from __future__ import annotations

import base64

import pytest
from pytest_bdd import parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/attachments.feature")

#: A valid 1x1 PNG. `naturalWidth > 0` in the page object only holds for bytes a
#: browser can decode, so this is a real image and not a placeholder.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

#: The smallest PDF a reader will open. Its bytes are what the download is compared with.
_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

_FILES = {
    "png": ("image/png", _PNG),
    "pdf": ("application/pdf", _PDF),
}


@pytest.fixture
def attached() -> dict[str, bytes]:
    """What Ada attached in this scenario, by file name — what a download is compared with."""
    return {}


def _payload(name: str) -> dict[str, object]:
    mime, content = _FILES[name.rsplit(".", 1)[-1]]
    return {"name": name, "mimeType": mime, "buffer": content}


@when(parsers.parse('Ada attaches "{first}" and "{second}"'))
def ada_attaches(ada: ChatPage, attached: dict[str, bytes], first: str, second: str) -> None:
    for name in (first, second):
        attached[name] = _FILES[name.rsplit(".", 1)[-1]][1]
    ada.attach_files([_payload(first), _payload(second)])


@then(parsers.parse('Grace sees "{name}" shown inline with "{body}"'))
def grace_sees_inline(grace: ChatPage, name: str, body: str) -> None:
    assert grace.has_inline_image(body, name), grace.message_bodies()


@then(parsers.parse('Grace sees "{name}" as a download with "{body}"'))
def grace_sees_download(grace: ChatPage, name: str, body: str) -> None:
    assert grace.has_file_chip(body, name), grace.message_bodies()


@then(parsers.parse('the "{name}" Grace downloads is the file Ada attached'))
def grace_downloads_the_file(grace: ChatPage, attached: dict[str, bytes], name: str) -> None:
    """The same bytes, end to end — what proves the claim, the URL and Garage agree."""
    assert attached[name], "the scenario attached nothing under that name"
    assert grace.download_attachment("the plans", name) == attached[name]
