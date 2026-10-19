# gh-3 — acceptance proof: accepted

## Summary
- A signed-in user opens **Settings** by clicking their name in the sidebar, and changes their display name. The new name shows at once in their own sidebar and on their own messages; another user sees it after a reload.
- Display names are unique across all of CollabHub, ignoring case. Alan trying "GRACE" gets "That name is already taken." on the field. His name is unchanged, and the 409 body names nobody and no workspace.
- The same page holds a clock preference (Automatic / 12-hour / 24-hour). Choosing 24-hour re-renders message times at once (`21:16` where Automatic showed `09:16 PM`), and the choice survives a reload because the server holds it.
- "Back to chat" returns to the channel the user came from.
- All three acceptance checks from the issue ran on the preview and passed; Ada and Grace were put back as they were.

## Try it
- On GitHub, the PR's own preview: its origin is in the preview comment on the PR, and it stays up until the PR is approved or closed. Sign in as ada@collabhub.dev (grace@collabhub.dev too) with the preview password, which goes to the delivery's Slack thread — `collabhub` where Slack isn't set up
- Locally: `BRANCH=feature/gh-3 scripts/deploy.sh preview up`, then `preview url`; `preview down` when you're done

## Acceptance criteria
The issue's *Acceptance — on the branch's preview* lists three checks; Req 1–8 and *Where the rules meet* are the rest. "Visible" means seen in the running app or at its public API.

| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| A1 | Ada renames herself; her sidebar and her own messages show it at once; Grace after a reload sees it on Ada's message; Ada renamed back (Req 1, 5, 8) | `test_ada_renames_herself_and_grace_sees_it` | **proven** (fails on `main`: no `/settings`) | [saved](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-settings-saved.png) · [own message](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-own-message-new-name.png) · [Grace](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-grace-sees-new-name.png) |
| A2 | Alan tries "GRACE": "That name is already taken.", his name unchanged, 409 body names no user and no workspace (Req 2, D46) | `test_alan_cannot_take_graces_name` | **proven** (fails on `main`: no page, no uniqueness) | [taken](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-name-taken.png) |
| A3 | Grace chooses 24-hour: a message sent after noon shows a 24-hour time; Automatic again at the end (Req 7, 8) | `test_grace_chooses_the_24_hour_clock` | **proven** (fails on `main`: no preference) | [before](../../../build/acceptance/feature/screenshots/test-grace-chooses-the-24-hour-clock-chromium-automatic-12-hour-before.png) · [after](../../../build/acceptance/feature/screenshots/test-grace-chooses-the-24-hour-clock-chromium-after-24-hour.png) |
| A4 | "Back to chat" goes to the last channel (Req 8) | same test as A1, which clicks it and then reads Ada's message | **proven** as a side effect of A1 | the "own message" shot above |
| I1 | Trim, NFC, the refused and accepted names (Req 1) | `test_names.py`, `test_display_names.py::test_each_refused_example_is_400_on_the_field`, `…::test_a_rename_is_stored_trimmed_and_composed` | internal — tested | — |
| I2 | Same-name save changes nothing; capitals-only allowed; deleted names stay taken (Req 1, 2) | `test_display_names.py::test_saving_the_name_you_have_writes_nothing`, `…::test_changing_only_your_own_capitals_is_allowed`, `…::test_a_deleted_accounts_name_stays_taken` | internal — tested | — |
| I3 | The two-at-once race: exactly one wins (Where the rules meet 1) | `test_display_names.py::test_two_renames_at_once_one_wins`, `…::test_a_rename_racing_a_held_rename` | internal — tested | — |
| I4 | First sign-in suffixing and its races (Req 3) — the issue says the preview can't show it | `test_display_names.py::test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix`, `…::test_two_first_sign_ins_with_one_name`, `…::test_a_first_sign_in_racing_a_held_rename` | internal — tested | — |
| I5 | Migration renames duplicates except the oldest (Req 4) | `test_migration_0002.py` (8 tests) | internal — tested | — |
| I6 | Preferences GET/PATCH, merge, `null`, 400, 404 for a deleted account (Req 6) | `test_preferences.py`, `test_preferences_merge.py`, `test_preferences.py` (unit) | internal — tested | — |
| I7 | Token's `name` claim keeps the old name until renewed; the workspace keeps its name | `test_display_names.py::test_the_token_keeps_the_old_name_until_renewed`, `…::test_a_rename_leaves_the_workspace_name` | internal — tested | — |
| I8 | The clock reaches all three formatters; a failed save reverts | `time.test.ts`, `MessageItem.clock.test.tsx`, `ThreadSummary.test.tsx`, `SearchResult.test.tsx`, `usePreferences.test.ts` | internal — tested. The preview shows message times only; thread-summary and search-result times are covered by Vitest alone | — |
| I9 | Rename after unmount, over a fetch in flight, and over a renewal in flight (Paths, Where the rules meet 3) | `useProfile.test.ts`, `session.test.ts` | internal — tested | — |

Visible: 4 (A1–A4), 4 proven, 0 regression checks. A4 has no test of its own; it is covered by a step inside A1.

## Preview
- Branch `feature/gh-3`, commit `7426f4b` (the worktree is clean beyond it, apart from the ignored `build/`).
- Namespace `preview-feature-gh-3`; the deploy came up on the first try (`build/acceptance/preview-up.log`: "preview preview-feature-gh-3 is up").
- Origin `https://tracked-projection-firms-keith.trycloudflare.com` (a tunnel, gone by the time this is read); object-store origin on its own tunnel. The standard pack's keys, internal-API and storage checks all passed against them.

## Standard smoke pack
**Passed, 6 of 6** (step 3, `build/acceptance/standard`): the app loads without errors, signing keys published, internal API not routed, Ada signs in to the shared workspace, a message survives a reload, an image round-trips through object storage. It passed again beside the feature pack (9 passed in all).

## Feature smoke pack
`build/acceptance/smoke/test_gh_3.py`, run with `scripts/smoke.sh --out build/acceptance/feature build/acceptance/smoke`: **3 feature tests passed**, plus the 6 standard.

- **`test_ada_renames_herself_and_grace_sees_it`** — Ada creates a channel and sends a message, saves the name `ada-<run id>` on Settings, sees "Saved" and the new name in her sidebar, clicks "Back to chat" without reloading and sees the new name on her own message. A second browser signs in as Grace, opens the channel and reads the new name on Ada's message. Ada is saved back to her original name in a `finally`, and the test checks the sidebar shows it. Would fail on `main`: there is no Settings page to type the name into.
- **`test_alan_cannot_take_graces_name`** — Alan types Grace's name in capitals and saves. The PATCH answers 409; the response body contains neither Grace's name nor the word "grace" nor the shared workspace's name; the field shows "That name is already taken."; Alan's sidebar still shows `alan`, and after a reload it still does. Would fail on `main`: no page, and PATCH accepts any name there.
- **`test_grace_chooses_the_24_hour_clock`** — the browser runs in a time zone where it is now afternoon (here Asia/Kolkata), `en-US`. Grace sends a message; on Automatic it reads `09:16 PM`, which proves the starting point is the locale and not the preference. She picks 24-hour on Settings, goes back, and the same message reads `21:16`; after a reload it still reads 24-hour, so the server holds it. She is set back to Automatic in a `finally`, and the final state is checked from a fresh load. Would fail on `main`: no preference, times follow the locale.

Two of my own mistakes along the way, no bearing on the branch: a first version of the clock test used Playwright's `.check()`, which throws for a controlled radio that only updates after the save's `onMutate`; its failed clean-up left Grace on 24-hour for a few runs until I put her back by hand. The test now uses `.click()` and the clean-up waits for the server's answer. The final run started from Automatic and ended on it.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — standard in `standard/screenshots/`, feature in `feature/screenshots/`. I opened every one cited above. Disposable: the PR uploads them.

## For the human
**Assumed decisions** (plan; each is "assumed" there):
- 15 — "ignoring case" is full Unicode case folding (`Straße` collides with `STRASSE`), not `lower()`.
- 19 — an IdP name that breaks Req 1 is cleaned, not refused; falls back to the email's local part, then `"user"`.
- 20 — a suffix past 100 characters cuts the base.
- 21 — the migration only trims and NFC-normalises; an empty name becomes `"user"`; legacy names with refused characters stay until renamed.
- 22 — migration "oldest" is `(created_at, id)`; a duplicate takes the first suffix no row holds (`Sam, Sam, Sam 2` → `Sam, Sam 3, Sam 2`).
- 24 — saving the name you have is a no-write 200, unless an `avatarAsset` rides along.
- 27 — a PATCH that removes everything still creates the row.
- 35 — the return-to-page after sign-in was built for every protected route, not only `/settings` (the issue's assumption was wrong; plan correction 2).
- 36 — Save's "invalid" is empty or over 100 code points only; the server judges characters.
- 40 — the renamer's *other* tabs update their sidebar name at the next renewal (≤15 min), a switch or a reload; their message authors update on the directory refetch.
- 41 — "Save disabled while unchanged" wins over a click in the journey; the BDD step skips the click when Save is disabled.

**Departures** (green report): `useClock` is a cache subscription instead of the plan's `skipToken` query (plan-reviewer-2's finding); `upgrade_to_head` kept as a wrapper. Red report: `ChatPage.has_own_name` added; extra tests; `test/api.ts` gained `Refusal` and `auth.updatePreferencesBy`; `ALAN` in `tests/bdd/conftest.py`.

**Open from earlier reviews**
- Code review: `useClock` re-subscribes to the query cache on every render of every message row (minor, harmless but churny on long lists); green report's heading says "round 2" (wording).
- Code review, *Unpinned*: nothing in the suite fails if `ChatLayout` stops priming `['preferences']` (mutant 7 — a probe showed the real code right; it is the only thing that loads the clock outside `/settings`); Save while a save is in flight (mutant 6); a non-name `IntegrityError` in `provision_user` (mutant 12) is re-raised on reading but no test raises one; a decomposed-form same-name save at the API, and `{"theme": null}`; `DEFAULT_IGNORABLE` is sampled in four of its ranges.
- Plan *Left*: the clock outside `/settings` — this pack covers it on the preview, since Grace's message time re-rendered on the chat page without a Settings visit after the reload.
- Plan *No test covers*: 12/24-hour output in every locale (tests use `en-US`, `en-GB`).
- The code-writer left the first real run on `docker compose up` to the human. The preview run above covers Alan's "GRACE", the 24-hour clock and Back to chat. **Not covered by anyone:** sign out on `/settings`, sign in again, land back on `/settings` (Vitest covers the return path; no browser test does).

**Found while running**
- A message time reads `09:16 PM` — a leading zero on the 12-hour hour, from `hour: '2-digit'`, as before this change. Not a regression, just how it looks beside `3:05 PM` in the plan's examples.
- The clock radios save on click with no confirmation text; the choice shows in the message times only after "Back to chat". That fits "saves at once" but a person on Settings alone sees only the radio change.
- Preferences settings are per user and global; a workspace switch on `/settings` leaves them alone, as designed. The preview's directory has both Ada's old and new names for a while in Grace's open tab until she reloads; that is Req 5.

## The run
```
01 plan-writer done [11.6m 102 turns · opus]
02 plan-reviewer changes_requested [7.1m 62 turns · opus]: 0 critical, 2 major, 7 minor
03 plan-writer done [4.7m 67 turns · opus]: all 9 findings answered
04 plan-reviewer approved [2.3m 24 turns · opus]: 1 minor, left to the code pair
05 test-writer done [16.6m 158 turns · sonnet]: 54 new failing tests, 8 files not loading, 9 green by design
06 test-reviewer changes_requested [8.9m 118 turns · sonnet]: 1 major (page not tied to the rename hook), 4 minor
07 test-writer done [0.9m 19 turns · sonnet]
08 test-reviewer approved [0.6m 18 turns · sonnet]
09 code-writer send_back [10.4m 156 turns · sonnet]: a type error in SettingsPage.test.tsx
10 test-writer done [0.4m 11 turns · sonnet]: type error fixed
11 test-reviewer approved [0.4m 13 turns · sonnet]
12 code-writer done [7.1m 14 turns · sonnet]: typecheck, build, lint, unit 1993, integration 625, e2e 25 all passed
13 code-reviewer approved [9.9m 92 turns · opus]: 0 critical, 0 major, 2 minor; 9 of 12 mutants caught
```
