# Red tests — gh-3, round 1

Display names, unique names and a preferences page, written outside-in: one BDD journey, then pytest and Vitest below it. 138 new tests across 17 files: 48 unit, 34 Auth integration, 55 Vitest, 1 BDD scenario. At red every new test fails (36 Vitest tests run and fail; 19 more sit in two files that fail to load because every test in them needs the missing module; the two Python unit files fail to collect for the same reason). The 21 Auth integration tests and 503 Vitest tests that were already there still pass. Every new test goes green against a throwaway build, and each has a named wrong build that turns it red (*Sketch runs*), with one exception: the plan's `hour12` build, which this runtime cannot tell from `hourCycle`.

## Baseline

| Files | Before | After (at red) |
|---|---|---|
| `auth/tests/unit` (all) | 59 passed | 59 passed + `test_names.py`, `test_preferences.py` fail to collect |
| `test_users.py` / `test_schema.py` / `test_r1_unreachable.py` | 12 / 4 / 5 passed (21) | the same 21 pass; 12 + 1 + 1 new fail |
| Vitest, whole suite | 503 passed | 503 passed, 36 failed, 2 files fail to load |

Auth integration for the other files was not run before: they are untouched, and the whole directory passes (157) against the sketch.

## Tests

Layer: U = pytest unit, I = pytest integration, V = Vitest, B = BDD. Observed red is the first line of the failure. "Match" is yes unless said.

| File · test | Layer | Plan task | Proves | Observed red |
|---|---|---|---|---|
| `test_names.py` (all 36 cases: refused examples, accepted examples, each category alone, default-ignorables outside Cf, length, `stored_form`, key, `first_free`, limit, `provision_name`, four `dedupe`) | U | 1 | the name rules | `ModuleNotFoundError: No module named 'auth.names'` (collection) |
| `test_preferences.py` (7 groups, 12 cases) | U | 1 | `parse_patch` | `ModuleNotFoundError: No module named 'auth.preferences'` |
| `test_users.py::test_a_name_is_stored_trimmed_and_in_nfc` | I | 2 | trim + NFC on write | `AssertionError: assert '  José  ' == 'José'` |
| `…::test_an_invalid_name_is_refused[5 inputs]` | I | 2 | 400 + `errors.displayName`, name unchanged | `assert 200 == 400` |
| `…::test_saving_the_name_you_have_changes_nothing` | I | 2 | padded same name: 200, no write; real change bumps `version` | `assert ' ada ' == 'ada'` (the response still carries the raw string) |
| `…::test_a_taken_name_is_409_naming_nobody` | I | 2 | 409 body, nobody named, a free name still 200 | `assert 200 == 409` |
| `…::test_names_colliding_only_after_nfc_are_taken` | I | 2 | NFC + case across forms | `assert 200 == 409` |
| `…::test_changing_only_your_own_capitals_is_allowed` | I | 2 | own capitals OK, and the name is still held | `assert 200 == 409` (Grace takes `ada`) |
| `…::test_a_legacy_name_can_be_saved_unchanged` | I | 2 | decision 15 order | `assert (2, …) == (0, …)`: the version moved |
| `…::test_a_deleted_accounts_name_stays_taken` | I | 2 | D46 | `assert 200 == 409` |
| `test_display_names.py::test_two_renames_to_one_name_one_wins` | I | 2 | the index is the control | `AttributeError: module 'auth.identities' has no attribute 'rename_user'` |
| `…::test_a_rename_racing_a_first_sign_in` | I | 2 | rename vs sign-in | same `AttributeError` |
| `…::test_two_first_sign_ins_with_one_name` | I | 2 | "Sam" and "Sam 2" | `Failed: B never blocked on the name index` (5 s) |
| `…::test_a_taken_idp_name_gets_the_first_free_suffix` | I | 2 | suffix through the real callback; workspace named from it | `assert 'alan' == 'alan 2'` |
| `…::test_a_deleted_accounts_name_is_skipped_at_sign_in` | I | 2 | deleted rows count | `assert 'alan' == 'alan 2'` |
| `test_migration_0002.py` (4 tests: trim/NFC, duplicates by `created_at`, normalising-only duplicates, the index and NOT NULL) | I | 2 | the data migration | `alembic.util.exc.CommandError: Can't locate revision identified by '0002'` |
| `test_preferences.py` (11 tests: no row, `{}`, store, null, last write, unknown key, bad value, deleted 404 with `detail`, across workspaces, no token, merge race) | I | 2 | the routes and the merge | `assert 404 == 200` etc.; the deleted one `KeyError: 'detail'`; the merge one `ModuleNotFoundError: No module named 'auth.preferences'` (that test only) |
| `test_r1_unreachable.py::test_a_rename_and_a_preference_fail_open` | I | 2 | both PATCHes fail open | `assert 404 == 200` (the preferences half) |
| `test_schema.py::test_a_display_name_differing_only_in_case_is_refused` | I | 2 | the index | `Failed: DID NOT RAISE IntegrityError` |
| `test_schema.py::test_email_uniqueness_ignores_case` (modified) | I | 2 | now asserts `users_email_key` | passes before and after, by design |
| `lib/time.test.ts` (9) | V | 4 | the three clock choices | `Failed to resolve import "./time"` |
| `ClockProvider.test.tsx` (10: three places × 24h / 12h / automatic, plus the cache change) | V | 4 | clock reaches `MessageItem`, `ThreadSummary`, `SearchResult`; no refetch | `Failed to resolve import "./ClockProvider"` |
| `SettingsPage.test.tsx` (16) | V | 4 | page, Save gating, the writes, the races, the clock | `Unable to find role="textbox" and name "Display name"` for most (`/settings` is *No such page*); the directory tests stop at `expected [] to have a length of 1 but got +0` (no sidebar on that page yet); the clock ones at `Unable to find role="radio" and name "24-hour"` |
| `App.test.tsx` (2 new) | V | 4 | direct load; sign-in returns to `/settings` | `Unable to find role="heading" and name "Settings"`; `Unable to find role="button" and name "Sign in"` (differs from the plan, see *Departures*) |
| `session.test.ts` (3 + 3 + 10 new) | V | 4 | `updateProfile`, the `adopt` race, the return path | `TypeError: session.updateProfile is not a function` / `session.takeReturnPath is not a function` |
| `chat.test.ts` (2 new) | V | 4 | `lastChannelId` | `expected undefined to be 'channel-1'`; `expected undefined to be null` |
| `settings.feature` | B | 3 | Alan's rename seen by Grace after a reload | cannot run here; see *BDD* |

## Types

`npm --prefix src/frontend run typecheck` reports only what the missing code provides:
- `lib/auth/api` has no `Clock`, `Preferences`, `PreferencesPatch` (in `test/api.ts`, `ClockProvider.test.tsx`, `SettingsPage.test.tsx`); three `TS7006` on `(body)` in `SettingsPage.test.tsx` follow from that and should vanish with the type. The same shape on `auth.patchMe((body) => …)` already types, because that body is declared.
- No `./time`, no `./ClockProvider`.
- `session.updateProfile`, `session.takeReturnPath`, a second argument to `session.signIn`, `lastChannelId` and `resetLastChannel` on the chat store.

I could not typecheck against the sketch (the helper only runs Vitest), so "the types resolve" is checked by reading, not by `tsc`.

## Sketch runs

Correct build first: the whole SPA suite is green against it (54 files, 558 tests = 503 + 55 new), and all of Auth's integration directory (157) plus the 48 unit tests. Then a wrong build for each test, named and run:

| Test(s) | Wrong build | Result |
|---|---|---|
| `test_key_ignores_case_and_form` | key from `lower()` | `Strauß` ≠ `strauss`: red |
| refused examples, `default_ignorables_outside_cf` | category check only, no default-ignorable table | 6 red |
| `test_length_after_trim_and_nfc` | length counted before NFC | red |
| `test_dedupe_never_takes_a_kept_name` and two more | kept names not reserved | 3 red |
| `test_first_free_keeps_the_name_inside_the_limit` | suffix not cut to fit | red |
| `test_a_bad_value_is_refused[list]` | `value in allowed` without the `str` check | `TypeError`: red |
| race tests, `test_schema`, `test_migration…::index`, four `test_users` | unique index made non-unique | 9 red |
| `test_a_legacy_name_can_be_saved_unchanged` | validate before the no-op check | red |
| `test_changing_only_your_own_capitals_is_allowed` | a case-only rename treated as "no change" | red |
| `test_two_writers_on_different_keys_both_land` | upsert replaces `prefs` instead of merging | red |
| `test_duplicates_are_renamed_except_the_oldest` | migration orders by `id` | red |
| `test_a_deleted_accounts_name_is_skipped_at_sign_in` | none beyond the outcome | The sign-in retry loop papers over a taken-keys read that skips deleted rows, so only a build that lets a deleted account's name be reused (an index excluding deleted rows) fails it. I kept it as an outcome test |
| `test_no_row_reads…`, `test_an_empty_patch…` | none run | the assertions are the guard (row count 0) |
| SettingsPage "shows the server's name" | form seeded from the session | red |
| save / directory / unmount / in-flight tests | rename writes only invalidate (no `setQueriesData`) | 4 red |
| "first directory fetch still out" | writes without the leading `cancelQueries` | that test alone red. The cached-case test passes without it, as it should: `invalidateQueries` cancels a fetch that has data |
| "lands after leaving" | writes in the per-call `mutate` callback, not the hook's | that test alone red |
| "a second clock choice waits" | no mutation `scope` | red |
| "late failure does not undo" | `onError` restores unconditionally | red |
| "a second clock choice waits" | `onSuccess` writes the answer unconditionally | red |
| "workspace switch changes nothing" | page remounted per access token | red |
| "Save is off…" | length by UTF-16 units; `>= 100` | red, red |
| "back to the last channel", `chat.test` | `lastChannelId` cleared on leaving | both red |
| `App` "back there after signing in" | `state.from` not the visited path | red |
| `session`: both `adopt` race tests | `updateProfile` does not count the edit | red; the "adopts what a renewal fetches" test stays green, as the guard's positive should |
| `session`: "forgets it when the identity provider refused" | `returnPath` not cleared on that `return false` | red |
| `time` midnight | `hourCycle: 'h24'` | `24:05`: red |
| `time` midnight | **`hour12: false`** (the plan's wrong build) | **green**. On Node 24 / ICU, `hour12: false` renders `00:05` in `en-US`. The plan's premise ("some ICU locales render 24:05") does not reproduce here, so the test cannot pin `hourCycle` over `hour12`; it pins against `h24` and `h11`-style midnight bugs only |
| `ClockProvider` search result, 24h | clock dropped for `SearchResult` | red. The 12-hour cases cannot catch it: automatic *is* 12-hour in `en-US`, so only the 24h cases and the cache-change test pin the plumbing |
| "a changed clock re-renders… fetches nothing" | provider invalidates its query on change | red |

## BDD

`uv run pytest tests/bdd --collect-only -q` collects `test_grace_sees_the_name_alan_gives_himself_on_his_message` (25 tests); `--generate-missing --feature tests/bdd/features/settings.feature` prints no stub, so every step binds.

Expected red, at the code-writer's first run before the SPA: `Alan changes his display name to "Alan Turing"` stops in `ChatPage.open_settings` waiting for `settings-display-name`, because `current-user` is a `<p>`, not a link. Once the page exists, the last step is where a missing server-side rename would show: Grace's `has_author` waits for the label to read `Alan Turing`.

New page-object methods: `open_settings`, `change_display_name`, `shows_current_user`. New harness: `ALAN`, `alan_context`, `alan`.

## Departures from the plan

- **`TABLES` in `auth/tests/integration/conftest.py` is not changed.** Adding `user_preferences` makes `TRUNCATE` fail for every Auth integration test until migration 0003 exists, breaking the 21 existing tests at red. `RESTART IDENTITY CASCADE` already empties it through its foreign key to `users`, and the preferences tests prove it (the row count starts at zero in each).
- **`Strauß` / `STRASSE` → `Strauß` / `STRAUSS`.** `"Strauß".casefold()` is `strauss`, so the plan's pair would not share a key.
- **Added tests**: `test_an_empty_patch_changes_nothing_and_writes_no_row` (decision 25); `test_first_free_keeps_the_name_inside_the_limit` (third candidate and `with_suffix` at n = 10); `test_dedupe_returns_every_row_trimmed`; `test_a_valid_key_beside_an_invalid_one_is_not_applied`; `test_duplicates_that_only_normalising_reveals_are_renamed` (the issue names this); Save gating for 100 emoji (200 UTF-16 units) and for capitals-only; `no-break space` as a refused example; `12h` midnight; `survives a sign-in that completes` (so clearing on success is wrong); ClockProvider tests parametrised over three places and three states.
- **Merged:** the plan's "a directory fetch that lands before the save is overwritten by it" is the first half of "a save updates the sidebar…" (call 1 settled, save, call 2 held, entry reads `Ada L`), so there is one test.
- **Not tested, though the plan decides it:** decision 29's "`lastChannelId` is cleared on a workspace change" (`ChatLayout`'s cleanup). The plan's Task 4 lists no test for it. It is worth one line in the code-writer's check.
- **App return-path test fails earlier than the plan says.** Without a `/settings` route the guard is never reached (the route is *No such page*), so the first red is `Unable to find role="button" and name "Sign in"`, not "lands on `/`". Once the route exists it fails at the landing assertion. The sketch with `state.from` broken confirms it.
- **`wait_until_blocked` is written twice** (`test_display_names.py`, `test_preferences.py`), since a shared helper would need a `tests` import, which ruff bans (TID251).
- **Characters** are built with `chr()` and named (`ZERO_WIDTH_SPACE`, `BRAILLE_BLANK`), never as literals or `\u` escapes in the file.
- **The `Refusal` helper** (`auth.refuse(status, body)`) in `test/api.ts` lets a scripted PATCH fail on one call; it was not in the plan's list.
- **`test_users.py` imports `User`** to set a legacy name through the ORM (as the plan says). It will go through the `display_name` validator once that exists.

## Picked up from earlier reviews

- *Plan review 2, test-writer:* "`a second clock choice waits…` has a negative count that MSW may not have recorded yet." The count is taken after a 50 ms real pause, with the `12-hour` radio checked first as the positive anchor. The sketch with the `scope` removed fails there.
- *Plan review 2, code pair:* two failed clock saves in a row put back a value the server never stored. Not tested (optional fix); left to the code-writer.
- *Plan review 1 items* are in the tests: the held-directory pattern, the two session races and the return-path clearing.

## For the code-writer

- **Wire shapes asserted:** `PATCH /users/me` body `{displayName}`; `PATCH …/preferences` body `{clock: '24h' | '12h' | null}`; the 409 and 400 bodies carry `errors.displayName[0]`, which the page shows in a `role="alert"` element.
- **Markup the Vitest tests query** is the plan's Task 4 list: heading `Settings`; headings `Profile`, `Preferences`; textbox `Display name`; `Save`; `role="status"` with `Saved`; radios `Automatic`, `12-hour`, `24-hour`; link `Back to chat`; the sidebar name is a **link** named by the display name. The BDD page object uses the `data-testid`s from the plan.
- **The cache keys are literals in the tests:** `['workspace-members', ws]`, `['user-preferences', userId]`. Rename them and ten tests fail.
- **Timing pinned:** the directory refetch starts after the rename commits and not before (`directory.requests` reaches 2 only after "Saved"); `await cancelQueries` comes before `setQueriesData`; both clock PATCHes run through a mutation `scope` (the second request is not sent until the first settles).
- **`ClockProvider` renders nothing different until preferences load** (automatic), and its cache entry is the one a save writes.
- **`signIn(provider, returnTo)`** writes `collabhub.returnPath` in `sessionStorage` (the test reads that key once); `takeReturnPath()` must clear it.
- **Auth:** the store tests import `auth.identities.rename_user` and `NameTakenError`, `auth.preferences.apply_patch` and `read`, and expect `User.display_name_key` to follow `display_name` on assignment (the test sets the legacy name through the ORM). Migrations `0002` and `0003`, in that order; the upgrade test calls `command.upgrade(cfg, "0002")`.
- **The merge race test** relies on the upsert being a single `INSERT … ON CONFLICT` so that B waits on A's row; a read-then-write would fail it in a different way.
- **Python hazard:** `Cs` (`chr(0xD800)`) is passed through `normalise_display_name`; it must not raise anything but `InvalidNameError` (NFC leaves it alone).
