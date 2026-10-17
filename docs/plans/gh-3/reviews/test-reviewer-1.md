# Test review — gh-3, round 1: approved

The red is real. All 138 new tests fail, or fail to load where every test needs the missing module, for the reason the plan gives. My own correct sketch turned every SPA and unit test green, and the wrong builds I named went red. Nothing is critical or major; four minor items go to the code pair.

## Expectations

Written from the issue, the plan (RED Tasks 1–4), plan-reviewer-2's leftovers and the code as it
stands (`routers/users.py`: `PATCH /me` assigns `body.display_name` raw, bounds are in the schema;
`identities.provision_user` inserts the raw name; no `names`/`preferences` modules; no
`/settings` route, `lib/time`, `updateProfile`, `takeReturnPath`, `lastChannelId`), before opening
any test.

**Auth units (`test_names.py`, `test_preferences.py`).** Fail today: `ModuleNotFoundError` at
collection, every test needs the module. Vacuous: refused-example tests that only check "raises"
without the single offending char inside the name (a trailing U+2028 is stripped by `strip()`);
default-ignorable tests that only hit Cf (a Cf-only build passes U+115F/FE0F/E0100/17B4); length
pinned at 100 but not 101, or counted before NFC; key test using only ASCII case (a `lower()` build
passes without `ß`); `first_free` with only "X taken". Wrong builds: `lower()` key, validate before
trim, count before NFC, `dedupe` renaming the kept `X 2`, `dedupe` suffixing in `id` order not
`created_at`, `parse_patch` stopping at first error.

**Auth integration (`test_users`, `test_display_names`, `test_migration_0002`, `test_preferences`,
`test_r1_unreachable`, `test_schema`).** Fail today with assertions (200 where 400/409), `AttributeError`
on `rename_user`, `CommandError` for revision 0002, 404 for missing routes. Vacuous: a 409 test that
accepts any 409 without checking `errors.displayName`/detail and that the body names nobody; the 404
for deleted preferences that doesn't assert `detail` (route-missing 404 passes); `/preferences`
needs-token test passing on 404 (must be 401 and fail today); own-capitals test without Grace's
follow-up; race test with a sleep instead of a real lock wait, or a SELECT-then-UPDATE build passing;
legacy name test passing because the first PATCH is also rejected; migration tests where oldest
`created_at` coincides with oldest id; no-op check that doesn't read `version` (today it bumps).
Wrong builds: `lower(display_name)` functional index; pre-check without unique index; 409 mapped from
any IntegrityError (email index); preferences merge as read-modify-write; `null` as 422; unknown
key silently dropped while valid keys applied.

**BDD.** Must parse and bind (collect/generate-missing); `alan` fixture; last Then must be Grace after
reload (server), not Alan's optimistic view; selectors only in page object.

**Vitest.** Red: import-resolution (`./time`, `./ClockProvider`) or `is not a function`, or
*No such page* for `/settings`; must not load-fail files that could run. Vacuous: save test that
doesn't hold the post-save refetch (invalidate-only passes); uncached-directory race (set-then-invalidate
passes); late-failure test without the `12h` PATCH; second-choice test with a synchronous negative count
(plan-reviewer's note — needs a macrotask first); clock tests using imported constants; automatic test
that compares to nothing; midnight `00:05`; `24h` case that is trivially true in the locale;
unmount test that releases while still mounted; workspace-switch test with no positive. Existing tests
(ChatLayout etc.) only gain a stub, nothing weakened.

**Report.** Matches `git status`; no production code; counts.

## What ran

- `uv run pytest src/services/auth/tests/unit -q`: both new files fail to collect (`No module named 'auth.names'`, `'auth.preferences'`). The 59 existing unit tests were not collected, because collection is interrupted.
- `uv run pytest` over `test_users`, `test_display_names`, `test_migration_0002`, `test_preferences`, `test_r1_unreachable` and `test_schema`: **34 failed, 21 passed**. Docker was reachable. The first lines match the report's *Observed red* row for row: `200 == 400`, `200 == 409`, `AttributeError … rename_user`, `B never blocked on the name index`, `Can't locate revision identified by '0002'`, `404 == 200`, `KeyError: 'detail'`, `DID NOT RAISE IntegrityError`, `ModuleNotFoundError` for the merge race only. The 21 that pass are the existing ones plus the email-index test, which passes by design.
- `npm --prefix src/frontend test` (whole suite): **36 failed, 503 passed**, plus `time.test.ts` and `ClockProvider.test.tsx` failing to load (`Failed to resolve import "./time"` / `"./ClockProvider"`). Every test in those two files needs the missing module. The 503 are the baseline, so no existing test regressed.
- `npm --prefix src/frontend run typecheck`: errors only for `Clock`, `Preferences`, `PreferencesPatch`, `./time`, `./ClockProvider`, `updateProfile`, `takeReturnPath`, `signIn`'s second argument, `lastChannelId`, `resetLastChannel`, and three `TS7006` that follow from the missing `Preferences` type. This matches the report's *Types*.
- BDD: `--collect-only` collects 25 and `--generate-missing --feature …settings.feature` prints no stub, so every step binds. The journey cannot run before the code-writer.
- **Sketch, frontend** (`sketch.sh frontend`, built from the plan's interfaces): correct build over `time`, `ClockProvider`, `SettingsPage`, `App`, `session`, `chat.test`: 85 of 86 passed. The one red was `goes back to the last channel, or home after a direct load`, because my sketch did not reset `lastChannelId` when the shell unmounts. With `resetLastChannel()` added to `ChatLayout`'s existing cleanup effect (the plan's Task 8), `SettingsPage.test.tsx` was 16 of 16.
- **Sketch, wrong builds** (`SettingsPage.test.tsx`): no mutation `scope` → red, only `sends a second choice only after the first…`. `cancelQueries` removed → red, only `first directory fetch that is still out…`. No `setQueriesData` (invalidate only) → red, 3 tests (`updates the sidebar…`, `lands after leaving`, `already in flight`). No `session.updateProfile` → red, 2 tests. Unconditional `onError` restore → red, `late failure…`.
- **Sketch, Python** (`sketch.sh service auth`): a pure `names.py` and `preferences.py` to the plan's interfaces → all 48 unit tests passed. Wrong builds for these were not rerun; the report's run (`lower()` key, category-only check, count before NFC, kept names not reserved) is the writer's claim, and I read each test against its fixture instead (see *Checked and sound*).
- **Integration was not sketched.** A full Auth build (models, two migrations, routes, the upsert) is large. I reasoned through the race fixtures instead: A holds an uncommitted key, B's insert, update or upsert waits on it, which is `wait_event_type = 'Lock'`, and the index is the only thing that can make B fail afterwards. The report claims 157 integration tests green against its own sketch, and 9 red with a non-unique index. That claim is **unverified** by me.
- `.claude/delivery/sketch.sh clean` run.

## Coverage

| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| Task 1 rules (refused, accepted, categories, ignorables, length, stored_form, key, first_free, provision_name, dedupe ×4) | `test_names.py`, 36 cases | present; `Strauß` / `STRASSE` → `STRAUSS` is a sound departure, since `casefold()` of `Strauß` is `strauss` |
| `parse_patch` | `test_preferences.py` unit, 12 cases | present |
| Rename over REST (trim/NFC, 5 refusals, no-op, 409, NFC collision, own capitals + Grace, legacy, deleted) | `test_users.py` | present, every row |
| Race, sign-in racing rename, two sign-ins, Dex suffix, deleted skipped | `test_display_names.py` | present; the last is outcome-only (see *Left for later stages*) |
| Migration ×3 | `test_migration_0002.py`, 4 tests | present; adds an `id`-vs-`created_at` fixture |
| Preferences routes + merge race + 401 + 404 `detail` | `test_preferences.py` | present, plus an empty-patch test |
| Fail-open of both PATCHes; `test_schema` | present | present |
| `TABLES` gains `user_preferences` | not changed | departed, sound: `TRUNCATE … CASCADE` already empties it through the FK, and adding it breaks the 21 existing tests at red |
| BDD journey, `alan` fixture, page methods | `settings.feature`, steps, `chat_page.py`, `conftest.py` | present |
| `time`, `ClockProvider`, SettingsPage rows, `App`, `session`, `chat` | all present | present; "a directory fetch that lands before the save…" merged into the save test (its first half), sound |
| Expectation: positive half for every guard | own-capitals + Grace 409; unknown key with valid key not applied; clock-revert with positive; return path kept after success | present |

## Findings

No critical or major findings.

### 1. The 24-hour midnight test cannot tell `hour12: false` from `hourCycle` — minor
**Where:** `lib/time.test.ts`, midnight test, and its comment · **Checked:** the report's own run (green with `hour12: false` on this Node/ICU); not rerun by me.
The comment says `hour12: false` renders `24:05` "in some locales", but here it doesn't, so the test only pins against `h24`. A code-writer using `hour12` passes everything. Harmless to users, but the comment overclaims. The code-writer should still use `hourCycle` as decision 33 says.

### 2. `lastChannelId` is cleared by the shell's unmount, and the test only reaches it that way — minor
**Where:** `SettingsPage.test.tsx › goes back to the last channel, or home after a direct load` · **Checked:** sketch, red until `resetLastChannel()` was added to `ChatLayout`'s cleanup.
The second half expects `/` after an earlier render in the same module-level store. It passes only if `resetLastChannel()` runs in the cleanup that fires when the shell unmounts, as the plan puts it (`ChatLayout.tsx:51-57`, deps `[workspaceId]`). No test names the workspace-change reset on its own; the same effect covers both. A code-writer who resets only inside a changed-workspace branch would fail the test and be confused.

### 3. Settings revisit does not distinguish the server's name from a cached one — minor
**Where:** `drops an unsaved edit on leaving…` · **Checked:** read.
After leaving, the field is expected to hold `Ada Lovelace`, which is also the session's name and the cached one. `shows the server's name…` covers a direct load, where nothing is cached. A build that sets `staleTime` on `useProfile` and so reuses a cached name on revisit would pass both. Req 8 says "on every visit". Decision 35 (`refetchOnMount: 'always'`) is the code-writer's to follow.

## Left for later stages

- **Code-writer:** `test_a_deleted_accounts_name_is_skipped_at_sign_in` is an outcome test only: the retry loop produces `alan 2` even if the taken-keys read skipped deleted rows. Read deleted rows in `_taken_keys` anyway (decision 19, waiver per Global constraints). The test's docstring is true about the outcome, not the mechanism.
- **Code-writer:** decision 29's reset on a workspace change has no test of its own (the report says so). Add `resetLastChannel()` to the existing cleanup effect.
- **Code-writer, from plan-reviewer-2:** two failed clock saves in a row can restore a value the server never stored. Optional; not tested.
- **Code-writer:** in `a second clock choice waits…` the 50 ms real pause is the anchor for the negative count; keep `scope` (the unscoped sketch fails there).
- Assumed decisions 12, 13, 15, 17/19/22, 25, 28, 29, 30, 34, 37 still need the human's read at the end, as plan-reviewer-2 said.

## Checked and sound

- Red for the right reason: every Auth failure is an assertion on the new behaviour, a missing `rename_user`, or a missing revision. No fixture, typo or import error hides a body. The two load failures are the two files whose every test needs the missing module.
- The 409 test pins `status`, `detail`, `errors.displayName`, and that neither Grace's id, email nor the word "workspace" appears; it also shows a free name still succeeds.
- Validation tests put the refused character inside the name (trailing U+2028 would be stripped), assert the fixture's category, and cover Cs and default-ignorables outside Cf.
- Both sides of 100 are tested, counted after NFC (`a`×99 + `e` + U+0301), and in the SPA by code points (100 and 101 emoji).
- `test_changing_only_your_own_capitals_is_allowed` has its positive half; `test_a_legacy_name_can_be_saved_unchanged` has its 400 half.
- Race tests wait on `pg_stat_activity` with a 5 s bound, never a sleep; a SELECT-then-UPDATE build never blocks and fails the poll.
- `test_a_deleted_account_is_404` asserts `detail`; `test_preferences_need_a_token` is 401 and red today.
- The migration test orders by `created_at` against an id that sorts the other way, includes a deleted row, and normalising-only duplicates.
- Existing assertions: only stubs added to `App.test.tsx`, `ChatLayout*.test.tsx`, `CreateChannelDialog.test.tsx`; `test_schema`'s email test gains distinct names and a constraint-name assertion, as the plan says. Nothing loosened.
- No production code, config or docs changed: `git status` is clean apart from this review, and the report's file list matches the tree.
- The directory race tests hold the post-save refetch, and each wrong build in *What ran* fails exactly the tests meant to catch it.
