"""The Settings page, as the scenarios talk about it.

Selectors are `data-testid` only and live here; a step never contains one. Reached
from the chat shell by clicking the signed-in user's name — `ChatPage.open_settings`.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


class SettingsPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def rename_to(self, name: str) -> None:
        """Type a new display name, save it, and wait until the page says it is saved.

        The form renders only once the page has read the profile from the server, so
        `fill` waiting for the field also waits for that. **If Save is disabled after
        filling, the field already holds the name the account has** — a rerun against a
        kept stack, where Alan was renamed the first time — and there is nothing to
        save: the next step's check of what the server shows still fails if the
        rename never happened on a fresh stack.
        """
        expect(self.page.get_by_test_id("settings-page")).to_be_visible()
        self.page.get_by_test_id("settings-display-name").fill(name)
        save = self.page.get_by_test_id("settings-save")
        if save.is_disabled():
            return
        save.click()
        expect(self.page.get_by_test_id("settings-saved")).to_be_visible()
