# Plan review — gh-3, round 1: changes_requested

A strong plan: the library claims it leans on check out against the installed source, and most of
my expectations are settled in decision rows. Six major findings remain, each a small fix. There is
a ripple file that would quietly stop an existing test from proving anything, two races or
concurrency tests with no deterministic answer, one wrong expected failure, two requirement clauses
with no test, and one *Paths* row settled silently. Nothing is critical, and nothing needs a human.

## Expectations

Written from the issue, doc 01 §3–§4, doc 06 §3/§5.2/§9, the register (D2, D18, D24, D26,
D28 🔴 today) and the code (`routers/users.py`, `identities.py`, `oidc.py:248-252`,
`federation.py:175-212`, `schemas.py:129-133`, `shared/problems.py`, `session.ts`, `App.tsx`,
`WorkspaceSwitcher.tsx`, `useWorkspaceMembers.ts`, the three formatters, `tests/bdd/conftest.py`,
`test_schema.py`) — before the plan was opened.

**Decisions**
- D1. Validation order: is the 1–100 bound applied *after* trimming? Today pydantic's
  `min_length/max_length` run on the raw string, so `"  " + 100 chars` is refused and `"   "` passes.
  Which characters are "control" and "invisible format" (Unicode Cc / Cf? which zero-widths?) —
  and is an interior run of spaces or a tab kept, refused, or collapsed?
- D2. How is uniqueness enforced — a unique expression index on `lower(trim(display_name))`, a
  stored normalised column, or `citext`? Does `lower()` vs full case folding (ß/SS, Turkish ı) matter,
  as the issue asks the plan to say? Is the stored name trimmed, so `trim` in the index is moot?
- D3. Is the index over every row (deleted accounts included, as Req 2 says) — no `deleted_at` filter?
- D4. How is the 409 produced — catch `IntegrityError` on the unique index (race-safe) or a
  pre-check SELECT (racy unless backed by the index)? Is the 400 and 409 both under `errors.displayName`?
- D5. "Saving the name you already have succeeds and changes nothing" — does it bump `version` and
  `updated_at` (today every PATCH does)? Is a capitals-only change a real change (it must be allowed)?
- D6. Explicit `displayName: null` — the issue says check the code: today it's 400 (`users.py:61-65`). Kept?
- D7. First sign-in: the IdP name may itself be invalid (empty after trim, >100, control chars) —
  is it normalised before suffixing? Does `X 2` stay within 100 characters for a 99/100-char `X`?
  Is "first free" counted on the normalised (lower/trim) form? Unbounded loop or a cap?
- D8. Where does the first-sign-in collision retry happen — a savepoint around the user insert in
  `provision_user`, since the callback commits only at `federation.py:212`, *after* `issue_code`?
- D9. Migration: rename duplicates by `created_at` — tie-break on equal `created_at` (id)? Does it
  trim existing names first (and rename names that are empty/invalid after trim)? Can a generated
  `X 2` collide with an existing `X 2` (both the renamed row and an existing distinct row)? Does the
  migration rename workspaces too (Req 3 names workspaces only for *new* accounts)? Downgrade —
  index dropped, renames not undone (one-way)?
- D10. Preferences: is `version` bumped, and is the merge atomic (`prefs || patch` / `- key` in one
  UPDATE, or row lock) so two tabs on different keys don't lose each other's write? Upsert on first
  PATCH with `ON CONFLICT`? What does PATCH return — the full merged map? Is `{}` PATCH a no-op?
  Does a PATCH that only removes keys from a user with no row create one? Is an empty / non-object
  body a 400?
- D11. Preferences 404 for a deleted account — GET *and* PATCH, checked before any write.
- D12. Where the clock preference lives in the SPA — a TanStack query (`['preferences']`, not
  workspace-keyed since it's per user), optimistic `setQueryData` with rollback on error; where is the
  error shown? How the clock reaches three formatters (hook/context vs prop)? `hour12` vs
  `hourCycle: 'h23'/'h12'`, and how `SearchResult`'s `timeStyle` combines with it.
- D13. `/settings` inside `Protected`/`ChatLayout` (socket stays up, sidebar visible) or a bare page?
  "Back to chat link to the last channel" — where does "last channel" come from (the chat store's
  `activeChannelId`?), and what on a direct load where there is none?
- D14. Signed-out `/settings`: `Protected` navigates to `/sign-in` and `Callback` to `/` — so
  "sign-in, then back on /settings" isn't true today. Does the plan build a return-to, or say it
  doesn't (the issue asks it to say so either way)?
- D15. How the SPA writes the session profile — `session.ts` has no setter; a new exported
  function? And how the directory cache is updated — `setQueryData` on which workspace's key (the
  active one only, or every `['workspace-members', *]`)?
- D16. "Reads the profile and preferences from the server on every visit" — a fresh `GET /users/me`
  per mount (query with `staleTime: 0` / `refetchOnMount: 'always'`)? Does that fetched profile also
  update the session's `current-user`?
- D17. Save button: "disabled while unchanged" — compared trimmed? case-sensitively (capitals-only
  must enable it)? "Saved" — when does it clear (on next edit)?

**Conflicts**
- C1. Req 2 / Decided 4 (global 409) against CLAUDE.md's "A resource the caller may not see is a
  404" — settled by D46 and the CLAUDE.md record item; does the plan carry the record?
- C2. Req 6 / Decided 7 — D28 is 🔴 in the register today; the issue decides it. Does the plan record
  it in the slice (register, ADR, docs, CLAUDE.md) rather than building on a 🔴?
- C3. Req 5 ("at once" in the renamer's tab) against the token's `name` claim and a renewal's
  `adopt()` re-reading `/users/me`: harmless, or a race (below)?
- C4. Paths table "Leaving /settings mid-save — a successful response still updates…" against
  TanStack `useMutation` callbacks passed to `mutate()` (not fired after unmount in v5).
- C5. Req 3 "never refuses over a name" against the existing 400-bounds — an IdP name >100 chars.

**Tests**
- T1. Integration: trim (`"  Ada  "` stored as `"Ada"`), 101 after trim refused but 100 + padding
  accepted; `"   "`, a control char, a ZWSP/ZWJ/BOM each refused with `errors.displayName`; and the
  row unchanged after each refusal (proves "nothing changes").
- T2. 409 on exact, on different case, on padded; body names nobody (no other user's id/name/
  workspace); own-capitals allowed; deleted account's name still taken (with the positive: a name
  freed? n/a — but a live user's own name not refused).
- T3. Concurrent rename: two sessions/tasks at once — exactly one 200, one 409 — at integration, with
  real concurrency (gather + a barrier), not two sequential calls.
- T4. First sign-in suffixing: `X` taken → `X 2`; `X` and `X 2` taken → `X 3`; workspace named
  `X 2's Workspace`; existing user's name not overwritten on re-sign-in; two first sign-ins at once
  both succeed with distinct names; a case-only collision suffixed.
- T5. Migration: run from 0001 with duplicates (incl. case/whitespace variants, a deleted
  duplicate, equal `created_at`), upgrade, assert oldest kept, others suffixed, index exists.
- T6. Preferences: `{}` with no row and no row created; merge keeps other keys; `null` removes;
  unknown key 400 with `errors.<key>` and nothing written; bad value 400; deleted → 404 on GET and
  PATCH; two concurrent PATCHes on different keys both survive.
- T7. Vitest: form disabled unchanged/invalid (whitespace, >100 after trim), enabled for
  capitals-only; 400 and 409 on the field; "Saved"; session profile *and* directory cache updated —
  including when unmounted mid-save; clock in all three formatters (12h, 24h, absent each, with a
  time where 12h and 24h differ — after noon); revert on failed save with error shown; no refetch of
  messages on change.
- T8. BDD: Alan renames; Grace *reloads* and sees it on Alan's message — server-proved.

**Risks**
- R1. Existing tests that create users with one fixed name: `test_schema.py:21-22` `a_user()` always
  "Ada Lovelace" — `test_email_uniqueness_ignores_case` would then raise on the *name* index and pass
  without proving citext. Any other fixture minting several users with one name.
- R2. The callback commits after `issue_code` (`federation.py:200-212`): a unique violation at that
  commit leaves a code issued for an account never written, and a 500 instead of a sign-in.
- R3. A renewal's `adopt()` in flight (fired before the rename commits) landing *after* the rename's
  success — overwrites the session profile with the old name. Same for a workspace switch.
- R4. Directory cache updated with `setQueryData` while a directory refetch is in flight (started
  before the rename committed) — the stale fetch lands and reverts the renamer's own messages.
- R5. Optimistic clock update while a preferences GET is in flight (the page's on-visit read) — the
  GET lands with the old value. And two quick choices: the first's failure rolls back over the second.
- R6. `hour12: false` produces `24:05` at midnight in some ICU/locale combinations; tests must pin
  a time that tells the readings apart and run under the locale Vitest has.
- R7. Ripple: `UpdateUserRequest`'s raw-string bounds; `Profile` type; `test/api.ts` MSW stubs for
  the new routes; doc/register/ADR/CLAUDE.md records; truncation list in Auth's integration conftest
  (`TABLES`) needs `user_preferences`; BDD `alan` fixture; Dex name for Alan; `.env.example` if any.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 rename yourself: trimmed, 1–100 after trim, no control/invisible, 400 `errors.displayName`, nothing changes, same name no-op | Dec 17, 18, 20; Task 1 unit; Task 2 `test_display_names` 400/length/no-op; Task 6 drops `Field` bounds | covered |
| Req 2 unique: trimmed, case-insensitive, all workspaces, deleted included; 409 text naming nobody; own capitals allowed | Dec 13–15; Task 2 409, capitals, accented, deleted, concurrent | covered |
| Req 3 first sign-in `X 2, X 3…`; workspace from result; never refuses, never overwrites | Dec 16, 19; `test_first_sign_in_names` incl. race, workspace and Dex path | covered |
| Req 4 migration: all but oldest renamed by Req 3's rule; one-way | Dec 21–23; `test_name_migration` | covered |
| Req 5 own tab at once (sidebar and own authors); others on next refetch; no broadcast | Dec 29–30; `useProfile`/`session` tests; BDD | covered, except the second-tab row: **F6** |
| Req 6 preferences: GET `{}` with no row created; PATCH merge, `null`, unknown/bad 400 nothing changes; deleted 404 | Dec 24; Task 1 unit; `test_preferences_api` | covered; the two-tab merge test doesn't hold the race: **F3** |
| Req 7 clock: 12h/24h/absent in all three formatters; saves at once; failed save reverts **and shows the error** | Dec 31–33; `time.test`, three formatter tests, `usePreferences` | the revert is covered; the error isn't shown in any page test: **F5** |
| Req 8 page: Profile (prefill, Save disabled, "Saved"), Preferences radios, via `current-user`, Back to chat, **server read every visit**, direct load/reload | Dec 25–28; `SettingsPage`, `App`, `ChatLayout` tests | profile read covered; the preferences read isn't: **F5** |
| *Where the rules meet* 1–7 | self-review mapping, verified | covered; two tabs: **F3** |
| *Paths* rows | self-review mapping | second tab: **F6**; rest covered |
| *Decided already* 1–11 | Decisions 1–12, global constraints | covered |
| *What this assumes*: index on lower+trim | Dec 13: `lower(display_name)` with every writer trimming, reason given | settled |
| …`lower()` vs full folding | Dec 14, **assumed** | settled |
| …only `provision_user` creates names | Correction 3; verified by grep (`identities.py:101` is the only non-test `User(`) | settled |
| …explicit null is 400 | Correction 3; verified `users.py:61-65` | settled |
| …sign-in returns to route | Correction 1, Dec 25; verified `App.tsx:26,63,83` | settled |
| …`hour12`/`hourCycle` across locales | Dec 33, `time.test` in three locales | settled |
| Tests section (pytest, Vitest, one BDD journey, `alan` fixture) | Tasks 1–4 | covered |
| Record in this slice | Task 8 — register D28/D46, two ADRs, doc 01, doc 06, both CLAUDE.md items | covered |
| Not in this issue | *Not in this plan* | covered |
| C1 D46 against 404-not-403 | Dec 3, Task 8 CLAUDE.md bullet | settled |
| C2 D28 🔴 decided by the issue | Dec 6, 35; Task 8 | settled |
| C3 token `name` claim | left, as the issue says | settled |
| C4 unmount mid-save | Dec 29, hook-level `onSuccess` (verified `mutation.js:123`) | settled |
| C5 IdP name >100 | Dec 19 `provisional_name` | settled |
| D1–D17 | Dec 13–34, Task 1/3 interfaces | settled; D14 Dec 25, D13 Dec 26–27 |
| T1–T8 | Tasks 1–4 | covered, except **F3** and **F5** |
| R1 `test_schema.a_user` | not in the file map | **missing — F1** |
| R2 commit after `issue_code` | Dec 16: savepoint per candidate, so the final commit can't hit the index | settled |
| R3 renewal vs rename | Dec 30 epoch counter, both orders tested | settled |
| R4 directory fetch in flight | Dec 29–30 invalidate (`cancelRefetch` default true); tracker's `load` doesn't dedupe (`directoryRefresh.ts:97-125`) | settled |
| R5 preferences fetch in flight vs optimistic choice | not addressed (Dec 32 covers bursts only) | **missing — F2** |
| R6 `h24` | Dec 33 `hourCycle: 'h23'` | settled |
| R7 ripple | file map: conftest `TABLES`, `test/api.ts` default handler, records | covered except F1 |

## Findings

### 1. `test_schema.py`'s fixed display name: an existing test would stop proving citext — major
**Where:** File map; *Known ripple* · **Checked:** `src/services/auth/tests/integration/test_schema.py:21-48`,
grep for `User(` across every `tests/` directory (this is the only one).
`a_user()` gives every user `display_name="Ada Lovelace"`. After Task 5's index,
`test_email_uniqueness_ignores_case` still raises `IntegrityError`, but now from
`uq_users_display_name`, so it passes whether or not `citext` works. Nothing else in the suite
proves email case-insensitivity at the schema. Put `test_schema.py` in the file map: `a_user` takes a
distinct name per user, or that test asserts which constraint fired. Say which task changes it.
Because the index lands in GREEN, the change belongs to the code-writer's Task 5, like `TABLES`.

### 2. A preferences fetch in flight overwrites an optimistic clock choice — major
**Where:** Decisions 31–32; Task 3 `usePreferences.test.tsx` · **Checked:** `main.tsx:15-28` (no
`staleTime`, so it is 0 and `ChatLayout`'s `usePreferences` refetches on every window focus and
mount); `SettingsPage` refetches on mount.
Dec 32 answers two choices in a row. It doesn't answer a `GET …/preferences` already in flight when
`onMutate` writes `['preferences']`. Here is one order: the window regains focus, a refetch starts,
Grace clicks 24-hour, and the GET lands with `12h`. The screen flips back while the PATCH is
pending. If the GET's response arrives after the PATCH's, the screen stays wrong until the next
fetch. The radios are disabled until Settings' own fetch lands, which narrows the window but doesn't
close it. A focus refetch can still start while the radios are enabled. Settle it in the plan, for
example with `cancelQueries(['preferences'])` in `onMutate`, and add a test that holds a GET with
the old value across a choice. The same pair exists for `['profile','me']`'s refetch against the
rename's `setQueryData`. That one is lower stakes, but it needs an answer, even if the answer is
"harmless because…".

### 3. `test_merges_of_different_keys_both_land` doesn't force the two writes to overlap — major
**Where:** Task 2, `test_preferences_api.py` · **Checked:** the test as specified, against the other
race tests in the same task.
"`preferences.merge` from two sessions at once" under `gather` doesn't make the writes interleave. A
read-modify-write `merge` passes whenever the event loop happens to run one write to commit before
the other reads. Then the *Two tabs* rule (*Where the rules meet* 7) is red at the gate but not
pinned at green. Do what `test_two_first_sign_ins_with_one_name` does: session A merges `{"a": "1"}`
and holds its transaction open, session B's merge must block (`waiting_on_a_lock` is `True`), then
A commits, B finishes, and both keys are stored. A read-modify-write build then loses `a`, or hits
a primary-key violation.

### 4. `test_preferences_api.py`: the merge test's stated red would take down the whole file — major
**Where:** Task 2, `test_merges_of_different_keys_both_land` · **Checked:** the expected-red column.
`auth/preferences.py` doesn't exist.
That test's red is `ModuleNotFoundError: … 'auth.preferences'`, which a module-level import gives
at collection, for every test in the file. The other eight tests' stated reds (`404`,
`KeyError: 'detail'`, `assert 404 == 401`) would never run, and the gate would see one load error
in their place (shared context, *Read the failure*). Say that the import is deferred into that one
test (or move the test to a file of its own), so each test fails for the reason the plan gives.

### 5. Two Req 7/8 clauses have no test at the page — major
**Where:** Task 3, `SettingsPage.test.tsx` · **Checked:** the test table against Req 7 and Req 8.
- Req 7: "a failed save puts the previous choice back **and shows the error**". `usePreferences`
  proves the cache reverts and an error is *exposed*. No test shows the radio returning and the
  `role="alert"` text the markup section promises.
- Req 8: "reads the profile **and preferences** from the server on every visit". The profile half is
  pinned: "prefills the name the server has, not the session's" seeds a stale cache. "The clock
  shows what the server holds" seeds nothing, so a build that reads `['preferences']` from
  `ChatLayout`'s cache without refetching passes it.

Add both as `SettingsPage` tests. The second seeds `['preferences']` with a stale value, and the
server answers another.

### 6. A second tab's sidebar name: the *Paths* row is settled silently — major
**Where:** Self-review, *Paths* "second tab"; Decisions 29–30 · **Checked:** `session.ts:76-94`
(`profile` is re-read only in `adopt()`), `WorkspaceSwitcher.tsx:26`.
The issue says a second tab of the renamer behaves "like anyone else: the new name … on its next
refetch". In that tab, a directory refetch renames the user's own messages, but `current-user` reads
`session.profile`. That changes only at the next renewal (up to about 14 minutes) or on a reload.
For that window the tab's sidebar and its own message authors disagree, which is what *Where the
rules meet* row 3 says must never happen. The plan maps the row to the directory tests and says
nothing about the sidebar. Add a decision row, **assumed** if you like. One option is to accept the
gap until renewal or reload. The other is to name the sidebar from the directory. Either way, the
human should see it.

### 7. The scenario vocabulary's ruling 6 also needs the exception — minor
**Where:** Correction 2, Task 8 · **Checked:** `docs/plans/ch06/gherkin/00-scenario-vocabulary.md:31-32,36,52`.
Lines 31–32 forbid "a session-scoped fixture that signs in a third", and `alan_context` is one.
Task 8 amends §1. Amend the ruling beside it too.

### 8. The migration tests can't call `service_database` from inside an async test — minor
**Where:** Task 2, `test_name_migration.py` · **Checked:** `testkit/databases.py:36-49` uses `asyncio.run`.
"Each test makes its own database" with `service_database(…)` raises `asyncio.run() cannot be called
from a running event loop` if it runs in the async test body. It has to run from a sync,
function-scoped fixture, or the test has to `await` `_create` and `upgrade` itself. Say which.

### 9. `test_two_first_sign_ins_with_one_name` needs `demo_workspace_name=None` — minor
**Where:** Task 2 · **Checked:** `identities.py:71-83`, `ensure_demo_workspace` takes
`pg_advisory_xact_lock`.
With a demo workspace name, the second provision blocks on the advisory lock even at red, so
`waiting_on_a_lock` is `True` for the wrong reason. The names half still fails, so red holds, but the
blocking half is vacuous. Pin `None` in the test.

## Left for later stages
- F7–F9 if not taken up, for the test pair.
- Dec 17, **assumed**: `Cf` includes U+200D ZWJ, so an emoji ZWJ sequence (👩‍💻) in a name is
  refused. Defensible, but the human should see it among the assumptions.
- `ChatLayout`'s `usePreferences` with the default `staleTime` 0 adds an Auth request on every
  window focus. That is harmless, but a `staleTime` like the directory's would be cheaper, and F2's
  answer may choose it.
- The exemplar's sweep includes sibling branches in flight. The plan doesn't record checking them,
  so the code-writer should run `git branch --no-merged main` before Task 9.

## Checked and sound
- Header: base `0ac4c21` is `main` (`git worktree list`, `git log`). The baseline `3daf13a` is the
  revision `docs/test-report.md` names, and Auth unit is 59 there.
- Library claims verified in the primary checkout's installed source:
  `sqlalchemy/dialects/postgresql/asyncpg.py:781-797` (`raise translated_error from error`),
  `@tanstack/query-core` `mutation.js:94-128` (hook-level `onSuccess`, `onMutate` before
  `retryer.start()`), and `mutationCache.js:60-71` (`canRun` serialises a scope).
- `ChannelView.tsx:37-38` clears `activeChannelId` on unmount (Dec 27). The `session.test.ts:312-326`
  `location` stub pattern exists.
- Ingress `/api/v1/users` (`ingress.yaml:50`), nginx `try_files` fallback, and CORS `PATCH`
  (`shared/cors.py:43`): no chart, env or nginx change needed.
- Expected reds: `storage.ts` exists, so `returnPath` is `undefined` and the TypeError is right. A
  404 with no `detail` for a missing route matches `problems.py:197-210`, and `extra="forbid"` and
  `Literal` errors land under `errors.theme` and `errors.clock` (`problems.py:177-195`). The literal
  query keys keep `MessageItem.test.tsx` loading at red. Every component gaining `useClock` is
  rendered through `renderWithProviders`.
- Migration rule walk-through: the `Sam, sam, " SAM ", Sam 2, Bob` example gives the stated result
  under Dec 22.
- Workflow rules: 582 lines, every RED task (1–4) before GREEN behind the test-reviewer gate,
  *Found while building* empty, no committing task, no 🔴 built on (D18, D38 and D16 named), Task 8
  records everything the issue lists, and Task 9 names lint, unit, integration and e2e.
- Every interface has a named test, and the BDD journey's last `Then` is Grace after a reload.
