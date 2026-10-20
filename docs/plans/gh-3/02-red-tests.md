# Red tests — gh-3, round 1

BDD outside-in as the plan recommends: one journey, with everything under it at the lowest layer. Every new
test fails as planned except **4 integration guards that pass today by design**; the Vitest files that
need a not-yet-existing module fail to load as a whole (every test in each needs the module). The BDD
scenario parses and binds; it cannot run here.

Counts as run: Auth integration **33 failed, 12 passed** (8 old + 4 guards); Auth unit 2 files fail to load, old 59 pass;
Vitest **21 failed, 503 passed**, 4 new files not loading.

## Baseline (before any change)

| File | Before | After |
|---|---|---|
| `auth/tests/integration/test_schema.py` + `test_r1_unreachable.py` | 8 passed | 8 old pass; 3 new fail |
| `fe/lib/auth/session.test.ts` + `fe/App.test.tsx` | 25 passed | 25 old pass; 21 new fail |
| Auth unit (`tests/unit`, old files) | 59 passed | 59 passed |
| Vitest, whole suite | 503 passed | 503 passed (+21 failing, 4 files not loading) |

`fe/test/api.ts` is a helper: every existing Vitest file still passes with its new default handler.

## Tests

Unit (`uv run pytest src/services/auth/tests/unit`) — **both files fail to load**: `ImportError: cannot import name 'names' from 'auth'` / `'preferences'`. Right for the whole file: every test in each uses the module.
`test_names.py` (22 test functions, ~50 cases) covers every Task 1 row plus three I added. `test_preferences.py` covers its five rows plus the constants.

Integration (`uv run pytest` over five files: **33 failed, 12 passed**). Observed first line of each failure:

| File · test | Plan task | Observed red (verbatim, trimmed) | Match |
|---|---|---|---|
| display_names · `a_rename_is_stored_trimmed_and_nfc` | 2 | `assert '  José  ' == 'José'` | yes |
| · `a_refused_name_is_400…` | 2 | `assert 200 == 400` on `'Grace​'` (first case) | yes |
| · `a_taken_name_is_409_and_names_nobody` | 2 | `assert 200 == 409` | yes |
| · `names_differing_only_in_normalisation…` | 2 | `assert 200 == 409` | yes |
| · `changing_only_your_own_capitals…` | 2 | first half 200 passes; `assert 200 == 409` on Grace → `ada` | yes |
| · `saving_the_name_you_have…` | 2 | `assert '  ada  ' == 'ada'` (the padded save is stored raw) | yes, earlier than the plan's version bump |
| · `a_deleted_accounts_name_stays_taken` · `a_name_in_a_workspace_you_cannot_see…` | 2 | `assert 200 == 409` | yes |
| · `two_renames_to_one_name_at_once` | 2 | `assert [200, 200] == [200, 409]` | yes |
| · `first_sign_in_with_a_taken_name…` | 2 | `assert 'ADA' == 'ADA 3'` | yes |
| · `two_first_sign_ins_with_one_name…` | 2 | `['Sam', 'Sam'] == ['Sam', 'Sam 2']` | yes |
| · `sign_in_behind_an_uncommitted_rename…` | 2 | `assert 'X' == 'X 2'` | yes |
| · `rename_behind_an_uncommitted_first_sign_in…` | 2 | `assert 200 == 409` | yes |
| · `idp_name_with_refused_characters…` | 2 | `assert 'Sam​' == 'Sam'` | yes |
| preferences · all except two below | 2 | `assert 404 == 200` (or `== 400`, `== 401`) — no route | yes |
| · `a_deleted_account_gets_404…` | 2 | `KeyError: 'detail'` — the 404 has no `detail` today | yes (the plan's "assertion") |
| · `concurrent_patches_of_different_keys…` | 2 | `ImportError: cannot import name 'preferences' from 'auth'` | yes (imports inside the test, so only it needs the module) |
| name_migration · 4 rename tests | 2 | `assert '  Ada  ' == 'Ada'` / `'Sam' == 'Sam 2'` / `' José ' == 'José'` / `'   ' == 'grace'` | yes |
| · `after_the_migration_every_key…` | 2 | `KeyError: 'display_name_key'` (not the plan's `ProgrammingError`: I read it with `SELECT *`) | differs, same cause |
| schema · `name_key_is_set_from_the_name` | 2 | `AttributeError: 'User' object has no attribute 'display_name_key'` | yes |
| · `database_refuses_a_second_name…` | 2 | `Failed: DID NOT RAISE IntegrityError` | yes |
| r1 · `rename_and_preference_write_fail_open` | 2 | `assert 404 == 200` (the preferences half) | yes |

**Green by design** (pass today; guards the plan asks for, named as such): `test_a_rename_leaves_the_users_workspace_name`,
`test_the_name_claim_changes_at_the_next_refresh`, `test_a_returning_sign_in_never_overwrites_the_name`, and
`test_a_name_of_exactly_100_characters_is_accepted` (mine — the upper bound's inside edge; the old schema already allows it).
Its pair, 101 refused, is inside `test_a_refused_name…` and is red.

Vitest (`npm --prefix src/frontend test`: **21 failed | 503 passed**, 4 files unloaded):

| File | Result | First line |
|---|---|---|
| `lib/time.test.ts` (4 plan tests × 2 functions + 2) | file fails to load | `Failed to resolve import "./time"` |
| `features/settings/clockSites.test.tsx` (4) | load failure | `Failed to resolve import "./usePreferences"` |
| `features/settings/ProfileSection.test.tsx` (9) | load failure | `Failed to resolve import "./useProfile"` |
| `features/settings/PreferencesSection.test.tsx` (10) | load failure | `Failed to resolve import "./PreferencesSection"` |
| `lib/auth/session.test.ts` (+11, all fail) | run | `TypeError: session.updateProfile is not a function` (×5) · `takeReturnTo is not a function` (×5) · `signIn` test: `sessionStorage` null |
| `App.test.tsx` (+10, all fail) | run | `Unable to find role="heading" and name "Settings"` and similar (the route is "No such page."); the callback test: `expected '/' to be '/settings'` |

`ProfileSection`, `PreferencesSection`, `clockSites` and `time` are load failures, so **their assertions have not
run once**. I wrote them against the installed `test/*` helpers and the query-core source named in the plan, but the
first real run is the code-writer's (see *For the code-writer*). The channel-opening stubs in `App.test.tsx`
were checked: `Back to chat` tests get as far as `the engine hums` rendering before they fail on the missing link.

## Types

`npm --prefix src/frontend run typecheck` lists only: `Clock`/`Preferences` missing from `lib/auth/api`;
modules `./time`, `./usePreferences`, `./useProfile`, `./ProfileSection`, `./PreferencesSection`;
`session.updateProfile`, `session.takeReturnTo`, `signIn`'s second argument; and `TS7031` ("`body` implicitly any")
in `PreferencesSection.test.tsx`, which is a knock-on — `Preferences` is unresolved, so the `auth.updatePreferences`
callback parameter has no type until `lib/auth/api.ts` exports it. No error comes from anything else.

## BDD

`uv run pytest tests/bdd --collect-only -q`: 25 collected, including
`test_profile_steps.py::test_alan_renames_himself_and_grace_sees_it_after_reloading`.
`--generate-missing --feature tests/bdd/features`: prints no stub — every step binds.
Expected red at the e2e run: `change_display_name` clicks `current-user` (a `<p>` today), then times out waiting for
`settings-page`. Needed `data-testid`s: `settings-page`, `profile-name-input`, `profile-save`, `profile-saved`; `current-user` must remain.

## Departures from the plan

1. **Invisible characters are named constants (`ZWSP = chr(0x200B)`), not `\u` escapes.** The tool that writes my
   files decodes `\uXXXX` into the literal character, which ruff then refuses (RUF001) and a reader can't see. Same intent (each is named in one place).
2. **Added:** `test_a_name_of_exactly_100_characters_is_accepted`; `test_an_empty_patch_returns_the_stored_map_and_writes_nothing` (integration, Req 6 / decision 30); `test_the_rule_texts_are_the_ones_the_spa_will_show`, `test_braille_blank_stays_allowed`, `test_deduplicate_leaves_clean_unique_names_out` (unit); `a directory fetch answered while the rename is in flight…` (the plan's "and the other order"); `the two settings differ…`/`keeps the date…` in `time.test.ts`; `with no stored clock a message shows the browser's own format` (positive for Automatic); `takeReturnTo` also refuses `javascript:` and a path with no leading `/`.
3. `test_a_refused_name…` also tries `"   "` and 101 characters.
4. **Migration "sync" tests** use `postgres_server` directly, as planned; a DB per test named `auth_mig_<n>`.
5. **Helper changes beyond the plan's list (`fe/test/api.ts`):** `auth.me` now also takes a reply function (the plan names only `updateMe`/`preferences`/`updatePreferences`) so a test can hold the profile GET; a reply may return `failWith(status, problem)` for a per-call failure. `AuthReply`, `ProblemReply`, `failWith` are new exports. The default `GET …/preferences → {}` handler is added as planned and does **not** record, so it never shows in `requests()`.
6. **`App.test.tsx`'s `aReturningUser()` gained `auth.members(...)`** — the sidebar reads the directory; without it every returning-user test logged an unhandled request. Harmless to the six old tests.
7. **The 400 test returns a single message.** `ProblemError.fieldError` returns the first message only, so how two messages are shown is left to the code; the plan's "every rule broken is listed in `errors`" is proven at integration.
8. **Not pinned (reviewer notes):** the radio during a focus refetch mid-save; a failed profile GET (`isFetchedAfterMount` after an error) — untested, as the plan reviewer left it.

## Picked up from earlier reviews

- `\u` escapes for invisible characters (plan-reviewer 1, Left for later) — taken as named constants; see Departure 1.
- Deleted rows in doc 01 §4 — Task 9, not a test.
- Decision 17's momentary refetch value (plan-reviewer 2) — not pinned.
- Decision 36 and a failed profile fetch (plan-reviewer 2) — not tested, for the code-writer to handle; one line for *Found while building*.
- `directoryRefresh.ts`'s `load` ignores the abort signal (plan-reviewer, for the code-reviewer) — relevant to `a directory fetch answered before the rename…`: that test needs the cancel to drop the held answer.

## For the code-writer

- **Two Auth PATCHes and the 409 race:** `test_two_renames_to_one_name_at_once`, and the two uncommitted-holder tests, only pass if the unique index decides and `provision_user` uses a SAVEPOINT per candidate.
- **A deleted account's 404 on both preferences routes** must carry `detail == "This account no longer exists."` on both preferences routes.
- **`names.deduplicate` is called with `StoredName(id, display_name, email, created_at)`** and returns a `dict[UUID, str]` of changed rows only; `candidates()` is an iterator.
- **`preferences.KEYS` is read at request time** (`test_concurrent_patches_of_different_keys` monkeypatches it): don't copy it at import.
- **SPA:** the tests use `getByRole` only. `Display name` textbox, `Save` button, `Saved` text, `Loading…` text on a revisit, radios `Automatic` / `12-hour` / `24-hour` in a radiogroup `Clock`, link `Back to chat`, headings `Settings` / `Profile` / `Preferences`, and the sidebar user as a **link** named by the display name.
- `useClock()` observes `['preferences','me']` — `clockSites.test.tsx` seeds it with `queryClient.setQueryData(preferenceKeys.mine, {clock})` and changes it in place, expecting a re-render with no request.
- `PreferencesSection.test.tsx` expects `refetchOnWindowFocus` to work with the test client's default `staleTime` (0) — don't set a long `staleTime` on `usePreferences`. The focus test leaves and returns (`visibilitychange`), because TanStack hears nothing else.
- `ProfileSection.test.tsx` expects the rename's `onSuccess` to **cancel in-flight directory fetches** and write the new name into `['workspace-members', *]`; its server then answers the *old* name from a held request, so a refetch-only build fails.
- `session.test.ts` expects `adopt()` to capture the profile epoch **before** `api.me()` is sent.
- `signIn(provider, returnTo)` stores under `collabhub.returnTo`; `takeReturnTo()` clears it and returns `/` for anything not starting with a single `/`.
- The journey's `current-user` must also be clickable (a link) and keep its test id.
