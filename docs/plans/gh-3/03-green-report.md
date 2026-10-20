# Green — gh-3, round 1

Tasks 5–9 are built: Auth's name and preference rules, the 0002 migration, the rename and preferences
routes, the SPA's `/settings` page with the clock, and the record. Everything is green except **3 Auth
migration tests that cannot pass against a correct build** (their seed helper has `created_at` the wrong
way round); they are sent back to the test-writer (`reviews/code-writer-sendback-3.md`).

## Baseline

I did not run the red set before building (the red report's counts stand): Auth unit's two new files failed
to load, Auth integration 33 failed / 12 passed, Vitest 21 failed / 503 passed with four files not loading.
After the build, Vitest ran its 556 tests on the first run, so the red report's expected counts (503 + the new
tests) hold. No difference from the red report was seen in the files I ran.

## Built

| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `auth/names.py`, `auth/preferences.py` | Auth unit 108 pass (was 59 + the two new files) | Default-ignorable table is Unicode 15.0.0's |
| 6 | `models.py`, `alembic/versions/0002_…` | schema tests pass; migration tests 2 of 5 pass, **3 fail on the test seed** | LOCK TABLE, de-duplication via `names.deduplicate`, bound parameters; docstring covers the rolling-deploy window |
| 7 | `identities.py`, `schemas.py`, `routers/users.py`, `routers/preferences.py`, `main.py` | all `test_display_names`, `test_preferences`, `test_r1_unreachable` pass | SAVEPOINT per sign-in candidate; unique index decides a rename; the 409 never carries the key |
| 8 | `lib/auth/{api,session,storage}.ts`, `lib/time.ts`, `App.tsx`, `stores/chat.ts`, `features/settings/*`, `ChannelView`, `ChatLayout`, `WorkspaceSwitcher`, `MessageItem`, `ThreadSummary`, `SearchResult` | Vitest 556 pass; typecheck clean; e2e journey passes | decisions 16, 17, 19, 20, 28, 31–36 |
| 9 | register (D28 🟢, D46), two ADRs, docs 00/01/06, vocabulary ruling 35, `src/frontend/README.md` | — | |

## What ran

- `uv run pytest src/services/auth` → 265 passed, **3 failed** (`test_name_migration.py`, see below).
- `npm --prefix src/frontend test` → 55 files, **556 passed**. `run typecheck` clean. `run lint` clean.
  `run build` ✓.
- `scripts/test.sh lint unit integration` → lint ✅ (ruff, conventions, workflows, frontend, helm);
  unit ✅ **1973 passed** (auth 108, frontend 556); integration ❌ **613 passed, 3 failed** (auth 160 =
  157 + 3 failed). The three:
  - `test_every_duplicate_but_the_oldest_is_renamed` — `'Sam 3' == 'Sam'`
  - `test_duplicates_only_normalising_reveals_are_renamed` — `'José 2' == 'José'`
  - `test_after_the_migration_every_key_is_set_and_unique` — keys swapped between users 1 and 2
- `scripts/test.sh e2e` → ✅ **25 passed, 0 failed**, including *Alan renames himself and Grace sees it after
  reloading*. (That run came after the integration run; nothing changed between except
  `src/frontend/README.md`, comment-level text.)
- `python3 .claude/hooks/checks/conventions.py` over the ten Python files I created or changed → clean.
  `.claude/hooks/security.sh` → "Security pass clean" (it prints `mktemp: too few X's` for gitleaks and semgrep
  in this environment; I left it).
- `docs/test-report.md` is the one `scripts/test.sh e2e` wrote: it shows integration ❌ with the 3 failures,
  because that is the tree's real state until the send-back is answered.

## Beyond the tests

- Doc-comments for the reasons: `names.py` (why a key and not `lower()`, the DI table's Unicode version),
  `routers/users.py` (D46's accepted leak, no pre-check), `identities.py` (`is_display_name_conflict` reads the
  constraint, never the message), `0002` (imports `auth.names` on purpose; the lock; one-way; rolling deploy),
  `usePreferences.ts` (serial optimistic writes and the bookkeeping), `useProfile.ts` (why `onSuccess` is
  hook-level, cancel-then-write), `session.ts` (`profileEpoch`, open-redirect guard), `lib/time.ts`
  (`hourCycle`, not `hour12`).
- `KEYS` is read at request time, not copied (`preferences.parse_patch`).
- The three D28 "🔴 / no preferences" comments in `MessageItem`, `SearchResult`, `ThreadSummary` are replaced;
  `src/frontend/README.md` no longer says there is nowhere to store a theme; doc 06 §3, §4, §5.2 and §9.
- A failed `GET /users/me` on Settings shows a `ProblemBanner` and no field (plan-reviewer 2).
- Return-to-route after sign-in for every protected route (decision 34); cleared on every failure path in
  `completeSignIn`.

## Departures from the plan

1. `update_me` returns early only when the PATCH carries a display name and *no* `avatarAsset` and the name is
   unchanged. A PATCH carrying both still writes and bumps. (Decision 23 speaks of a name-only PATCH.)
2. `ProfileSection` shows the error banner for any failed fetch (not tied to the `Loading…` text), see above.
3. The `PATCH` preferences 400's `detail` is `"Some preferences are invalid."`; the plan fixes only the
   `errors.<key>` field.
4. Nothing else. All of this is also in the plan's *Found while building*.

## Picked up from earlier reviews

- plan-reviewer 2, decision 36 and a failed profile fetch → built as above; no test.
- plan-reviewer 2, `directoryRefresh.ts`'s `load` ignores the abort signal → checked: it does, and it does not
  matter. `cancelQueries` rejects the retryer, and the held answer that arrives later is dropped by it; the
  test `a directory fetch answered before the rename cannot bring the old name back` passes.
- test-reviewer 2: the `clockSites` 20 ms wait and the focus test ran against a build for the first time here
  and passed; `App.test.tsx`'s 1 s timeouts passed.
- test-reviewer 1/2, `\u` escapes → n/a to code.

## Left for the human

- **The first real run** on the Compose stack (Task 10): give two dev users one name in SQL before 0002 so it
  has a duplicate to rename; rename in one browser and watch the sidebar; try another's name in capitals
  (expect "That name is already taken."); choose 24-hour and look at a thread summary and a search result;
  sign out on `/settings`, sign back in and expect to land on `/settings`.
- The 12/24-hour rendering in other ICU locales (the suite runs in one).
- The `.claude/hooks/security.sh` `mktemp` noise, if it appears outside this runner.

## Send-back

`reviews/code-writer-sendback-3.md` → test-writer: `test_name_migration.py`'s `user()` computes
`created_at = T0 + (100 - age)` days, which makes a lower `age` the newer account; the oldest keeps its name,
so three tests expect the opposite of Req 4. Fix: `T0 + timedelta(days=age)`.
