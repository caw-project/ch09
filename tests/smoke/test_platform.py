"""The standard smoke pack: what every deploy of CollabHub must do, seen from outside.

Run after any deploy with `scripts/smoke.sh`. It proves the routing, the identity flow,
the real-time path to Messaging's database and back, and object storage's own origin —
what a new environment most often gets wrong — and leaves a screenshot of each.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bdd.pages.chat_page import ChatPage
from playwright.sync_api import APIRequestContext, Browser, Page, expect

from smoke.fixtures import PNG, SHARED_WORKSPACE

Shot = Callable[[Page, str], Path]


def test_the_app_loads_without_errors(browser: Browser, origin: str, shot: Shot) -> None:
    context = browser.new_context()
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(origin)
        expect(page.get_by_test_id("sign-in")).to_be_visible()
        shot(page, "signed-out")
        assert errors == []
    finally:
        context.close()


def test_the_signing_keys_are_published(api: APIRequestContext) -> None:
    response = api.get("/.well-known/jwks.json")
    assert response.ok, response.status
    keys = response.json()["keys"]
    assert keys
    assert all(key["kty"] == "RSA" for key in keys)


def test_the_internal_api_is_not_routed(api: APIRequestContext) -> None:
    """D40: the Ingress's allow-list sends /api/v1/internal/ to the SPA, never a service."""
    response = api.get("/api/v1/internal/channels")
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/html"), content_type


def test_ada_signs_in_to_the_shared_workspace(ada: ChatPage, shot: Shot) -> None:
    assert ada.workspace_name() == SHARED_WORKSPACE
    shot(ada.page, "workspace")


def test_a_message_survives_a_reload(ada: ChatPage, run_id: str, shot: Shot) -> None:
    channel, text = f"{run_id}-chat", f"{run_id} hello from the smoke pack"
    ada.create_channel_and_wait(channel)
    ada.send_message_and_wait(text)

    ada.open()
    ada.open_channel(channel)
    assert ada.has_message(text)
    shot(ada.page, "after-reload")


def test_an_image_round_trips_through_object_storage(
    ada: ChatPage, run_id: str, shot: Shot
) -> None:
    channel, text = f"{run_id}-files", f"{run_id} an image"
    ada.create_channel_and_wait(channel)
    ada.attach_files([{"name": "smoke.png", "mimeType": "image/png", "buffer": PNG}])
    ada.send_message_and_wait(text)
    assert ada.has_inline_image(text, "smoke.png")
    shot(ada.page, "image")
