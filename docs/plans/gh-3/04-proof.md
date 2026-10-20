# gh-3 — acceptance proof: accepted

## Summary
- A signed-in user clicks their name in the sidebar, lands on `/settings`, and renames themselves. The sidebar and their own message authors show the new name at once. Another user sees it after a reload.
- Display names are unique across CollabHub, ignoring case. Alan trying `GRACE` is refused with a 409, "That name is already taken.". His name stays the same, and the 409 body names no user, email or workspace.
- Settings also holds the first preference, the clock (Automatic / 12-hour / 24-hour). Choosing 24-hour re-renders message times as 24-hour, and the choice survives a reload because Auth stores it.
- All three visible checks from the issue's *Acceptance* section pass on the branch's preview. Ada and Grace are restored afterwards (Ada to her original name, Grace to Automatic), and Alan's name was never changed.

## Try it
- On GitHub, the PR's own preview: its origin is in the preview comment on the PR, and it stays up until the PR is approved or closed. Sign in as ada@collabhub.dev (grace@collabhub.dev too) with the preview password, which goes to the delivery's Slack thread — `collabhub` where Slack isn't set up
- Locally: `BRANCH=feature/gh-3 scripts/deploy.sh preview up`, then `preview url`; `preview down` when you're done

## Acceptance criteria
Visible = a person can see it in the running app; internal = only a test shows it.

| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Req 1 — rename yourself from Settings (trim, NFC, refused characters) | visible part: `test_ada_renames_herself_and_grace_sees_it_after_a_reload`. Rules: `auth/tests/unit/test_names.py`, `test_display_names.py::test_a_rename_is_stored_trimmed_and_nfc`, `::test_a_refused_name_is_400_on_display_name_and_changes_nothing` | proven (the page doesn't exist on `main`) | [settings saved](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-settings-saved.png) |
| 2 | Req 2 — names unique everywhere, case-insensitive; 409 names nobody | visible: `test_alan_cannot_take_graces_name`. Internal: `test_display_names.py::test_a_taken_name_is_409_and_names_nobody`, `::test_names_differing_only_in_normalisation_collide_both_ways`, `::test_two_renames_to_one_name_at_once` (the race), `::test_a_deleted_accounts_name_stays_taken` | proven (on `main` the PATCH would succeed) | [name taken](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-name-taken.png) |
| 3 | Req 3 — first sign-in takes the first free suffix | `test_display_names.py::test_a_first_sign_in_with_a_taken_name_gets_the_first_free_suffix`, `::test_two_first_sign_ins_with_one_name_both_succeed`. The issue says the preview can't show it. | internal | — |
| 4 | Req 4 — migration renames existing duplicates | `test_name_migration.py` (5 tests, including `…_but_the_oldest_is_renamed`, `…_only_normalising_reveals_are_renamed`) | internal | — |
| 5 | Req 5 — the renamer sees it at once; others on their next directory fetch | `test_ada_renames_herself_and_grace_sees_it_after_a_reload`: Ada's sidebar and her own message author; Grace first reads the old name, then the new one after a reload | proven | [Ada's message](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-own-message-author.png), [Grace's view](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-grace-sees-new-name.png) |
| 6 | Req 6 — preferences store: GET/PATCH, merge, `null`, 400s, 404 | the clock saving and surviving a reload in `test_grace_chooses_24_hour…` shows it on the wire. Rules: `test_preferences.py` (integration, 11 tests), `auth/tests/unit/test_preferences.py`, `test_r1_unreachable.py` | internal for the rules; the happy path is seen in 7 | — |
| 7 | Req 7 — the clock applies to message times; saves at once | `test_grace_chooses_24_hour_and_message_times_follow`: starts on 12-hour (AM/PM), then 24-hour. The shown hour equals the 24-hour hour of the message's `datetime`, and it holds after a reload. Thread-summary and search-result times: `clockSites.test.tsx` (Vitest) | proven for messages; **regression check** for the other two formatters, which the preview pack doesn't open (`clockSites.test.tsx`: `a thread summary time follows it`, `a search result time follows it`) | [24-hour time](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-and-message-times-follow-chromium-24-hour-time.png) |
| 8 | Req 8 — the page: Profile, Preferences, Back to chat, a reload reads the server | `test_alan_cannot_take_graces_name` reloads on `/settings` and the field holds the server's name; `Back to chat` is used in tests 1 and 3. Disabled-Save rules and the signed-out return: Vitest `ProfileSection.test.tsx`, `App.test.tsx` | proven (direct-load and reload); the Save-disabled states are Vitest-only | [Settings page](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-name-taken.png) |

## Preview
- Branch `feature/gh-3`, commit `d0dde9a`, tree clean when the packs ran. The packs live under the ignored `build/acceptance/`.
- Namespace `preview-feature-gh-3`; Helm release `collabhub`, revision 1, `STATUS: deployed`.
- Origin `https://parish-geological-economic-camcorder.trycloudflare.com`. The preview log says "preview is up", and the app, the JWKS and the internal-API checks in the standard pack passed against it.
- The tunnel is gone by the time anyone reads this.

## Standard smoke pack
**Passed: 6 of 6**, none failed or skipped (run first, on its own, and again beside the feature pack: 6 of 6 both times).
App loads without errors; signing keys published; internal API not routed; Ada signs in to the shared workspace; a message survives a reload; an image round-trips through object storage.

## Feature smoke pack
`build/acceptance/smoke/test_gh_3.py`, run against the preview: **3 of 3 passed** (9 of 9 with the standard pack). Each user is its own: Ada, Alan and Grace in three browser contexts.
1. `test_ada_renames_herself_and_grace_sees_it_after_a_reload` — Ada makes a channel and a message. Grace reads "ada" on it first. Ada renames herself `ada-<run id>`. Her sidebar and her message author show it, and Grace sees it after a reload. Ada is renamed back in `finally`. Fails without the change: there is no Settings page.
2. `test_alan_cannot_take_graces_name` — Alan enters `GRACE` and saves. The PATCH answers 409 with `detail` and `errors.displayName` both "That name is already taken.". The body holds none of "grace", "alan", "@" or "workspace". The alert shows, his sidebar name is unchanged, and the field still holds his name after a reload. Fails without the change: on `main` the PATCH succeeds, and there is no page.
3. `test_grace_chooses_24_hour_and_message_times_follow` — Grace sends a message, chooses 12-hour (the time reads AM/PM), then 24-hour (no AM/PM, and the hour equals the local 24-hour hour). A reload keeps it. She returns to Automatic in `finally`. The 12-hour start means only the change decides the format.

**One fix to my own test**: the first run failed in the cleanup. Playwright's one-shot `check()` read the Automatic radio before it flipped. I switched to `click()` with a retrying expect. See *For the human* — the flip happens a moment after the click.

## Screenshots
**1. Ada's Settings after saving — "Saved", the sidebar already reads her new name.**

![Ada saved her new name](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-settings-saved.png)

**2. Alan typing `GRACE` — the field error "That name is already taken." and his sidebar still reads "alan".**

![Name taken](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-name-taken.png)

**5a. Ada, back in the chat — the author of her own message is her new name.**

![Ada's own message author](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-own-message-author.png)

**5b. Grace, after a reload — the same message is by Ada's new name.**

![Grace sees the new name](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-after-a-reload-chromium-grace-sees-new-name.png)

**7. Grace on 24-hour — the message time reads "21:58", no AM/PM.**

![24-hour time](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-and-message-times-follow-chromium-24-hour-time.png)

**8. The Settings page — Profile, Preferences with the three clock options, and the "Back to chat" link (same screenshot as 2).**

![Settings page](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-name-taken.png)

## For the human
**Assumed decisions in the plan** (decisions 17, 23–36 were marked assumed; the ones a user could notice):
- 17: with two failed or mixed clock saves, the tab ends on the last saved choice. A failed first save under a successful second shows no error.
- 23: saving the name you have is a 200 and writes nothing (no version bump). The code does this only for a name-only PATCH (departure 1 below).
- 24: an IdP name Req 1 would refuse is cleaned (refused characters dropped, cut to 100, fallback to the email's local part, then "user") rather than failing sign-in.
- 26: the migration trims and NFC-normalises only. A stored name with refused characters, or over 100 characters, is left for its owner to change. An empty one takes the email's local part.
- 28–29, 31: Save is disabled by length and emptiness only (the character rules come from the server's 400). The 400 wording is the plan's. "Saved" shows until the next edit.
- 32–34: Back to chat goes to the last channel opened in the active workspace, else `/`. A workspace switch on Settings keeps the page and an unsaved edit. The return-to-route after sign-in is built for every protected route, not only `/settings`.
- 36: the profile form waits for this visit's fetch and shows "Loading…" first.

**Departures** (green report): (1) the unchanged-name early return applies only when no `avatarAsset` is sent. (2) A failed profile fetch shows the error banner, with no field. (3) The preferences 400's `detail` is "Some preferences are invalid.". Red report: invisible characters are named constants in the tests, not `\u` escapes; the harness stubs gained a few helpers.

**Open from the reviews (Left for the human):**
- Code review (minor): **Back to chat after a workspace switch made on a channel page** goes to `{new workspace, old channel}` and shows that channel's 404 instead of `/`. Round 1's probe in `App.test.tsx` is the red test to start from.
- Code review (minor): **a failed background refetch on Settings** replaces the form with the error banner and loses typed text. Gate the banner on `data === undefined`. Untested.
- Code review (cosmetic): the field error stays after the user edits the field, until the next save.
- 12/24-hour in a non-en locale (e.g. `ja-JP`) was not checked in a browser. The pack ran in `en-US`.
- The 0002 migration over real duplicate data, and the rolling-deploy window, were not run by hand on the Compose stack (green report, Task 10). The migration is covered by `test_name_migration.py` (5 tests, passing).
- Plan *Found while building* 6: `.claude/hooks/security.sh` prints `mktemp: too few X's` in the runner.

**Unpinned** (code review round 1/2, held by reading only): the refetch of a directory that had no data when the rename landed (a probe passed, no test holds it); `hourCycle` over `hour12` (en-US output is the same, so no test can tell); `is_display_name_conflict` re-raising other IntegrityErrors; the migration's `LOCK TABLE` and the `version`/`updated_at` bump; `completeSignIn` clearing the return path on each failure branch.

**Found on the preview:**
- **A rough edge, not a failure:** the clock radio flips a moment after the click, because the optimistic cache write waits on `cancelQueries`. A one-shot `Locator.check()` (Playwright) read it too early. A person won't notice, but it is why the pack uses a retrying expect.
- **A criterion met in a way a person might not expect:** Settings is inside the chat shell, so the sidebar and the full channel list show beside it (screenshots). That is plan decision 21.
- **Left behind on the preview:** the pack's `smoke-…` channels and messages (named with the run id), as the standard pack does too. The users' names and clock are restored.
- In `en-US`, Automatic and 12-hour look the same, so the pack can't tell them apart. The Vitest `time.test.ts` covers Automatic.

## The run
1. plan-writer done — 13 assumed decisions, 6 corrections to the issue (12.5m, opus).
2. plan-reviewer changes_requested — 2 major, 2 minor (decision 17's save order, decision 35's renewal race).
3. plan-writer done — all four findings answered (round 2).
4. plan-reviewer approved — no new findings.
5. test-writer done — 33 Auth integration tests red, 21 Vitest red, 4 SPA files unloaded, BDD journey binds.
6. test-reviewer changes_requested — 1 critical (`clockSites` asserted before TanStack's timer), 1 major, 2 minor.
7. test-writer done — both fixed.
8. test-reviewer approved.
9. code-writer send_back — 3 migration tests had their seed `created_at` reversed.
10. test-writer done — seed helper fixed; 5 migration tests pass.
11. test-reviewer approved.
12. code-writer done — send-back answered; unit 1973, integration 616 green.
13. code-reviewer changes_requested — 1 major (stale D28 text in 3 places), 2 minor.
14. code-writer done — the major fixed; the minors left for the human.
15. code-reviewer approved — 0 critical, 0 major, 2 minor carried over.
16. acceptance-reviewer (this pass) — standard pack 6/6, feature pack 3/3, approved.
