# Test review — gh-3, round 1: changes_requested

The red is real and well-aimed: every new test fails today for the reason the report gives (27 Vitest, 2 Auth unit files at load, the Auth integration reds), and a correct frontend sketch turns the whole suite green. Two things block approval: one Auth unit case (`Zl`) that no plan-conformant build can pass, and the "read already in flight" tests, which pass without the `cancelQueries` the plan makes them pin.

## Expectations (written before the tests were opened)

Read first: issue, plan, both plan reviews, `identities.py`, `routers/users.py`.

**Rules (unit).** `auth.names` / `auth.preferences` do not exist → whole files fail with `ModuleNotFoundError`.
- Vacuous: blank test that only checks `""` not `"   "`; length test pinned at 101 only (needs 100-after-trim passes, 101 fails); the Cf/Cc/Zl refusal checked on only one category; a `candidates` test that doesn't check a 100-char base stays ≤100.
- Wrong build: validate before trim; `len` before trim; refuse only `Cc`.
- Preferences: `extra="forbid"` loc `("theme",)`; `null` vs absent told apart by `model_fields_set` (a build treating None as absent would fail `{"clock": None}` only if tested).

**Rename route (integration).** Today PATCH stores untrimmed, accepts `"   "`, no 409.
- Vacuous: 409 test that doesn't assert unchanged state; "names nobody" tested without a body that would contain the name; case test where Ada's "ADA" is allowed but not the converse; no-op test not checking `version`/`updated_at`; deleted-account test where the deleted row wasn't actually taken; race test that passes serially (both 200 → must be [200,409]; and a serial build with a pre-check would also give [200,409] — so the race needs a lock-wait proof, which the plan requires).
- Wrong builds: pre-check SELECT only (no index) — caught only by the concurrent test; `deleted_at IS NULL` filter in the check — caught by the deleted test; case-sensitive compare; `btrim` on a stale value.

**First sign-in.** Today stores raw name. Vacuous: count-based suffix vs first-free (needs a gap: Sam, Sam 2, Sam 4 → Sam 3); case-insensitive; deleted skipped; workspace named from result; race with two sessions where the second really blocks; "never overwrites" passes at red by design.

**Migration 0002.** `upgrade` import missing → whole file ImportError. Vacuous: renaming by `created_at` order not asserted (needs distinct created_at and an out-of-id-order insertion); reserved names (Sam 2) scenario; deleted oldest keeps; the unique index afterwards (BOB rejected, Bobby accepted).

**Preferences API.** 404 today. Vacuous: GET `{}` with no row-count check; merge atomicity test that doesn't prove B really blocked (lock wait) — a read-modify-write build would pass otherwise; unknown key 400 without checking unchanged; 404 test without detail.

**R1 down.** rename fail-open passes at red by design; prefs red 404.

**SPA (Vitest).** Modules missing → load failures, right only if every test needs them. Vacuous: formatter tests in a 24h default locale; clock tests that import `preferenceKeys` (undefined at red); race tests with no deferred response or no active observer (plan review: needs `usePreferences` rendered beside `useSetClock`); `Saved` negative before the positive; disabled-state boundary 100/101; "no request" assertions checked synchronously; `expect.assertions` on timers.
- Wrong builds: session.updateProfile only (not directory); directory write in `mutate()`-level callback (unmount path); no cancel in onMutate; adopt overwriting profile; returnPath accepting `//evil`; `hour12:false`.

**BDD.** Steps bind; last Then is Grace after reload; `rename_self` handles disabled Save. Check vocabulary phrases verbatim and `@bdd` on Feature line only.

## What ran

- `uv run pytest src/services/auth/tests/unit` → collection error, `ModuleNotFoundError: No module named 'auth.names'` (and `auth.preferences`). With the two new files ignored: 59 passed (baseline intact).
- Auth integration, four files (`test_display_names`, `test_first_sign_in_names`, `test_preferences_api`, `test_r1_unreachable`): every first failure line matches the report's *Observed red* (`'  Ada L  ' == 'Ada L'`, `200 == 409`, `[200, 200]`, "went ahead without waiting", `404`, `KeyError: 'detail'`, `ImportError … 'preferences'` in the merge body). Docker is up. `test_name_migration.py` fails at collection, `ImportError: cannot import name 'upgrade'` — right, all four tests need it. Passing by design: `test_a_rename_fails_open`, `test_sign_in_never_overwrites_a_name`, `test_a_free_name_is_kept_as_it_is`, the avatar guard — all named in the report.
- `npm --prefix src/frontend test` → 27 failed | 505 passed, 11 files failed (4 at load: `time`, `SettingsPage`, `useProfile`, `usePreferences`). Matches the report.
- `npm --prefix src/frontend run typecheck` → 22 errors, all the missing contract (`Clock`/`Preferences`, the four modules, `updateProfile`, `returnPath`, `signIn` arity, five implicit-any callbacks that follow from `Preferences`). Matches *Types*.
- `uv run pytest tests/bdd --collect-only -q` → 25 collected; `--generate-missing` prints no stub: every step binds.
- **Sketch, frontend, correct** (api, storage `returnPath`, `session.updateProfile`/`signIn`, `time.ts`, `usePreferences`, `useProfile`, `SettingsPage`, `App`, `WorkspaceSwitcher`, `ChatLayout`, three formatters): the full Vitest suite, 58 files, **569 passed**. So every new test can go green and the plan's interfaces satisfy them.
- **Sketch, wrong builds** (each run on the files that should catch it):
  - `useSetClock` with no `scope` → 3 fail (order, burst-failure, read-in-flight). Caught.
  - `useSetClock` with no settle `invalidateQueries` → `is not undone by a read that was already in flight` fails. Caught.
  - **`useSetClock` with no `cancelQueries` in `onMutate`** → `usePreferences.test.tsx` 7 passed. **Not caught** (finding 2).
  - **`useUpdateDisplayName` with no `cancelQueries`** → `useProfile.test.tsx` 5 passed. **Not caught** (finding 2).
  - `SettingsPage` radios enabled before the server answered → `reads the clock from the server on every visit` fails. Caught.
  - `SettingsPage` form drawn from the cached profile → `prefills the name the server has` fails. Caught.
  - `time.ts` with `hour12` instead of `hourCycle` → `time.test.ts` 10 passed on this Node (minor, finding 3).
- **Sketch, Auth** (`auth.names`, `auth.preferences` only, pure): 19 passed, **1 failed** — `test_invisible_and_control_characters_are_refused[line separator (Zl)]`, `DID NOT RAISE` (finding 1). The migration and routes were not sketched (containers); I walked the migration's expected list through the plan's algorithm by hand (`Sam`, `sam 3`, `SAM 4`, `Sam 2`, `Bob`) and it matches.
- `.claude/delivery/sketch.sh clean` run; the tree holds only this review.

## Coverage

| Plan test / expectation | As written | Outcome |
|---|---|---|
| Task 1 rules (7) + prefs (4) | `test_display_name_rules.py`, `test_preference_rules.py`, plus unicode-kept, cut-stem, wire-name | present; **`Zl` case unsatisfiable** (1) |
| Task 2 rename (12) | `test_display_names.py`, plus avatar guard | present; reds as planned; both races force a real lock-wait |
| Task 2 first sign-in (8) | `test_first_sign_in_names.py`, plus free-name positive | present |
| Task 2 migration (4) | `test_name_migration.py` | present; created_at order distinct from id order, `Sam 2` reserved, deleted oldest |
| Task 2 preferences (9) + R1 (2) | `test_preferences_api.py`, `test_r1_unreachable.py` | present; merge test proves B blocks, both with and without a row |
| Task 3 formatters, storage, session, App, ChatLayout, SettingsPage | all present, plus extra guards | present |
| Task 3 hooks: own-view, unmount, directory race, profile race | `useProfile.test.tsx` | present; **the in-flight tests don't pin the cancel** (2) |
| Task 3 `usePreferences` (7) | present | same (2) |
| Task 4 journey | feature, steps, page object, `alan` fixtures | present; binds; last `Then` is Grace after reload |
| Expectations: unit `candidates` stays ≤100 | present | ok |
| Expectations: no-op writes nothing / other input held apart | version+`updated_at` check, avatar guard | ok |

## Findings

### 1. The `Zl` refusal case can't pass for a build that follows the plan — critical
**Where:** `test_display_name_rules.py::test_invisible_and_control_characters_are_refused[line separator (Zl)]` (`"Ada" + chr(0x2028)`) · **Checked:** sketched `names.py` to the plan (trim, then refuse `Cc Cf Cs Co Cn Zl Zp`): 19 pass, this one `DID NOT RAISE`.
`str.strip()` removes U+2028 (it is whitespace to Python), so a *trailing* `Zl` is trimmed away before the category check. Decision 17 and Req 1 say "after trimming"; the test puts the character where trimming eats it. The code-writer can only pass it by checking the raw string before trimming (which would also refuse a trailing `\n`/`\t` that Req 1 says is trimmed) or by contorting the rule. The plan's Task 1 row has the same flaw (a literal U+2028 in `"Ada "`), so note it to the code pair; the fix is in the test.
**Fix:** put the line separator inside the name (`"Ad" + LINE_SEP + "a"`), keep it as a refusal case; leave Cf/Cc/Co as they are (neither is whitespace to `strip()`; they passed in the sketch). Consider an extra case showing a *trailing* separator is trimmed and accepted, which pins "after trimming" from the other side.

### 2. The "read already in flight" tests pass without the cancel they are about — major
**Where:** `usePreferences.test.tsx::is not undone by a read that was already in flight`; `useProfile.test.tsx::is not undone by a directory fetch…` and `…profile fetch…` · **Checked:** sketch with `cancelQueries` removed from `onMutate` (preferences, then profile + directory): 7/7 and 5/5 pass.
Decision 36/29 make the cancel the thing that stops the old read overwriting the choice *while the PATCH is pending*. In all three tests the PATCH answers at once and the old read is released afterwards, so the success/settle `invalidate` (which cancels an in-flight fetch itself) repairs the cache before anything is asserted. A build with the cancel missing flickers the old clock/name on screen until the PATCH settles — the exact defect named — and passes. The report's claim that these tests "pin" the cancel is therefore not borne out.
**Fix:** hold the PATCH (a deferred reply, as `applies a choice before the server answers` already does), release the old GET *while the PATCH is held*, and assert the cache still holds the new value before releasing the PATCH. Same shape for the profile and the directory (hold the PATCH, release the old fetch, assert the new name still shows, then release). The existing end-state assertions can stay.

### 3. Smaller points on what the tests can see — minor
- "Nothing was fetched" (`requests()` empty) in `useClock`, `MessageItem`, `ThreadSummary`, `SearchResult` cannot see `GET …/me/preferences`: the default handler in `test/api.ts` is deliberately unrecorded. A `useClock` that fetched would pass. The plan makes `useClock` a cache subscription, so low risk; a comment or recording the default handler under a separate counter would make it honest.
- `Saved` test does `findByRole('status')` then asserts its text: a correct build with a persistent (empty) live region resolves the `findBy` at once and fails the assertion. Prefer `findByText('Saved')` and check its role after.
- `time.test.ts` "never prints 24:05" can't fail on this Node (the `hour12` sketch passed); it is a guard for other ICU builds, fine, but the report shouldn't present it as a pinned mechanism.

## Left for later stages
- Finding 3, all three bullets (minor).
- For the code-writer: the plan's Task 1 `Zl` row has the same literal-U+2028 flaw as the test (finding 1); decision 17 stands as written once the case is interior.
- `at_0001` (sync fixture calling `asyncio.run`) was probed by the writer, not by me; the migration file can't load until `upgrade` exists. Unverified — if it errors at setup, build the database inside the async test (plan-reviewer-2's second option).

## Checked and sound
- Red reasons match the report and plan everywhere except the two noted departures (`App … back to /settings` fails earlier at the missing route; no-op test reads 2→0 not 1→0) — both sound and recorded.
- Races: rename-vs-sign-up and two sign-ups assert a real Postgres lock wait before releasing; the merge test proves B blocks in both the row and no-row cases; `commit` is left to the test.
- 409 body: asserts exact `detail`/`errors`, no `@`, no user id, no "Workspace", name unchanged.
- Suffix: gap case (Sam, Sam 2, Sam 4 → Sam 3), case, deleted, workspace name, cleaning, positive half.
- Migration: oldest by `created_at`, reserved names, deleted oldest, cleaning, index case-insensitive plus a distinct name accepted.
- Preferences: `{}` with no row created, `null` vs absent, unknown/bad key leave state, 404 with `detail`, per-user across a workspace switch, 401.
- Frontend: caught by the sketch — scope/ordering, settle invalidate, server-read-on-every-visit, prefill from server. Boundaries 100/101, trimmed-equal, capitals-only all pinned.
- Existing tests: Vitest 505 passed (503 + 2 by-design), Auth unit 59, R1 file's four old tests pass; no assertion removed or loosened. Shared helpers changed (`test/api.ts`, `render.tsx`, BDD `conftest.py`, `chat_page.py`) are all in the report and the plan's file map; no production code written.
- BDD: phrases bind, `@bdd` on the Feature line only, Alan's Dex account exists in the test Dex config, the last `Then` is Grace's reloaded window, `rename_self` handles the already-renamed rerun.
