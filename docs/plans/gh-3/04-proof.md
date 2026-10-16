# gh-3 — acceptance proof: accepted

## Summary
- A signed-in user opens **Settings** by clicking their name in the sidebar and renames themselves. The sidebar and their own messages show the new name at once. Another user sees it after a reload.
- Display names are unique across CollabHub, ignoring case. Alan trying "GRACE" gets "That name is already taken." on the field. The 409 body names no user, id, email or workspace, and his name stays as it was.
- The same page has a clock choice (Automatic / 12-hour / 24-hour). It saves at once, shows on message times, and is still there after a reload because Auth holds it.
- First-sign-in suffixing (`X 2`, `X 3`…) and the duplicate-renaming migration can't be seen on the preview. Integration tests prove them.

## Try it
- Origin: https://integration-subaru-womens-balance.trycloudflare.com — sign in as ada@collabhub.dev / collabhub (grace@collabhub.dev and alan@collabhub.dev too), then click your name in the sidebar.
- Quick-tunnel URLs die with cloudflared: `BRANCH=feature/gh-3 scripts/deploy.sh preview url`, or `preview up` for new ones
- Take it down: `BRANCH=feature/gh-3 scripts/deploy.sh preview down`

## Acceptance criteria
| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Ada renames herself to `ada-<run id>`; her sidebar and her own messages show it at once (Req 1, 5, 8) | `test_ada_renames_herself_and_grace_sees_it_after_a_reload` | **proven** — fails on main, which has no `/settings` | [ada](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-ada-sidebar-and-own-message-show-the-new-name.png) |
| 2 | Grace, after a reload, sees the new name on Ada's message (Req 5) | same test, second half | **proven** | [grace](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-grace-sees-the-new-name-on-adas-message.png) |
| 3 | Alan tries "GRACE": reads "That name is already taken."; his name is unchanged; the 409 names no user or workspace (Req 2) | `test_alan_cannot_take_graces_name` — asserts status 409, the exact `detail` and `errors`, no `@`, no `Workspace`, no UUID, no Grace name in the body; the saved name after a reload is still his | **proven** — on main there is no page, and without the index the PATCH would return 200 | [alan](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-alan-told-the-name-is-taken.png) |
| 4 | Grace chooses 24-hour: a message after noon shows a 24-hour time; it holds after a reload; she chooses Automatic again (Req 7) | `test_grace_chooses_the_24_hour_clock` — the browser context's zone is picked so it is about 16:00; the test first sets Automatic and checks the time reads `04:13 PM`, then 24-hour and checks `16:13`, then reloads and checks again | **proven** | [before](../../../build/acceptance/feature/screenshots/test-grace-chooses-the-24-hour-clock-chromium-automatic-shows-am-pm.png) · [after](../../../build/acceptance/feature/screenshots/test-grace-chooses-the-24-hour-clock-chromium-24-hour-time-on-the-message.png) |
| 5 | Req 1 validation: trim, 1–100, no control or invisible characters, 400 with `errors.displayName`, saving your own name is a no-op (internal) | `test_display_names.py::test_a_name_is_stored_trimmed`, `test_a_blank_name_is_400_and_nothing_changes`, `test_length_is_counted_after_trimming`, `test_an_invisible_character_is_400`, `test_saving_the_name_you_have_changes_nothing`; unit `test_display_name_rules.py` | internal | — |
| 6 | Req 2 uniqueness: case-insensitive, deleted accounts count, own capitals allowed, the concurrent rename (internal) | `test_display_names.py::test_your_own_capitals_are_free_and_nobody_elses_are`, `test_a_deleted_accounts_name_stays_taken`, `test_two_renames_to_one_name_at_once`, `test_a_rename_waits_on_a_sign_up_holding_the_name` | internal | — |
| 7 | Req 3 first sign-in suffix (the issue says it can't be checked on the preview) | `test_first_sign_in_names.py::test_the_first_free_suffix_is_taken`, `test_two_first_sign_ins_with_one_name`, `test_a_first_sign_in_through_dex_takes_a_suffix`, `test_the_own_workspace_is_named_from_the_result` | internal | — |
| 8 | Req 4 migration renames duplicates, the oldest keeps its name | `test_name_migration.py::test_duplicates_are_renamed_and_the_oldest_keeps_its_name`, `test_a_deleted_oldest_keeps_its_name`, `test_duplicates_are_found_the_way_the_index_folds_case`, `test_afterwards_a_duplicate_cannot_be_inserted` | internal | — |
| 9 | Req 6 preferences API: merge, `null` removes, unknown key or bad value is 400, `{}` and no row, 404 for a deleted account, merges of different keys both land | `test_preferences_api.py` (all), `test_merges_of_different_keys_both_land`, unit `test_preference_rules.py`, `test_r1_unreachable.py::test_a_preferences_patch_fails_open` | internal | — |
| 10 | Req 8 `/settings` on a direct load, and sign-in returning to it | Vitest `App.test.tsx` (`renders /settings on a direct load`, `takes a signed-out visitor … back to /settings`). The preview run reaches `/settings` only by the in-app link; a direct load of `/settings` wasn't driven there | internal (Vitest) | — |

## Preview
- Branch `feature/gh-3`, commit `9db8bdc` (the tree was clean when checked).
- Namespace `preview-feature-gh-3`; Helm release `collabhub` installed, status deployed.
- Origin https://integration-subaru-womens-balance.trycloudflare.com. The log ends "CollabHub is up". It shows one `curl 503` while the tunnel warmed up, and every check passed after it.

## Standard smoke pack
6 passed, 0 failed, 0 skipped: the app loads, the signing keys are published, the internal API isn't routed, Ada signs in, a message survives a reload, an image round-trips through object storage. They passed again beside the feature pack (9 passed in all).

## Feature smoke pack
`build/acceptance/smoke/test_gh_3.py`, 3 passed:
- **Ada renames herself and Grace sees it after a reload** — creates a channel and a message, renames Ada to `ada-<run id>` on Settings, goes back to chat, checks the sidebar and the author, then signs Grace in on a second context, reloads, opens the channel and checks the author. It restores Ada's name in `finally`.
- **Alan cannot take Grace's name** — reads Grace's name, tries its upper-case form as Alan, and checks the response and the field. Alan's saved name is confirmed after a reload.
- **Grace chooses the 24-hour clock** — see criterion 4. It resets Grace to Automatic at the end.

Rerun notes. My first two runs failed on my own test: Playwright's `check()` errors on a radio that is already selected, and the clock radio re-renders a moment after the click because the page awaits `cancelQueries` before the optimistic write. I switched to `click()` and an explicit `to_be_checked`. The feature was not at fault. The run is repeatable on one preview: Ada and Grace are restored, and Alan's name never changes.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — I looked at each one cited above.
- feature: `build/acceptance/feature/screenshots/`
- standard: `build/acceptance/standard/screenshots/`

## For the human
Open items from the record, with where each came from:
- **Assumed decisions** (plan): 14 (`lower()`, not full Unicode case folding), 17 (`Cf`, so a zero-width joiner and emoji ZWJ names are refused), 18–23, 25–28, 33, 34, 37 (sidebar name read from the directory). Sixteen in all.
- **`CLAUDE.md`** was edited by the first code-writer run (the D28 paragraph and the D46 tenancy exception), which a code-writer may not write. Both code reviewers found the edits accurate (green report; code-reviewer-1 and -2). A person decides whether to keep them.
- **`docs/test-report.md`** comes from `f45e31d`, before the migration fix (code-reviewer-2). Rerun `scripts/test.sh` before committing so the record shows this tree.
- **StrictMode in `npm run dev`**: a sign-in lands on `/` and not `/settings` on the dev server, but not in the built container (code-reviewer-1).
- **Back to chat from `/settings` itself**: clicking your own name while on Settings sets `from` to `/settings`, so Back goes to `/` (code-reviewer-1, plan decision 27).
- **Run migration `0002` on a copy of real data before the first deploy** (code-reviewer-2). The change to duplicate names is one-way.
- **`security.sh`**'s gitleaks and semgrep steps printed `mktemp` errors in the code-writer's environment, so they may not have run (green report).
- **Departures**: the code-writer did not make the `TABLES` and `test_schema.py` edits (the test pair made the second, and `TRUNCATE … CASCADE` makes the first unneeded); the radios also unlock after a failed read; `PATCH /users/me {}` writes nothing. The red report's departures are in `02-red-tests.md`: the no-op test reads version 2 → 0, and one App test fails earlier than the plan said.
- **Left for later stages, still open**: the unrecorded default preferences stub can't see a fetching `useClock`, and `time.test.ts` "never prints 24:05" doesn't pin `hourCycle` on this Node (test-reviewer-2). Both are low risk.
- **Found here**: the clock's optimistic change lands a moment after the click, because `onMutate` awaits `cancelQueries`. A fast observer sees the radio unselected for that instant. It's cosmetic, and the final state is right.
- **Not seen on the preview**: a direct load of `/settings` and the signed-out return. Vitest covers both (criterion 10).
- **Record**: the green report's *Left for the human* says the first real run should be in two browsers. This proof is that run.

## The run
- 01 plan-writer done · 02 plan-reviewer changes_requested · 03 plan-writer done · 04 plan-reviewer approved
- 05 test-writer done · 06 test-reviewer changes_requested · 07 test-writer done · 08 test-reviewer approved
- 09 code-writer done · 10 code-reviewer send_back (migration 0002 used Python `lower()`, the index uses Postgres `lower()`)
- 11 test-writer done · 12 test-reviewer approved · 13 code-writer done · 14 code-reviewer approved
- 15 acceptance-reviewer: approved (this proof)
