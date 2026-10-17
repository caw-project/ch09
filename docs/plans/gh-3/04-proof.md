# gh-3 — acceptance proof: accepted

## Summary
- A signed-in user clicks their name in the sidebar and lands on `/settings`. There they rename themselves and choose a clock (Automatic / 12-hour / 24-hour). The save is confirmed with "Saved".
- Ada's rename shows at once in her sidebar and on her own message. Grace, who had the old name cached, sees the new one on Ada's message after a reload.
- Display names are unique across CollabHub, ignoring case. Alan typing `GRACE` gets "That name is already taken." on the field. His name is unchanged, and the 409 body names no user and no workspace.
- Grace's 24-hour choice turns an afternoon message time from `03:36 PM` into `15:36`. It is stored on the server and survives a reload.
- All 3 visible criteria are proven on the preview. The first-sign-in suffix, the migration and the preferences routes are internal and are held by integration tests.

## Try it
- Origin: https://farmers-robot-distribution-phrases.trycloudflare.com — sign in as ada@collabhub.dev / collabhub (grace@collabhub.dev and alan@collabhub.dev too)
- Quick-tunnel URLs die with cloudflared: `BRANCH=feature/gh-3 scripts/deploy.sh preview url`, or `preview up` for new ones
- Take it down: `BRANCH=feature/gh-3 scripts/deploy.sh preview down`

## Acceptance criteria
| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Ada renames herself to `ada-<run id>`: sidebar and own messages show it at once; Grace, after a reload, sees it on Ada's message; Ada is renamed back | feature pack `test_ada_renames_herself_and_grace_sees_it_after_a_reload`. Fails on `main`: no `/settings`, no rename. Grace's directory is warm with the old name first, so only a stored rename plus a refetch can show the new one | **proven** | [settings](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-settings-saved-sidebar-shows-new-name.png) · [own message](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-own-message-shows-new-name.png) · [Grace](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-grace-sees-new-name-after-reload.png) |
| 2 | Alan tries "GRACE": "That name is already taken.", his name unchanged, the 409 body names no user and no workspace | feature pack `test_alan_cannot_take_graces_name`. Asserts status 409 and that the body has no "grace", "workspace" or "@". It also checks the sidebar and a reloaded form are unchanged. Case differs (`GRACE` vs `grace`), so only the uniqueness rule can refuse it; `main` has no `/settings` and no uniqueness | **proven** | [Alan](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-alan-sees-name-taken.png) |
| 3 | Grace chooses 24-hour: a message after noon shows a 24-hour time; Automatic again at the end | feature pack `test_grace_chooses_24_hour_and_a_message_shows_it`. Grace's browser zone is one where it is afternoon now. Before the choice the time must end in AM/PM; after it, it must match `13:00`–`23:59`; a reload keeps it. Fails on `main`: no clock | **proven** | [automatic](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-and-a-message-shows-it-chromium-automatic-is-12-hour.png) · [chosen](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-and-a-message-shows-it-chromium-settings-24-hour-chosen.png) · [24-hour](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-and-a-message-shows-it-chromium-message-time-24-hour.png) |
| 4 | Req 1 validation (trim, NFC, refused characters, 400 + `errors.displayName`) — internal on the preview | `test_names.py` and `test_users.py::test_an_invalid_name_is_refused`, `::test_a_name_is_stored_trimmed_and_in_nfc` | internal | — |
| 5 | Req 2 uniqueness, case and NFC, deleted names stay taken, concurrent rename | `test_users.py::test_names_colliding_only_after_nfc_are_taken`, `::test_a_deleted_accounts_name_stays_taken`; `test_display_names.py::test_two_renames_to_one_name_one_wins`; `test_schema.py::test_a_display_name_differing_only_in_case_is_refused` | internal | — |
| 6 | Req 3 first-sign-in suffix (the issue says: integration only) | `test_display_names.py::test_a_taken_idp_name_gets_the_first_free_suffix`, `::test_two_first_sign_ins_with_one_name` | internal | — |
| 7 | Req 4 migration | `test_migration_0002.py` (4 tests) | internal | — |
| 8 | Req 6 preferences routes | `test_preferences.py` (integration, 11), `test_preferences.py` (unit, 12) | internal | — |
| 9 | Req 7 clock reaches thread summaries and search results | `ClockProvider.test.tsx` (3 places × 24h / 12h / automatic). The preview run covers only the message time | internal | — |

## Preview
- Branch `feature/gh-3`, commit `8d9cc2b` (working tree clean).
- Preview `preview-feature-gh-3`, up at https://farmers-robot-distribution-phrases.trycloudflare.com. `preview-up.log` ends "preview is up".
- The standard pack's "app loads" and "signing keys" checks went through the origin and passed.

## Standard smoke pack
6 passed, 0 failed, 0 skipped (step 3, `build/acceptance/standard`). It passed again beside the feature pack.

## Feature smoke pack
`build/acceptance/smoke/test_gh_3.py`, run with the standard pack: 9 passed.
- **`test_ada_renames_herself_and_grace_sees_it_after_a_reload`**: Ada sends a message. Grace loads it and sees "ada". Ada renames on Settings and the sidebar shows the new name. Back in the channel her own message shows it with no reload. Grace reloads and sees it. Ada is renamed back in a `finally`. Passed.
- **`test_alan_cannot_take_graces_name`**: Alan saves "GRACE" and gets a 409 with "That name is already taken." on the field. His name is unchanged, even after a reload. Passed.
- **`test_grace_chooses_24_hour_and_a_message_shows_it`**: Grace's message goes from `03:36 PM` (Automatic) to `15:36` (24-hour) and survives a reload. She is put back to Automatic in a `finally`. Passed.
- Two earlier runs failed because of my own test. A direct load of `/settings` has no last channel, so "Back to chat" correctly goes to `/`. I fixed that, and made the radio helper wait for the page to settle. No feature fault.
- The pack can be rerun against this preview at any time. Each run's own names carry the run id, and Ada and Grace are restored. Alan and Grace's names are never changed.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — `feature/screenshots/` holds the seven feature shots above and the standard ones. Disposable: the PR uploads them.
I opened every cited screenshot. Each shows the feature in view, nothing cut off.

## For the human
**Assumed decisions** (plan): 12 (full Unicode case folding via `casefold`), 13 (length in code points), 15 (saving your own name is a no-op, checked before validation), 17/19/22 (base name, retries, empty stored names), 25 (`PATCH {}`), 28 (sign-in returns to the route), 29 (Back to chat / `lastChannelId`), 30 (client-side Save gating), 34 (optimistic clock and scope), 37 (a renewal racing a rename).

**Corrections to the issue**: sign-in did not return to the starting route, so the plan built it for every protected route. Auth needed a second stored column (`display_name_key`) to carry the case-insensitive rule.

**Departures** (green report): `useClock` in its own file; `directoryKeys.all`; the form is not rendered until the profile is fetched; an unchanged avatar no longer bumps `version`; `usePreferences` on defaults. Red report: `TABLES` in the Auth conftest unchanged; `Strauß`/`STRAUSS`; the signed-out `/settings` test fails earlier than the plan says; decision 29's workspace-change reset has no test of its own.

**Open items from reviews**
- Two clock saves that fail in a row restore a value the server never stored (plan review 2, optional). The next visit reads the server.
- `origin/feature/gh-3-run1` edits the same files; only one branch can merge.
- The green report records a flake in `App.test.tsx` ("sends a signed-out visitor…"): once in a full run, passing alone and in later runs.
- Test review: the 24-hour midnight test cannot tell `hour12: false` from `hourCycle` on this ICU.
- Test review: `test_a_deleted_accounts_name_is_skipped_at_sign_in` is an outcome-only test.

**Unpinned** (code review, no test holds these; the code was right in each case):
- `ClockProvider` in the shell: removing it passes every approved test (probe 1 caught it).
- `onMutate`'s `cancelQueries` for the clock (probe 2 caught it).
- The profile cache write on a rename.
- `_is_name_conflict` matching on the constraint name.
- `_taken_keys` reading deleted rows.
- The avatar no-op writing nothing.
- The ADR `260815-tailwind-v4…` still says no preferences feature exists, left on purpose.

**Things I found**
- The members panel truncates a long display name (`ada-smoke-2026101…`) — cosmetic, and only with long names.
- The preview checks cover the message time only. Thread summaries and search results rely on the Vitest tests.
- No contradiction between the record and the branch: both reviews' claims match the files, and `git status` is clean at `8d9cc2b`.

## The run
- 01 plan-writer done — 101 turns, plan of 521 lines, 12 assumed decisions.
- 02 plan-reviewer changes_requested — 4 major, 5 minor.
- 03 plan-writer done — all nine answered.
- 04 plan-reviewer approved — round 2.
- 05 test-writer done — 138 failing tests.
- 06 test-reviewer approved — no critical or major.
- 07 code-writer done — everything green, e2e 25/25.
- 08 code-reviewer changes_requested — README/`index.css` still said D28 was open.
- 09 code-writer done — both findings fixed.
- 10 code-reviewer approved — round 2, no findings.
