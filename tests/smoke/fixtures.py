"""Fixtures for the smoke packs: a running CollabHub, reached only through its origin.

`scripts/smoke.sh` loads this with `-p smoke.fixtures`, so a pack anywhere — the standard
one beside it, or a feature's under `build/acceptance/` — gets the same fixtures. It sets
`SMOKE_ORIGIN` and `SMOKE_OUT`; run any other way, the session stops at once.

**Non-destructive, by rule.** Unlike `tests/bdd`, nothing here reaches a database, a
Compose port or anything but the origin, and nothing is truncated. A test creates only
what it names with `run_id`, so a pack is safe against a preview someone is using.

Sign-in goes through the real flow with the `bdd.pages` page objects, once per session
into a context that stays alive — `tests/bdd/conftest.py` explains why a saved
`storage_state` would sign the user out.
"""

from __future__ import annotations

import os
import re
import struct
import time
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from bdd.pages.chat_page import ChatPage
from bdd.pages.sign_in_page import SignInPage
from playwright.sync_api import APIRequestContext, Browser, BrowserContext, Page, Playwright

ADA = "ada@collabhub.dev"
SHARED_WORKSPACE = os.environ.get("AUTH_DEMO_WORKSPACE_NAME", "CollabHub Demo")


def solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A PNG of one solid colour, built here so a pack needs no image files or Pillow."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


#: An image a screenshot shows — a 1x1 or transparent one proves nothing to the person
#: reading the proof.
PNG = solid_png(160, 90, (37, 99, 235))


@pytest.fixture(scope="session")
def origin() -> str:
    value = os.environ.get("SMOKE_ORIGIN", "").rstrip("/")
    if not value:
        pytest.exit(
            "SMOKE_ORIGIN is not set — run the smoke packs with scripts/smoke.sh", returncode=4
        )
    return value


@pytest.fixture(scope="session")
def out_dir() -> Path:
    path = Path(os.environ.get("SMOKE_OUT", "build/smoke"))
    (path / "screenshots").mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def run_id() -> str:
    """A prefix for everything a run creates — a channel name is a letter, then letters, digits and dashes."""
    return time.strftime("smoke-%Y%m%d-%H%M%S", time.gmtime())


@pytest.fixture(scope="session")
def api(playwright: Playwright, origin: str) -> Iterator[APIRequestContext]:
    """Unauthenticated requests to the origin, as anyone on the internet could make them."""
    context = playwright.request.new_context(base_url=origin)
    yield context
    context.dispose()


@pytest.fixture(scope="session")
def ada_context(browser: Browser, origin: str) -> Iterator[BrowserContext]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    sign_in = SignInPage(page, origin)
    sign_in.sign_in(ADA)
    sign_in.use_workspace(SHARED_WORKSPACE)
    page.close()
    yield context
    context.close()


@pytest.fixture
def ada(ada_context: BrowserContext, origin: str) -> Iterator[ChatPage]:
    page = ada_context.new_page()
    chat = ChatPage(page, origin)
    chat.open()
    yield chat
    page.close()


@pytest.fixture
def shot(request: pytest.FixtureRequest, out_dir: Path) -> Callable[[Page, str], Path]:
    """Save a full-page screenshot, named after the test, to `<out>/screenshots/`."""

    def take(page: Page, name: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{request.node.name}-{name}".lower()).strip("-")
        path = out_dir / "screenshots" / f"{slug}.png"
        page.screenshot(path=str(path), full_page=True)
        return path

    return take
