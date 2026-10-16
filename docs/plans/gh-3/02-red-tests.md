# Red tests — gh-3, round 1

BDD outside-in with the rules pushed down the pyramid, as the plan recommends: 1 journey, Auth unit rules (2 files), Auth
integration (4 new files + 1 changed), and the SPA's Vitest (13 files touched). Every new test is red except the ones marked
*green by design*; four Vitest files and both Auth unit files fail at load because every test in them needs the missing module.
Nothing but test files, the two shared Vitest helpers and the BDD page object/fixtures was written.

## Baseline
| File | Before | After |
|---|---|---|
| `lib/auth/session.test.ts` | 19 passed | 19 pass + 8 new fail |
| `App.test.tsx` | 6 passed | 6 pass + 1 new passes (green by design) + 2 new fail |
| `ChatLayout.test.tsx` | 2 passed | 2 pass + 3 new fail |
| `MessageItem.test.tsx` | 10 passed | 10 pass + 1 new fails |
| (4 files together) | 37 passed | 37 pass, as before |
| Whole Vitest | 503 passed (plan) | 505 passed, 27 failed, 4 files fail to load |
| `test_r1_unreachable.py` | 4 (collected; run before my edit was impossible — added in the same pass, the 4 old tests all pass) | 4 old pass + 1 new passes (green by design) + 1 new fails |

Auth unit baseline is 59 (plan); after, the unit directory cannot collect (the two new files fail at import). Auth integration and
BDD have no recorded baseline (plan).

## Tests
`red` = first failure line, verbatim. Vitest "load" = `Failed to resolve import …`.

| File · test | Layer | Task | Proves | Observed red | Match |
|---|---|---|---|---|---|
| `test_display_name_rules.py` (all, ≈14 incl. parametrised) | unit | 1 | trim, blank, length after trim, Cf/Cc/Zl/Co refused, unicode kept, IdP cleaning, suffix sequence, long-base cut and no double space | `ModuleNotFoundError: No module named 'auth.names'` (collection) | yes |
| `test_preference_rules.py` (5) | unit | 1 | set / null removes / absent leaves / unknown key `loc` / bad value `loc` | `ModuleNotFoundError: No module named 'auth.preferences'` | yes |
| `test_display_names.py::test_a_name_is_stored_trimmed` | integ | 2 | trim stored | `AssertionError: assert '  Ada L  ' == 'Ada L'` | yes |
| `…::test_a_blank_name_is_400_and_nothing_changes` | integ | 2 | 400 + `errors.displayName`, name kept | `assert 200 == 400` | yes |
| `…::test_length_is_counted_after_trimming` | integ | 2 | padded 100 → 200; 101 → 400 | `assert 400 == 200` | yes |
| `…::test_an_invisible_character_is_400` | integ | 2 | ZWSP refused | `assert 200 == 400` | yes |
| `…::test_a_taken_name_is_409_and_names_nobody` | integ | 2 | 409 contract, no `@`/id/"Workspace" | `assert 200 == 409` | yes |
| `…::test_your_own_capitals_are_free_and_nobody_elses_are` | integ | 2 | own ADA 200; Grace→ada 409 | `assert 200 == 409` | yes |
| `…::test_case_folding_covers_accented_capitals` | integ | 2 | É/é on the real image | `assert 200 == 409` | yes |
| `…::test_saving_the_name_you_have_changes_nothing` | integ | 2 | no-op (also padded) writes nothing; real rename bumps version +1 | `assert (2, datetime…) == (0, datetime…)` | yes (version moved on the no-op; 2 because two no-op PATCHes — plan said 0→1) |
| `…::test_the_same_name_with_an_avatar_still_writes_the_avatar` | integ | 2 (added) | no-op needs "nothing else sent" | passes — *green by design* | n/a |
| `…::test_a_deleted_accounts_name_stays_taken` | integ | 2 | deleted holder | `assert 200 == 409` | yes |
| `…::test_two_renames_to_one_name_at_once` | integ | 2 | `[200, 409]`, one row | `assert [200, 200] == [200, 409]` | yes |
| `…::test_a_rename_waits_on_a_sign_up_holding_the_name` | integ | 2 | rename queues on uncommitted holder | `AssertionError: the rename went ahead without waiting on the uncommitted holder of the name` | yes |
| `…::test_a_sign_up_after_a_rename_takes_a_suffix` | integ | 2 | rename then sign-up | `assert 'Sam' == 'Sam 2'` | yes |
| `test_first_sign_in_names.py::test_the_first_free_suffix_is_taken` | integ | 2 | Sam/Sam 2/Sam 4 → Sam 3 | `assert 'Sam' == 'Sam 3'` | yes |
| `…::test_a_free_name_is_kept_as_it_is` | integ | 2 (added) | positive half: Samantha stays | passes — *green by design* | n/a |
| `…::test_suffixing_ignores_case` | integ | 2 | sam/SAM | `assert 'SAM' == 'SAM 2'` | yes |
| `…::test_a_deleted_accounts_name_is_skipped` | integ | 2 | deleted counts | `assert 'Sam' == 'Sam 2'` | yes |
| `…::test_the_own_workspace_is_named_from_the_result` | integ | 2 | "Sam 3's Workspace" | `assert 'Sam' == 'Sam 3'` (user name asserted first) | yes (first assertion; workspace name check follows) |
| `…::test_an_idp_name_is_cleaned` | integ | 2 | cleaned name + workspace | `assert ' Sam​ ' == 'Sam'` | yes |
| `…::test_two_first_sign_ins_with_one_name` | integ | 2 | second insert queues, falls to Sam 2 | `AssertionError: the second sign-in did not wait on the first one's uncommitted name` | yes |
| `…::test_a_first_sign_in_through_dex_takes_a_suffix` | integ | 2 | whole path | `assert 'ada' == 'ada 2'` | yes |
| `…::test_sign_in_never_overwrites_a_name` | integ | 2 | guard for `provision_user` rewrite | passes — *green by design* (plan) | n/a |
| `test_name_migration.py` (4) | integ | 2 | dedupe order, deleted oldest, cleaning, index afterwards (+ `user_preferences` exists) | `ImportError: cannot import name 'upgrade' from 'auth.migrations'` (collection) | yes |
| `test_preferences_api.py::test_no_preferences_read_as_an_empty_object…` | integ | 2 | GET `{}`, no row | `assert 404 == 200` | yes |
| `…::test_a_patch_is_read_back` · `test_null_removes_a_key` | integ | 2 | PATCH/GET/null | `assert 404 == 200` | yes |
| `…::test_an_unknown_key_…` · `test_a_bad_value_…` | integ | 2 | 400 `errors.<key>`, nothing changes | `assert 404 == 400` (the setup PATCH asserts 200 first, so the reason is the missing route) | yes |
| `…::test_merges_of_different_keys_both_land[with_row/without_row]` | integ | 2 | atomic merge, blocks, both keys land | `ImportError: cannot import name 'preferences' from 'auth'` (in test body) | yes |
| `…::test_preferences_are_per_user_not_per_workspace` | integ | 2 | across a workspace switch | `AssertionError: assert {'type': 'htt…` — the setup PATCH (404 body) | yes (404; message carries the problem body) |
| `…::test_a_deleted_account_gets_404_on_both` | integ | 2 | handler 404 with detail | `KeyError: 'detail'` | yes |
| `…::test_preferences_need_a_token` | integ | 2 | 401 | `assert 404 == 401` | yes |
| `test_r1_unreachable.py::test_a_rename_fails_open` | integ | 2 | keeps `require_user` | passes — *green by design* (plan) | n/a |
| `…::test_a_preferences_patch_fails_open` | integ | 2 | fail open | `assert 404 == 200` | yes |
| `time.test.ts` (3 describes, 8) | Vitest | 3 | formatters by clock/locale, h23 midnight, Automatic = browser | load: `Failed to resolve import "./time"` | yes |
| `storage.test.ts` (11) | Vitest | 3 | `returnPath` take-once, clear, open-redirect list, positive `/c/abc?message=m` | `TypeError: Cannot read properties of undefined (reading 'write')` | yes |
| `session.test.ts` · `updateProfile` ×6 | Vitest | 3 | replace, other id, signed out, renewal race both orders, later renewal wins | `TypeError: session.updateProfile is not a function` | yes |
| `session.test.ts` · `signIn … path to return to` ×2 | Vitest | 3 | stores / clears | `AssertionError: expected null to be '/settings'`; `expected '/c/left-over' to be null` | yes |
| `App.test.tsx` · `renders /settings on a direct load` | Vitest | 3 | route | `Unable to find role="heading" and name "Settings"` | yes |
| `App.test.tsx` · `takes a signed-out visitor … back to /settings` | Vitest | 3 | guard→return | `Unable to find role="button" and name "Sign in"` (no `/settings` route, so NotFound renders) | **differs**: plan said "stored null"; the earlier stop is the missing route. Past it, the stored-path assertion is next |
| `App.test.tsx` · `lands on / when no path was remembered` | Vitest | 3 | guard | passes — *green by design* (plan) | n/a |
| `ChatLayout.test.tsx` · links to Settings | Vitest | 3 | link + `state.from` | `Unable to find role="link" and name "Ada Lovelace"` | yes |
| `ChatLayout.test.tsx` · names the user as the directory does | Vitest | 3 | decision 37 | `expected [ <span …(2)></span> ] to have a length of 2 but got 1` (author row already 'Ada L'; sidebar not) | yes |
| `ChatLayout.test.tsx` · falls back to the session's name | Vitest | 3 | fallback | `Unable to find an accessible element with the role "link" and name "Ada Lovelace"` | yes (fails for no link, the fallback half of 37 is pinned once the link exists) |
| `MessageItem` / `ThreadSummary` / `SearchResult` · follow the clock | Vitest | 3 | cache change re-renders, nothing fetched | `Unable to find an element with the text: 13:05` | yes (en-US default is 12-hour) |
| `ThreadSummary.test.tsx` · shows nothing at zero replies | Vitest | 3 (added) | characterisation of existing file | passes — *green by design* | n/a |
| `SettingsPage.test.tsx` (≈14 incl. each) | Vitest | 3 | prefill, Save states, 409, 400, Saved, clock shows/saves/every-visit/failed save, Back to chat ×3, workspace switch | load: `Failed to resolve import "./SettingsPage"` | yes |
| `useProfile.test.tsx` (5) | Vitest | 3 | rename own view; refused leaves all; unmount; directory race; profile race | load: `Failed to resolve import "./useProfile"` | yes |
| `usePreferences.test.tsx` (7) | Vitest | 3 | optimistic; revert; order/scope; failure behind a later; all fail; read in flight; `useClock` | load: `Failed to resolve import "./usePreferences"` | yes |
| `display_names.feature` (1 scenario) | BDD | 4 | journey | see BDD | — |

## Types
`npm --prefix src/frontend run typecheck` — 22 errors, all the missing contract:
- `Clock`, `Preferences` not exported from `lib/auth/api` (`test/api.ts`, `SettingsPage.test.tsx`, `usePreferences.test.tsx`) — decision 9 / Task 7 interface.
- `Cannot find module './SettingsPage' | './usePreferences' | './useProfile' | './time'`.
- `session.updateProfile` missing (6) and `signIn` taking one argument (1).
- `returnPath` not exported from `./storage`.
- `TS7006` implicit-any `patch` ×5 — the callback param types come from `Preferences`, so they vanish with it.

## BDD
`uv run pytest tests/bdd --collect-only -q`: 25 collected, including `test_display_name_steps.py::test_grace_sees_the_name_alan_gives_himself_after_a_reload`.
`uv run pytest tests/bdd --generate-missing --feature tests/bdd/features`: prints nothing — every step binds.
Expected red against the current SPA: the scenario clears the Background and the setup steps (Alan joins `CollabHub Demo`,
creates `general`, sends), then stops at `When Alan renames himself…`: `rename_self` clicks `current-user` (a `<p>`, no navigation) and
waits for `display-name-input`, which does not exist (no `/settings`). It was not run (needs the Compose stack).

## Departures from the plan
- **Added tests:** `test_the_same_name_with_an_avatar_still_writes_the_avatar` (the no-op rule's "nothing else sent" input held
  apart), `test_a_free_name_is_kept_as_it_is` (positive half of the suffix tests), `test_a_cut_stem_loses_its_trailing_space`,
  `test_ordinary_unicode_is_kept`, `Zl`/`Co` parametrised refusal, `test_the_wire_name_is_the_key_itself`; Vitest:
  `useUpdateDisplayName … leaves everything as it was when the server refuses`, `updateProfile … does nothing when signed out`,
  `… does not stop a later renewal from taking what the server holds` (the epoch counter must guard only a fetch in flight), `timeOfDay
  never prints 24:05 for just after midnight` (decision 33), `ThreadSummary shows nothing at zero replies`, `App … lands on /`.
- **Migration**: the `at_0001` fixture is sync and function-scoped as planned. The plan reviewer's doubt about `asyncio.run` there was
  checked with a throwaway probe (two tests, a function-scoped sync fixture calling `service_database`): both passed. Probe removed.
- **Red differs** for `App … back to /settings` (above), and `test_saving_the_name_you_have_changes_nothing` reads version 2→0 not
  1→0 (it sends two no-op saves).
- **Shared helpers changed** (needed by the plan's tests; all under `src/frontend/src/test/` or `tests/bdd`): `api.ts` — the plan's
  `auth.updateMe / preferences / updatePreferences` and unrecorded default `GET …/me/preferences → {}`, plus **`auth.meBy`**
  (`GET /users/me` answered per request, holdable and recorded) which the profile-race and prefill tests need; `render.tsx` — a
  `routeState` option on `renderWithProviders` (the `Back to chat` tests need `location.state`); `bdd/conftest.py` — `ALAN`,
  `alan_context`, `alan`; `chat_page.py` — `rename_self`, `own_name`, `has_own_name`.
- **`ChatLayout` tests** render the real `ChannelView` to see the author line (the plan says "a message by her in the open channel").
- **Not written:** nothing from the plan was dropped.

## Picked up from earlier reviews (plan-reviewer-2, *Left for later stages*)
- **Active observer for the in-flight tests** — both `usePreferences` and `useProfile` race tests render `usePreferences` /
  `useProfile` beside the mutation hook, and the GET goes through recorded stubs (`auth.preferences`, `auth.meBy`). Done.
- **`asyncio.run` in a sync function fixture** — probed; works (see above).
- **`merge` leaves the commit to its caller** — the merge test commits both sessions itself, so a `merge` that commits inside would
  release A's lock early and fail the "must block" assertion.
- Carried assumptions (decisions 14, 17, 37) — test 14 on the real image (`test_case_folding_covers_accented_capitals`), 17
  (ZWSP/Zl/Co tests, `Cf` includes ZWJ though no test asserts an emoji sequence), 37 (ChatLayout tests).

## For the code-writer
- `auth.names.candidates` is exercised through `islice`; keep it a lazy iterator.
- `identities.provision_user(session, email=, display_name=, demo_workspace_name=)` is called with a session the test then commits
  or holds open: it must flush (take the name's unique-index entry) before returning and **must not commit**, or the two
  racing-provision tests cannot hold the lock. Same for `preferences.merge(session, user_id: UUID, set_, remove)`: flush only.
- `waiting_on_a_lock` polls a *fresh* session each time (stat snapshots), so the blocking statement must really wait in Postgres.
- `test_name_migration.py` calls `auth.migrations.upgrade(dsn, "0002")` with positional revision and `partial(upgrade, revision="0001")`.
- Auth's `TABLES` in the integration conftest gains `"user_preferences"` first, and `test_schema.py` changes, in GREEN (plan).
  Until then, truncating `users` with a `user_preferences` row would fail — the preferences tests leave a row behind, so do this in
  the same step as the table.
- The SPA tests write cache keys as literals: `['preferences']`, `['profile','me']`, `['workspace-members', ws]`.
- `SettingsPage` pinned beyond the plan's markup: radios are rendered *disabled* until the server's preferences have arrived since
  mount (`the clock is read from the server on every visit` asserts all three disabled while the GET is held); the display-name
  textbox does not exist until `GET /users/me` has answered since mount; Saved is `role="status"`.
- `session.signIn(provider, returnTo)` must clear a previous `collabhub.returnTo` when `returnTo` is absent (test pins it).
- `returnPath.take()` also validates on the way out (a bad value written straight to storage is dropped and cleared).
- `useSetClock` test timing: two `mutate()` calls in one `act` — the second's `onMutate` must run (and the cache show `12h`) while
  the first request is still held; the second request must not be sent until the first settles.
- `useUpdateDisplayName`'s success marks `['profile','me']`, each `['workspace-members', *]` entry *invalidated* (asserted via
  `isInvalidated` while the queries have no observer).
- Formatter tests assume `hourCycle` (decision 33); Automatic must equal `toLocale*String([], {…})` exactly.
- Task 1 `Zl` row in the plan puts U+2028 at the end of the name, where `strip()` trims it. Follow decision 17 as written: the refusal test now uses an interior separator, and a trailing one is trimmed and accepted.

## Review responses (round 2, to test-reviewer-1)
1. Fixed — the `Zl` case is now interior (`"Ad" + LINE_SEP + "a"`, id "interior line separator (Zl)"). Added `test_a_trailing_line_separator_is_trimmed_not_refused` (trailing U+2028 trims to "Ada"), pinning "after trimming" from the other side. Unit directory still fails at collection (`ModuleNotFoundError: auth.names` / `auth.preferences`), as before.
2. Fixed for preferences — `usePreferences.test.tsx` "is not undone by a read that was already in flight" now holds the PATCH, releases the old GET while the PATCH is pending, and asserts `24h` before releasing the PATCH. It fails a build with no `cancelQueries` in `onMutate`. It is red at load (missing module) and hasn't been run against code. Declined for `useProfile.test.tsx`: the plan (decisions 29/30) has no cancel before the rename PATCH. The rename is not optimistic, so the old name is correct while the PATCH is pending, and asserting the new name then would fail a correct build. The cancel there is the invalidate's `cancelRefetch`, which those two tests do pin: without the invalidate, the released old answer wins.
3. Partly fixed — `Saved` is now `findByText('Saved')` and then the `status` role is checked. Left for a later stage: the unrecorded default `GET …/me/preferences` can't see a fetching `useClock` (low risk, since the plan makes it a cache subscription). `time.test.ts` "never prints 24:05" is a guard for other ICU builds and does not pin `hourCycle` on this Node.
