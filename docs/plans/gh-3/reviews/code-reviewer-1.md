# Code review — gh-3, round 1: approved

The build does what the plan says, task by task. It has one departure, recorded with a sound
reason: `useClock` reads the cache through a subscription rather than a `skipToken` query. Every
check I reran is green, and the record is written and matches the code. Nine of twelve mutants
were caught. The three survivors are harmless or correct on reading, and a probe passed for the
one that mattered. No critical or major finding is open.

## Expectations

Written from the issue, the plan, the red report, the approved tests and the pre-change code
(`b5f3ffd`) before any production file the writer touched was opened.

### Task 5 — names, key, migration
- **Not pinned:** `DEFAULT_IGNORABLE` holds every range the plan lists (the unit tests sample
  four of nineteen); `MAX_LENGTH` used by `candidates`; `name_key` is NFC *after* casefold;
  the migration runs in one transaction and its downgrade drops table, index and column;
  `user_preferences.user_id` a real FK; `updated_at` timestamptz.
- **Takes for granted:** that every write of `display_name` goes through the ORM so
  `@validates` runs — any `update(User)…values(display_name=…)` or raw SQL would skip it. The
  migration's `SELECT … ORDER BY created_at, id` reads deleted rows too (no `deleted_at`
  filter, on purpose: deleted names stay taken).
- **Could go wrong:** `dedupe` giving an empty name `"user"` that collides with a stored
  `"user"` (must suffix too); a suffix colliding with a later row's own name (Decision 22);
  the key column backfilled for unchanged rows as well as changed ones (else `NOT NULL`
  fails); key computed from the *normalised* name, not the raw one.
- **Wrong build:** key from `lower()`; validator setting the key only in `__init__`; dedupe
  over raw rather than normalised names — tests catch each (unit + migration integration).

### Task 6 — provisioning and routes
- **Not pinned:** that a non-name `IntegrityError` is re-raised (no test makes one); nothing
  logged with the name; `/me/preferences` declared before `/{user_id}` (tested by status);
  `find_user` before `parse_patch` (404 before 400 for a deleted user with a bad body);
  `updated_at` set by the merge; docstrings updated.
- **Takes for granted:** `IntegrityError.orig.__cause__.constraint_name` is how the asyncpg
  adaptor exposes the constraint (check installed SQLAlchemy); that a failed flush inside
  `begin_nested()` leaves the outer transaction usable and expunges the added `User`;
  that `db_session` does not commit after the route raises; that after a rename's flush
  fails the route rolls back before raising, so "nothing changes".
- **Could go wrong:** the 409 path leaving the session failed and the dependency's
  commit/close raising a 500; the provision loop retrying forever on a non-name violation
  (email race) — it must re-raise; the workspace named from the IdP's raw name instead of
  the result; same-name check comparing raw input rather than the stored form (Decision 24);
  version/updated_at bumped on the same-name no-op, or the avatar dropped by it.
- **Wrong build:** catching every `IntegrityError` as 409 — no test catches it (unverified
  until read); a pre-check `SELECT` instead of the index — race tests catch it.

### Task 7 — SPA plumbing
- **Not pinned:** `storage.returnPath` with the same lifetime/comment as `pkceVerifier`;
  `updateProfile`'s counter bumped and `adopt`'s guard applied to renewal as well as switch
  (only the switch is tested); `takeReturnPath` called only on a completed sign-in.
- **Takes for granted:** `adopt` is the only writer of `session.profile` besides
  `updateProfile`; `Protected`'s `<Navigate>` can carry `state` and `SignIn` reads it from
  `useLocation()`.
- **Could go wrong:** the guard comparing against the wrong id (fetched vs. session) or
  keeping the session's profile when the user changed; a failed callback leaving a stale
  return path that a later successful callback honours (acceptable — `signIn` clears or
  rewrites it first); `formatTime` with no clock not identical to today's output.

### Task 8 — page and clock
- **Not pinned:** Save disabled while a save is pending (double click → two PATCHes); the
  field error cleared on the next edit; the field *not* reset from the profile query's
  refetch after `applyRename`'s invalidate (would wipe an edit typed after Save);
  `setLastChannel` beside `setActiveChannel`; `usePreferences` options `staleTime` 5 min,
  refetch on focus/reconnect (Decision 28); the clock error cleared on the next choice;
  `aria`/labels for the radiogroup.
- **Takes for granted:** the directory cache's shape is `WorkspaceMember[]` under
  `['workspace-members', ws]` (tests seed arrays); message authors come only from the
  directory; `isFetchedAfterMount` is per observer, so a page with `fresh` shows nothing
  until its own GETs answer — on every visit, not only the first.
- **Could go wrong:** `applyRename` writing rows of other users; `useClock` (now a cache
  subscription, departure 1) returning a new object each snapshot → render loop, or missing
  a query added after mount; revert when the snapshot is `undefined` (`setQueryData(undefined)`
  is a no-op); `onSettled` invalidating on every settle instead of only the last;
  `ChatLayout`'s cleanup clearing `lastChannelId` on unmount as well as on switch (sign-out —
  fine) — and on *mount* under StrictMode (dev only).
- **Wrong build:** form initialised from the session profile rather than this visit's GET —
  caught; page-local mutation not writing directories — caught; `invalidate` without
  `setQueryData` — caught.

### Task 9 — record
- Register D28 🟢 (Decided 7, Decisions 25–28) and D46 🟢; two ADRs; conventions §5.4 gains
  the D46 exception; doc 01 §3 (two routes, 400/409), §4 (`display_name_key`, the index,
  `user_preferences`), §5.1 (suffix + IdP fallback); doc 06 §3, §4 return path, §5.2 Names,
  §9; vocabulary §35; stale comments in `MessageItem`, `SearchResult`, `ThreadSummary`,
  `schemas.py`, the two docstrings; no "D28 open" left.

### Task 10 — verification
- `docs/test-report.md` shows lint, unit, integration and e2e passed for this tree;
  `e2e.xml` lists `test_grace_sees_the_name_alan_gives_himself` passed.

## What ran

- `npm --prefix src/frontend test`: 58 files, **582 passed**. `run typecheck`: clean. `run lint`:
  clean. `run build`: built (408 kB JS).
- `uv run pytest src/services/auth/tests/unit`: **110 passed**. `uv run ruff check
  src/services/auth`: all checks passed.
- `uv run pytest …/integration/test_display_names.py …/test_preferences.py`: **33 passed** (Docker
  reachable).
- `python3 .claude/hooks/checks/conventions.py` over the 8 changed or new Auth files: no findings.
- **`scripts/test.sh` evidence.** `docs/test-report.md` shows lint, unit 1993, integration 625 and
  e2e 25 all passed at `15b9496bca31`. `git diff --name-only 15b9496 HEAD` lists only the green
  report, `docs/test-report.md` and `run/` state, none of which feeds a layer. The production code
  was committed at `74d103a`, before `15b9496`. *Journeys → Settings* reads "Grace sees the name
  Alan gives himself ✅". `build/test-results/e2e.xml` has
  `test_grace_sees_the_name_alan_gives_himself` and no `<failure>` or `<error>`.
- **Mutants** (sketch; each one alone, reset before the next):

| # | File · change | Tests run | Result |
|---|---|---|---|
| 1 | `usePreferences.ts` `onSettled`: invalidate when `isMutating >= 1` (on every settle) | `usePreferences`, `SettingsPage` | caught (*reverted only if nothing newer…*) |
| 2 | `usePreferences.ts` `onError`: unconditional revert | same | caught (same test) |
| 3 | `usePreferences.ts` `onMutate`: no `cancelQueries` | `usePreferences` | caught (*not undone by a read in flight*) |
| 4 | `useProfile.ts` `applyRename`: no directory invalidate | `useProfile`, `SettingsPage` | caught (2 tests) |
| 5 | `useProfile.ts` `applyRename`: renames every member's row | same | caught (3 tests) |
| 6 | `SettingsPage.tsx` `canSave` without `!rename.isPending` | `SettingsPage`, `App` | **survived** |
| 7 | `ChatLayout.tsx` no `usePreferences(current.accessToken)` (clock never loaded outside Settings) | whole suite (582) | **survived**. Probe below |
| 8 | `session.ts` `adopt` always takes the fetched profile | `session` | caught (*a switch in flight over a rename…*) |
| 9 | `ChannelView.tsx` no `setLastChannel` | `App`, `features/channels` | caught (*Back to chat returns to the channel visited before*) |
| 10 | `names.py` `dedupe` skips only `claimed`, not `held` | `test_names.py` | caught (`'Sam 2 2'`) |
| 11 | `names.py` `_cleaned` without the second NFC | `test_names.py` | caught (`é` uncomposed) |
| 12 | `identities.py` `is_name_taken` → always `True` | integration `test_display_names`, `test_users`, `test_schema` (43) | **survived** |

- **Probe** `src/probe.clock.test.tsx` (sketch). A signed-in `App` loads `/c/:id` with no Settings
  visit. The server holds `{clock:'24h'}`, then `{clock:'12h'}`. The probe asserts the message time
  reads `15:05`, then `3:05 PM` and not `15:05`. It **failed against mutant 7**, as it should, and
  **passed 2/2 against the real code**.
- `sketch.sh clean` was run. `git status --short` shows only this review.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| D14–16 key column, `casefold`→NFC, `@validates` | `models.py:41-71`, `names.name_key` | as planned |
| D17 409 via `orig.__cause__.constraint_name`, others re-raised | `identities.is_name_taken`; `users.update_me` | as planned |
| D18 savepoint per candidate | `identities._insert_with_free_name` | as planned |
| D19–20 `from_idp` with a second NFC; suffix cut | `names._cleaned`, `candidates` | as planned |
| D21–22 migration: trim/NFC, `"user"`, oldest by `(created_at, id)`, skip held suffixes | `0002_…py`, `names.dedupe` | as planned. One transaction (`engine.begin`), keys for every row, downgrade drops all three |
| D23 validation in the route, schema loses `min/max_length`, null stays 400 | `users.py`, `schemas.py` | as planned |
| D24 same stored form → no write; avatar still applied | `update_me` `changed` flag | as planned |
| D25–27 one upsert, flat shape, messages, empty patch still upserts | `preferences.merge`, `parse_patch` | as planned. `updated_at = now()` on update |
| Routes before `/{user_id}`; `find_user` first (404); FK to `users.id` | `users.py`, migration | as planned |
| D28 `['preferences']`, 5 min, focus and reconnect | `usePreferences` | as planned |
| D29 `formatTime`/`formatDateTime`, `hourCycle` | `lib/time.ts`; 3 components | as planned. With no clock, the options are the old ones |
| D30 scope, cancel, conditional revert, last-settle invalidate | `useUpdateClock` | as planned |
| D31–32 hook-level `onSuccess`; write then invalidate | `useUpdateDisplayName`, `applyRename` | as planned |
| D33 `/settings` inside `Protected`; `current-user` a `<Link>` | `App.tsx`, `WorkspaceSwitcher.tsx` | as planned |
| D34 `lastChannelId`, set by `ChannelView`, cleared in the workspace cleanup | `stores/chat.ts`, `ChannelView`, `ChatLayout` | as planned |
| D35 return path: state, storage, `takeReturnPath` safe-path check | `App.tsx`, `session.ts`, `storage.ts` | as planned. `takeReturnPath` runs only on a completed sign-in |
| D36, D41 Save rule over code points after trim/NFC, against the stored name | `SettingsPage` `NameSection` | as planned |
| D39 `adopt` guard by count and id | `session.ts` | as planned. It covers renewal and switch alike (one `adopt`) |
| D42 `useClock` only reads | `useSyncExternalStore` over the query cache | **departed**, recorded (green report 1; plan *Found while building* 1), with the plan-reviewer's reason. Sends nothing, leaves no options on the Query |
| Task 9 record | register D28 🟢, D46 🟢; 2 ADRs; Conventions §5.4; doc 01 §3/§4/§5.1; doc 06 §3/§4/§5.2/§9; vocabulary §35; stale comments; READMEs | as planned. `grep D28` leaves no "open" |
| Task 10 verification | test report and `e2e.xml` | done. The `docker compose` first run is left for the human (below) |

## Findings

None critical or major.

### 1. `useClock` re-subscribes on every render — minor
**Where:** `features/settings/usePreferences.ts:118-124` · **Checked:** read
The `subscribe` argument is a new arrow on each render, so React re-subscribes every
`MessageItem`, `ThreadSummary` and `SearchResult` on each of its renders. Each one also listens to
*every* query-cache event in the app. `getSnapshot` returns a primitive, so nothing re-renders
needlessly, and it is correct. It is churn on long message lists. A `useCallback`, or a
module-level subscribe keyed by client, would remove it. I would not block on it.

### 2. The green report's heading says "round 2" — minor
**Where:** `03-green-report.md:1` · **Checked:** read
This is the code pair's round 1. The second pass came after a send-back. Wording only.

## Unpinned

- **Save while a save is in flight** (mutant 6). `!rename.isPending` holds this, and nothing
  tests it. On reading, a second PATCH of the same name would be a no-op on the server
  (Decision 24), so leaving the guard out costs a request, not a wrong state.
- **The clock on a plain load** (mutant 7). Nothing in the approved suite fails if `ChatLayout`
  stops priming `['preferences']`, yet that is the only way Req 7 holds outside `/settings`. My
  probe shows the real code right in both directions. Only reading protects it from a later edit.
  It is worth a test-pair addition in a later change.
- **A non-name `IntegrityError`** (mutant 12). No test raises one, for example an email race in
  `provision_user`. On reading, `is_name_taken` compares `constraint_name` with
  `ux_users_display_name_key` and the caller re-raises anything else. So a concurrent first
  sign-in with the same email fails as it did before this change, and does not loop through
  suffixes. The 409 and race tests show the comparison matching the real index.
- `DEFAULT_IGNORABLE`: the tests sample four of its seventeen ranges. I compared the table entry
  by entry with the plan's list, and it matches.

## Left for the human

- Findings 1 and 2 (minor). Each asks for one small edit. Neither changes behaviour.
- **First real run** (plan Task 10). The code-writer left it undone. The e2e journey ran on the
  full Compose test stack, which covers the rename. On `docker compose up -d --build`, still check
  three things: Alan trying `GRACE` (the 409 body names nobody), 24-hour on a message after noon,
  and a sign-out and re-sign-in from `/settings` landing back on `/settings`.
- From test-reviewer-3, still unpinned: a decomposed-form same-name no-op at the API, and
  `{"theme": null}`. On reading, the route normalises before comparing, and `parse_patch` refuses
  any key but `clock`, `null` or not.

## Checked and sound

- Mutants 1–5 and 8–11 were caught by the tests the plan names for them.
- The 409 path rolls back before raising. `db_session` only closes. `expire_on_commit=False`, and
  the rolled-back `user` is not read afterwards.
- The savepoint loop builds a fresh `User` for each candidate. The workspace is named from
  `user.display_name`. Nothing is logged.
- The migration reads deleted rows on purpose (deleted names stay taken), writes a key for every
  row, and then sets `NOT NULL` and the index.
- `applyRename`'s prefix `['workspace-members']` matches only `directoryKeys.members` (grep), whose
  shape is `WorkspaceMember[]`.
- A workspace switch while on `/settings`: there is no navigation (grep `changeWorkspace`), the
  query keys carry no token, and the unsaved edit survives (tested). `lastChannelId` is cleared,
  so Back to chat goes to `/`.
- `takeReturnPath` refuses `//`, `/\`, absolute and relative paths, and is called only after a
  completed sign-in. A plain sign-in clears an old path.
- `updateProfile` writes only for a signed-in session with the same id. `adopt`'s guard keeps the
  session profile only for that same id.
- `formatTime` and `formatDateTime` with no clock pass the old options exactly.
  `MessageItem.test.tsx` holds this.
- The rules: `require_user` only, ids from the token, the 404 detail, Problem Details everywhere,
  camelCase, UTC `timestamptz`, no new env var, no suppression comments. D46's exception is
  recorded in Conventions §5.4.
- Nothing outside the file map changed except the two READMEs (stale D28 text, as Task 9 asks).
  Apart from the test-writer's round-3 fix, no test, helper or fixture changed since the red gate.
