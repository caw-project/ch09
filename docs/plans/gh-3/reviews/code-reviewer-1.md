# Code review — gh-3, round 1: send_back

The build matches the plan closely, and every check it names is green: Vitest 569, typecheck, lint, build, Auth unit 80, and the journey on the recorded e2e run. One probe fails. Migration `0002` finds duplicates with Python's `str.lower()`, but the index it then creates uses Postgres `lower()`. For a pair like "İvan" and "ivan", Python sees two different names and Postgres sees one. The migration renames neither, `CREATE UNIQUE INDEX` aborts, and Auth cannot be upgraded on that data. No approved test covers this, so by D32 it goes back to the test pair, who write the red test from my probe. The code-writer then fixes the migration.

## Expectations                 (round 1 — written before the code was opened)

Read first: the issue, the plan whole, the red report, both plan and test reviews, the approved
SPA tests (useProfile, usePreferences, SettingsPage, session, App, ChatLayout, storage, time,
test/api.ts) and the plan's Auth test tables, and `git show 0ac4c21:` of `session.ts`, `App.tsx`,
`WorkspaceSwitcher.tsx`, `storage.ts`, `routers/users.py`, `identities.py`, `migrations.py`,
`schemas.py`. One thing out of order: reading the plan through to its end took in its *Found while
building* (four lines: TABLES/test_schema not changed, `directoryKeys.all()`, radios unlock on
error, `{}` writes nothing). Nothing else the writer touched was open.

### Task 5 — names, migration, first sign-in
- **No test pins:** the CH009 waiver on `display_name_taken`; no name in any log call (incl. the
  migration); `downgrade` drops table and index; the migration UPDATEs only changed rows;
  `Index("uq_users_display_name", …)` on the model; **`is_display_name_conflict` telling the name
  index from the email one** — the plan's `test_schema` sharpening was not made (seen in *Found while
  building*), so nothing holds it.
- **Takes for granted:** `exc.orig.__cause__.constraint_name` is how the installed asyncpg adaptor
  chains; `begin_nested()` on the AsyncSession rolls back only the failed insert, and the `User`
  object is fresh per candidate (a rolled-back pending object re-added is a different state);
  Python `str.lower()` agrees with Postgres `lower()` for the migration's `reserved` set — where they
  disagree, `CREATE UNIQUE INDEX` fails mid-migration.
- **Could go wrong:** too much — any `IntegrityError` treated as a name conflict turns a two-tab
  first sign-in of one email into an endless candidate walk (no cap); too little — a lost race that
  re-raises instead of retrying fails a sign-in (pinned by the two racing tests).
- **Wrong build:** pre-check alone with no savepoint (caught by `test_two_first_sign_ins_with_one_name`);
  conflict check on bare `IntegrityError` (no test catches).

### Task 6 — the routes
- **No test pins:** other `IntegrityError` re-raises; PATCH prefs with `{}` writes nothing;
  `response_model_exclude_none`; GET prefs on `require_user` (only PATCH has the fail-open test).
- **Takes for granted:** the shared validation handler maps a body `loc` `("body","theme")` to
  `errors.theme`; `CAST(:remove AS text[])` binds an empty list under asyncpg; after `rollback()` the
  route raises without touching expired attributes.
- **Could go wrong:** no-op compared case-insensitively (would swallow "ADA"); no-op ignoring
  `avatarAsset` (pinned by the added avatar test); a version bump on the 409 path.
- **Wrong build:** read-modify-write merge (pinned by the lock tests).

### Task 7 — the SPA
- **No test pins:** `Protected` passing `pathname + search` (the tests use `/settings` with no query);
  the Callback's failure path setting `state.from` from what it took, so a retry still returns;
  dropping the "D28 🔴" comments; the storage header comment; `Save` guarding the Enter key (a form
  submit with an unchanged or invalid name); `Save` disabled while a save is pending; the profile
  form's behaviour when `GET /users/me` fails (does the page say anything, or hang on nothing?).
- **Takes for granted:**
  - `useClock`'s `getSnapshot` returns a primitive (an object would re-render forever);
  - the switcher's `useWorkspaceMembers` key matches `DirectMessageList`'s, so no new request and
    the rename's `setQueriesData` updates the very entry the sidebar reads; the directory cache's
    shape is what the updater maps (array vs object);
  - `usePreferences`' key carries no token, so a workspace switch neither refetches nor splits it;
  - `adopt()` reads the counter before *and* after the fetch; `updateProfile` calls `set()` so the
    sidebar re-renders.
- **Could go wrong:**
  - **the burst baseline, second time through** — "the value from before the burst" must be taken
    afresh at each new burst. A build that keeps the first burst's baseline restores a stale choice
    when a later, lone save fails (24h saved OK, then 12h fails → must show 24h). No approved test
    makes two bursts. Too much: a baseline reset by every mutation loses the burst rule (pinned).
  - "only the latest result applies": a counter that's never compared on success lets an older
    response land last (pinned by the ordered test only because scope serialises them).
  - the Callback taking the return path before `completeSignIn` settles, so a failure loses it.
  - `setQueriesData` updater on an entry whose data is `undefined` must return `undefined`.
  - the sidebar: Settings link `state.from` while on `/settings` itself becomes `/settings`.
- **Wrong builds to mutate:** no `cancelQueries` in either `onMutate`; per-mutation rollback; no
  invalidate after rename; mutate-level instead of hook-level `onSuccess`; no counter in `adopt`;
  sidebar reading only the session; `hour12` instead of `hourCycle`; `from` without `search`;
  `refetchOnMount: 'always'` dropped from Settings; radios not disabled before the fetch.

### Decisions to read against the code
13/15/16 (index sole arbiter, constraint name, savepoint walk), 20 (no write on no-op), 25
(return path, open-redirect filter), 29/30/36 (hook callbacks, epoch, cancel+invalidate), 31
(`useSyncExternalStore`, no second `useQuery`), 32 (scope), 33 (`hourCycle`), 37 (sidebar).

### What the record must say
Register D28 🟢 (Auth `user_preferences`, per user, validated keys, the clock) and new D46 🟢
(global, trimmed, case-insensitive, deleted included, the existence leak, `lower()` gap), both in
*Resolve First*'s settled list; two ADRs; doc 01 §3 (two routes, 400/409 on PATCH), §4 (table,
index), §5.1 (suffix rule); doc 06 §3 `features/settings`, §4 the `collabhub.returnTo` key, §5.2
the renamer's own tab, §9 D28; CLAUDE.md's D28 paragraph and the D46 tenancy exception; READMEs and
`index.css` reasons; the scenario vocabulary's Alan exception in §1 and ruling 6. Every claim must
match the code — the 409 wording, the key name, the `{}` no-write.

## What ran

- `npm --prefix src/frontend test`: 58 files, **569 passed**. `run typecheck`: clean. `run lint`:
  clean. `run build`: built (408 kB JS).
- `uv run pytest src/services/auth/tests/unit`: **80 passed**. `uv run ruff check src/services/auth`:
  all checks passed. `conventions.py` over the ten changed Auth files: no findings.
- `scripts/test.sh` evidence: `docs/test-report.md` shows Lint, Unit 1843, Integration 595 and
  End-to-end 25, all passed at `f45e31d7b664`. `git diff --stat f45e31d HEAD` touches only the green
  report, `run/` and the test report, so no code has changed since that run. The revision has no
  `-dirty` suffix because the code was committed when it ran. `build/test-results/e2e.xml` has
  `failures="0" errors="0"` and lists `test_grace_sees_the_name_alan_gives_himself_after_a_reload`.
  `integration.xml` has no `<failure>` or `<error>`, and includes test_display_names 13,
  test_first_sign_in_names 9, test_name_migration 4, test_preferences_api 10 and test_r1_unreachable 6.
- **Mutants (SPA, `sketch.sh test`):**
  1. `usePreferences.ts`: take the burst baseline only at `id === 1` (never afresh) → settings
     tests **survived** (27 passed). Probe below.
  2. `usePreferences.ts`: drop `cancelQueries` in `onMutate` → **caught** ("is not undone by a
     read that was already in flight").
  3. `usePreferences.ts`: `onError` rolls back on any failure, not only the latest's → **caught**
     ("ignores a failure behind a later choice").
  4. `useProfile.ts`: drop the directory `invalidateQueries` → **caught** (2 tests).
  5. `useProfile.ts`: skip `session.updateProfile` → **caught** (incl. the unmount test).
  6. `App.tsx` `Protected`: `from: pathname` without `search` → App + lib/auth tests **survived**.
  7. `App.tsx` `Callback`: failure path drops `state.from` → App tests **survived**. Probe below.
  8. `session.ts`: `profileWrites` guard never applies → **caught** (renewal-in-flight test).
  9. `WorkspaceSwitcher.tsx`: name from the session only → **caught** (ChatLayout directory test).
  10. `SettingsPage.tsx`: drop the submit guard (`!valid || !changed || isPending`) → **survived**.
  11. `SettingsPage.tsx`: preferences without `refetchOnMount: 'always'` → **survived**. It is
      equivalent today: `main.tsx` sets no `staleTime`, so a mount refetches anyway.
  12. `time.ts`: `hour12` in place of `hourCycle` → formatter tests **survived** (24 passed), as
      test-reviewer-2 predicted.
- **Probes (SPA), on the real code:**
  - `probe.test.tsx`: start at 12h, save 24h successfully, then choose Automatic and have it
    fail. The cache must go back to 24h. **Passed** on the real code, and **failed** on mutant 1
    (`{clock:'12h'}`), so the probe tells the two apart.
  - `probeApp.test.tsx`: `returnTo=/settings` stored, `/auth/callback?error=access_denied`, then
    Sign in again → `/settings` stored again. With nothing stored → `null`. **Both passed.**
- **Auth (`sketch.sh service auth`, `sketch.sh pytest`, real Postgres via testcontainers):**
  - `test_probe_lower.py`: the migration from 0001 to 0002, with an older and a newer account per
    pair: `İvan`/`ivan`, `ẞSA`/`ßsa`, `ǅura`/`ǆura`, `KK` (Kelvin sign)/`kk`. **`İvan`/`ivan` failed**:
    `UniqueViolationError: could not create unique index "uq_users_display_name" DETAIL: Key
    (lower(display_name::text))=(ivan) is duplicated.` Captured: `pg lower: ['ivan', 'ivan'] py
    lower: i̇van ivan`. The other three passed. → Finding 1.
  - `test_probe_email_conflict.py`: a deleted account keeps its email, and a new first sign-in
    uses that email → `IntegrityError` with `is_display_name_conflict` False. A real name clash
    → True. **Both passed.**
  - Mutant: `is_display_name_conflict` returns `cause is not None` → test_schema, first-sign-in
    and display-names: **27 passed (survived)**. The probe **caught** it: `TimeoutError`, the walk
    through `X 2, X 3, …` never ends.
  - Mutant: `update_me` no-op compared with `.lower()` → **caught** (`ADA` ≠ `ada`).

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| 5 `names.py` (13, 17, 18, 19) | `validate_display_name`, `provisional_name`, lazy `candidates`, refused set as decision 17 | as planned |
| 5 migration `0002` (11, 21, 22, 23) | `_dedupe` with `auth.names`, reserved-first, oldest by `created_at, id`, UPDATE only changed rows, index then table; downgrade drops both | as planned in shape; **wrong key function** (Finding 1) |
| 5 model index, `UserPreferences`, `upgrade(dsn, revision)` | present | as planned |
| 5 `display_name_taken` + CH009 waiver, `is_display_name_conflict` (15), savepoint walk (16), workspace named from result | present | as planned |
| 5 conftest `TABLES`, `test_schema` `a_user` | not made — test files | departed, reason given (Finding 2) |
| 6 schema without `Field` limits; `PreferencesResponse` | present | as planned |
| 6 `update_me`: null 400, 400 message, exact no-op (20), flush in try, 409 fixed text, other `IntegrityError` re-raised | present; `{}` also writes nothing | as planned; `{}` departure recorded |
| 6 `preferences.read/merge` one statement, operators not interpolation | `insert…on_conflict_do_update`, `.op("||")`, `.op("-")`, `cast(…, ARRAY(Text))` | as planned |
| 6 routes on `require_user`, 404 detail, `{}` writes nothing, `exclude_none`, registered | present | as planned |
| 7 `api.ts` contract; `storage.returnPath` + header comment; `session.updateProfile` + counter (30); `signIn(…, returnTo)` | present | as planned |
| 7 `App.tsx`: `from` = pathname + search; SignIn passes it; Callback `take() ?? '/'`, failure carries `state.from`; `/settings` under `Protected` (25, 26) | present | as planned |
| 7 `WorkspaceSwitcher` link + directory name (37); `ChatLayout` `usePreferences` | present; `directoryKeys.all()` added | as planned; addition recorded |
| 7 `time.ts` `hourCycle` (33); three formatters on `useClock`; "D28 🔴" comments gone | present | as planned |
| 7 `usePreferences` (31, 32, 36), `useProfile` (29, 36), `SettingsPage` (27, 28) | present; radios also unlock on error | as planned; departure recorded |
| 8 record | register, ADRs, docs 01/06, CLAUDE.md, READMEs, `index.css`, vocabulary | as planned (see *Checked and sound*) |
| 9 verification | report and JUnit as above; sibling-branch check recorded | as planned |

## Findings

### 1. Migration 0002 decides "duplicate" by Python `lower()`, the index by Postgres `lower()` — critical
**Where:** `src/services/auth/auth/alembic/versions/0002_unique_display_names_and_preferences.py:37-46`
· **Checked:** probe `test_probe_lower.py` against real Postgres (output above).

`reserved` and `assigned` are built with `str.lower()`, and `CREATE UNIQUE INDEX … (lower(display_name))`
then judges with Postgres's. The two disagree for `İ` (U+0130). Python gives `i̇` (two code points)
and Postgres gives `i`. So an older `İvan` and a newer `ivan` do not look like duplicates to the
dedupe, neither is renamed, and the index build fails. That breaks Req 4 ("renames every
duplicate except the oldest") for this data, and the upgrade aborts. Its transaction rolls back,
so no data is lost. But Auth's entrypoint (`docker/auth/entrypoint.sh:11`) and the chart's
pre-upgrade `auth-migrate` Job both run it, so on such an installation Auth does not start in
Compose and `helm upgrade` fails. Nobody can sign in until a person renames the pair by hand.
`İ` begins common Turkish names (İsmail, İbrahim), so a pair like `İsmail`/`ismail` is ordinary
data.

**Settles it:** a red test in `test_name_migration.py`: an older `İvan` and a newer `ivan` → after
0002, `İvan` and `ivan 2`, and the index exists. The fix compares as the index does: Postgres's
`lower()` for every cleaned name and every candidate in `_dedupe`. For example, take each key
from `SELECT lower(:name)` on `bind`, which costs one query per row in a one-off migration. The
route and `provision_user` need nothing: the route relies on the index, and the pre-check is
already SQL `lower()`.

### 2. The plan's GREEN edits to `test_schema.py` and the integration `TABLES` were never made — minor
**Where:** `src/services/auth/tests/integration/test_schema.py`, `…/integration/conftest.py`
· **Checked:** read. The mutant above shows nothing approved pins `is_display_name_conflict`'s
negative half.

The plan gave two test-file edits to the code-writer, who may not write tests. The departure is
recorded and the reason holds: `TRUNCATE … CASCADE` clears `user_preferences`, and my email-clash
probe shows the real code is right. But the sharper citext assertion the plan wanted is still
missing. The test pair is taking a round anyway, so the send-back asks them to make both edits
(plan Task 5 file map).

## Unpinned

- **The burst baseline is taken afresh for each burst** (`pending === 0`). Mutant 1 survived. My
  probe passes on the real code and fails on the mutant. Worth adding to `usePreferences.test.tsx`.
- **The return path keeps its query** (`pathname + search`, mutant 6). Read: `App.tsx:106`.
- **A failed callback carries `state.from` to `/sign-in`** (mutant 7). Probe passed both ways.
- **Enter cannot submit an unchanged, invalid or pending name** (mutant 10). Read: the guard is
  the first line of `submit` (`SettingsPage.tsx:51`).
- **`refetchOnMount: 'always'` on Settings' preferences** (mutant 11). Equivalent under today's
  `staleTime` 0. It starts to matter only if a default `staleTime` is ever set.
- **`hourCycle` over `hour12`** (mutant 12). On this Node's ICU the two print the same, so only
  the code holds decision 33.
- **An email clash in provisioning re-raises rather than walking names.** The mutant survived 27
  approved tests. My probe passes on the real code and times out on the mutant (Finding 2).

## Left for the human

- **`CLAUDE.md` changed under a stage that may not write it.** The issue's *Record in this slice*
  asks for both edits. I read them against the code and they are accurate: the D46 bullet and
  "User preferences exist now". Keep them on purpose or revert them.
- **StrictMode in `npm run dev`:** the Callback's effect runs twice. The second
  `completeSignIn`, with no verifier left, takes the return path first, so a dev-server sign-in
  lands on `/` and not on `/settings`. The built container (production, no double effects) is
  unaffected, and CLAUDE.md already says not to run journeys on the dev server.
- **Clicking your own name while already on `/settings`** sets `state.from` to `/settings`, so
  Back to chat goes to `/` from then on. This is the plan's reading of decision 27. It is a small
  UX point, not a finding.
- Assumed decisions to read: 14 (`lower()` folding), 17 (ZWJ refused), 37 (sidebar from the
  directory). The first real run is as the green report lists. Add one check to it: run
  migration `0002` on a copy of real data before the first deploy.
- `security.sh`'s gitleaks/semgrep printed `mktemp` errors in the writer's environment. Rerun it
  where they work.

## Checked and sound

- Mutants 2, 3, 4, 5, 8 and 9 caught, and the Auth no-op `.lower()` mutant caught.
- 409 body: fixed text `"That name is already taken."` in `detail` and `errors.displayName`,
  through `ProblemException.conflict`. No name in any log call (grep of the diff: no logger
  call added).
- Tenancy: all three routes key on `principal.user_id`, take no id from the path or body
  (CH001), and use `require_user` only. GET prefs creates no row. 404 detail as on `/users/me`.
- `merge` is one statement built from SQLAlchemy operators (no CH006), and the caller commits.
  `PreferencesPatch` merges `extra="forbid"` with `CamelRequest`'s alias config (Pydantic v2
  merges `model_config`).
- `ProblemError` from `lib/auth/api` is the same class as `lib/api/client`'s (re-export), so
  `fieldError` works.
- `useClock`'s snapshot is a primitive (no render loop), and it subscribes without fetching.
  `useSetClock` uses `scope: {id:'preferences'}`. `setQueriesData`' updater returns `undefined`
  for an empty entry.
- The switcher's `useWorkspaceMembers(accessToken, activeWorkspaceId)` uses the same key as
  `DirectMessageList`, so it adds no request.
- The record: register D28 🟢 and D46 🟢, with both in the settled list. Both ADRs. Doc 01 §3
  rows, §4 SQL and the 0002 note, and the first-sign-in paragraph. Doc 06 §2 styling row, §3
  `/settings`, §4 the return-path key, §5.2 Renames, §9 D28. README, frontend README,
  `index.css`, and vocabulary §1 and ruling 6. Each matches the code (the 409 text, `{}` writes
  nothing, `collabhub.returnTo`, the refused categories).
- Nothing outside the file map changed except what the departures name (`useWorkspaceMembers.ts`)
  and the record. No test, helper or fixture was touched by the code stage
  (`git diff --stat b5f3409 HEAD`).
