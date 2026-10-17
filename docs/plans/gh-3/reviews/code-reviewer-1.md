# Code review — gh-3, round 1: changes_requested

The code does what the plan says. Every suite I ran is green, the journey passed, and every
premise I wrote down before opening the code holds in the real code, including two races the
tests don't cover, which I probed. One major finding stops approval: the record. Two places,
the root `README.md` and a comment in `index.css`, still say D28 is open and that no preferences
feature exists. That now contradicts the register this slice settled. The fix is two doc edits.

## Expectations

Written from the issue, the plan (decisions 1–37, Tasks 5–12), the red report, the test review and
the pre-writer code (`git show 6dc9da4:<path>`: `routers/users.py`, `identities.py`, `models.py`,
`session.ts`, `ChatLayout.tsx`, `App.tsx`), before any file the writer touched was opened.

**Task 5 — `names.py`, `preferences.py`.**
- *Unpinned:* the three exact messages; `stored_form` is `strip()` then NFC (not NFKC); `name_key`
  is NFC(casefold) — tested. `apply_patch` returns what SQL `RETURNING` gives, not a Python merge
  (decision 24 "no Python copy"); bound parameters only (CH006). `read` never inserts.
- *Wrong builds:* a Python read-modify-write merge (caught by the race test); `apply_patch` called
  for `PATCH {}` writing a row (tested); a merge whose INSERT branch stores `remove` keys.

**Task 6 — models, migrations.**
- *Unpinned:* `@validates("display_name")` sets the key on every assignment (incl. the
  constructor); the docstring says why the key is stored; 0002 orders `(created_at, id)`, reads
  deleted rows (CH009 waiver), `SET NOT NULL` after the update, index unique; downgrade drops index
  and column; 0003 FK to `users.id`, `server_default`s. `UserPreferences` model matches 0003.
- *Takes for granted:* the migration can import `auth.names` (Alembic env on the path).

**Task 7 — identities, schemas, router.**
- *Unpinned:* `_is_name_conflict` checks the **constraint name** (`ux_users_display_name_key`), so
  the email index never becomes a 409 or a retry; `_taken_keys` has no `deleted_at` filter (only an
  outcome test — retry papers over it) with the waiver citing D46/§3; the prefix match escapes
  `%`/`_`; at most 10 retries then re-raise; the own workspace named from the *stored* name;
  `updated_at`/`version` move out so an avatar-only PATCH still bumps and a no-op doesn't; the 409
  carries no name; nothing logs a name.
- *Takes for granted:* a SAVEPOINT rollback leaves the outer transaction (the OIDC callback's)
  usable and the failed `User` expunged; after a refused rename the `user` object is not committed
  by anything later in the request; `exc.orig.__cause__` is asyncpg's error.
- *Could go wrong:* email-violation treated as name-violation → retry loop on an email race
  (too much); deleted rows skipped (too little); version bump on no-op; a 500 on a non-object
  preferences body; `GET /me/preferences` creating a row; 404 detail differing from `/me`.

**Task 8 — SPA.**
- *Unpinned:* `ClockProvider` actually wraps `ChatLayout`'s tree (the ClockProvider tests mount
  the provider themselves — a build that forgets it in the shell may pass everything); `hourCycle`
  not `hour12` (decision 33; red report says the test can't tell); `useClock()` null outside;
  `setQueriesData` returns `undefined` for an entry with no data and maps only the profile's user;
  `useProfile` `refetchOnMount: 'always'` (test-review finding 3 says a revisit can't tell);
  form waits for `isFetchedAfterMount`; `resetLastChannel()` in the workspace cleanup.
- *Takes for granted:* the directory cache under `['workspace-members', ws]` holds a flat
  `WorkspaceMember[]` (whatever `useWorkspaceMembers` stores — must match the updater); ChatLayout
  stays mounted across `/c/x` → `/settings` so `lastChannelId` survives; author names on one's own
  messages come from the directory.
- *Could go wrong:* the clock's `onMutate` without `cancelQueries` — a preferences fetch in flight
  (Settings' `refetchOnMount: 'always'`, a focus refetch) lands after the optimistic write, then
  `onSuccess`'s "only if the cache still holds my value" refuses to write the server's answer: the
  tab shows the old choice while the server stores the new (the standard TanStack optimistic
  recipe cancels first; the plan doesn't say). Two failures in a row restore an unsaved value
  (plan-review-2, optional). A non-Problem error (network) on Save shows nothing. "Saved" lingering
  after a new edit. Save clickable while pending.
- *Wrong builds a test may miss:* no `ClockProvider` in the shell; no `refetchOnMount: 'always'`;
  `hour12`; `resetLastChannel` missing on workspace change.

**Task 9 — return path, `updateProfile`, `adopt`.**
- *Unpinned:* the `//` refusal applies to a path from `location.state` only; `signIn()` from the
  plain sign-in page clears; `Protected` passes `pathname + search`; `profileEdits` read *before*
  the fetch.
- *Could go wrong:* `Callback` taking the path even when sign-in failed (must only on success);
  the path consumed by StrictMode's double effect (effect runs twice — second `takeReturnPath`
  returns null → lands `/`?). In production no StrictMode double, but `completeSignIn` returns false
  on the second run anyway.

**Task 10/11 — record.** Register D28 🟢 and new D46 🟢 with the soft-delete exception and the
stored key; Conventions §3 third exception, §5.4 D46 exception; two ADRs; doc 01 §3 routes + 409 +
normalising, §4 key + index + `user_preferences`, §5.1 suffix rule; doc 06 §3 settings, §4 return
path + kept profile, §5.2 renamer's tab, §9 D28; README D28 lines; MessageItem/SearchResult/
ThreadSummary docstrings no longer say "D28 🔴". Each claim read against the code.

**Task 12.** `docs/test-report.md` at this revision `-dirty`, lint/unit/integration/e2e passed,
the `settings` journey passed in `build/test-results/e2e.xml`.

## What ran

- `npm --prefix src/frontend test`: 54 files, **558 passed**. `run typecheck`: clean. `run lint`:
  clean. `run build`: built (408 kB JS).
- `uv run pytest src/services/auth/tests/unit`: **107 passed**. `uv run pytest
  src/services/auth/tests/integration`: **157 passed** (Docker reachable). `ruff check` and
  `ruff format --check` on `src/services/auth`: clean.
- `python3 .claude/hooks/checks/conventions.py` on the 8 changed Auth files, by name: no findings.
  The two CH009 waivers (`_taken_keys` and the migration read) cite D46 and §3.
- Evidence for `scripts/test.sh`: `docs/test-report.md` is stamped `6dc9da4bec6f-dirty`, which is
  the tree the writer built on, committed by the runner as `8fe2f32`. It shows Lint, Unit 1860,
  Integration 594 and End-to-end 25, all passed, matching the green report's *What ran*.
  `build/test-results/e2e.xml` has `test_grace_sees_the_name_alan_gives_himself_on_his_message`
  (feature *Settings*), and the report lists it as passed.
- `git diff --name-only 6dc9da4 HEAD`: no test, helper or fixture was touched. Every changed file
  is in the file map, or is `useClock.ts` / `useWorkspaceMembers.ts` (departures 1 and 2).
- **Mutants and probes** (`sketch.sh frontend`):
  1. `ChatLayout.tsx`: `ClockProvider` removed from the shell. Ran `features/settings`,
     `features/channels` and `App.test.tsx` (33 files, 322 tests): **survived**. Probe
     `probe.test.tsx` renders `<App/>` at `/c/<id>` with a 13:05 message. With `{clock:'24h'}` it
     expects `13:05`; with `{}` it expects no `13:05`. The probe **failed the mutant** (`01:05 PM`
     rendered) and **passed on the real code**.
  2. `usePreferences.ts`: `await cancelQueries` removed from `onMutate`. Ran `features/settings`
     (28 tests): **survived**. Probe `probe2.test.tsx` makes a direct load of `/settings`, holds
     the preferences GET, clicks `24-hour` (the PATCH succeeds), then releases the GET with `{}`.
     It expects `24-hour` still checked. The probe **failed the mutant** (it fell back to
     Automatic, while the server held 24h) and **passed on the real code**.
  3. `ChatLayout.tsx`: `resetLastChannel()` removed from the cleanup. Ran `SettingsPage.test.tsx`
     and `chat.test.ts`: **caught** (`goes back to the last channel, or home after a direct load`).
  4. `useProfile.ts`: the `setQueryData(profileKeys.mine…)` write on success removed. Ran
     `SettingsPage.test.tsx` (16): **survived**. I walked the real code instead of probing (see
     *Unpinned*).
  5. Not run, because each is equivalent or already shown: `refetchOnMount: 'always'` removed
     (equivalent here, since the app's `staleTime` is 0 and data is always stale on mount);
     `hour12` (the red report showed it can't be told apart on this ICU); `scope`, unconditional
     restore and `cancelQueries` for the directory (the test review caught each).
  - Python was not mutated. The red report and the test review ran the unit wrong builds. For
    the integration-level mutants my *Expectations* named (an email violation taken for a name
    violation; a deleted-row filter in `_taken_keys`), I read the code, and it is right (see
    *Unpinned*).
  - `sketch.sh clean` was run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T5 `names.py`: interface, refused set, messages | `auth/names.py`. The range table matches the plan and DerivedCoreProperties, and the messages are exactly the plan's | as planned |
| T5 `preferences.py` (d24 to d26) | One `pg_insert…on_conflict_do_update…returning`. `PATCH {}` reads and doesn't write. Errors are collected per key | as planned |
| T6 models, 0002, 0003 | `@validates` sets the key. 0002 orders `(created_at, id)`, reads deleted rows, sets NOT NULL, then adds the unique index. 0003 is as the plan gives it | as planned |
| T7 identities (d16, d19) | `_is_name_conflict` matches on the constraint name. Taken keys come with no deleted filter and `autoescape=True`. 10 attempts, then re-raise. The workspace is named from `user.display_name` | as planned |
| T7 router (d14, d15) | Null gives 400. A `stored_form` no-op is checked before validation. 400 and 409 as the wire contract says. Preferences routes come before `/{user_id}`, and a deleted account gets 404 `GONE` | as planned. The avatar no-op is departure 5 (recorded) |
| d31 rename writes | Hook-level `onSuccess`: `updateProfile`, then the profile query, then an awaited `cancelQueries`, then `setQueriesData` (only the profile's user; `undefined` stays `undefined`), then `invalidateQueries` | as planned |
| d32 to d34 clock | `ClockProvider` in `ChatLayout`. `useClock` is null outside. `hourCycle`. Optimistic writes guarded on both sides. `scope`. A cancel in `onMutate` (beyond the plan, and right) | as planned. `useClock.ts` is departure 1 |
| d35 settings queries | `useProfile` with `'always'`. The form waits for `isFetchedAfterMount`. `usePreferences` uses the defaults | departure 3, equivalent |
| d28 return path, d37 adopt | `Protected` passes `state.from`. `SignIn` hands it to `signIn`. Every `return false` clears it. `takeReturnPath` refuses `//`. `profileEdits` is read before the fetch | as planned |
| d29 `lastChannelId` | Store and cleanup reset | as planned |
| T10 docstrings, README (src/frontend) | Rewritten | as planned, **but the sweep missed two files** (finding 1) |
| T11 record | Register D28 🟢 and D46 🟢 in the Settled list. Conventions §3 has a third exception and §5.4 the D46 note. Two ADRs. Doc 01 §3, §4 and §5.1. Doc 06 §3, §4, §5.2 and §9 | as planned |
| T12 verification | Report stamped and every layer passed | as planned |

## Findings

### 1. The sweep left D28 described as open and preferences as nonexistent — major
**Where:** `README.md:45-47`, `src/frontend/src/index.css:7-14` · **Checked:** Grep for
`no user-preferences|D28` outside `docs/plans`.
The root README says "Still open and worth knowing about: **D28** — there is no user-preferences
feature anywhere, which is why the SPA is light-only". The `@theme` comment in `index.css` says
"there is no user-preferences feature in the design at all … Revisit when preferences exist."
Both are false now: D28 is 🟢, and Auth stores preferences. Task 10's own sweep command
(`grep -rn "…preferences" … src/frontend`) finds the `index.css` line. The root README lies
outside that grep, but it contradicts the register this slice settles, which is the thing
CLAUDE.md warns about. **Fix:** rewrite the README sentence to drop D28 from "still open". You
can say that D28 is settled (Auth stores preferences; the first is the clock) and that the SPA
is still light-only because no theme preference exists, as `src/frontend/README.md` now says.
Rewrite the `index.css` comment the same way: preferences exist, a theme isn't one of them, so
the palette stays light-only. Leave `docs/adr/260815-tailwind-v4…` alone, because an ADR records
its own date. No test is needed.

### 2. A missing space in `update_me`'s docstring — minor
**Where:** `routers/users.py`, `update_me` docstring, "left alone;`avatarAsset: null`" ·
**Checked:** read. Add the space while you're in the file for finding 1's round.

## Unpinned

What only reading protects. The code is right in each case today:
- **The clock reaches the app at all.** The `ClockProvider` tests mount the provider themselves,
  so removing it from `ChatLayout` passes every approved test, and Req 7 would silently do
  nothing. My probe (mutant 1) shows the real shell applies it.
- **A clock chosen while a preferences read is in flight.** Without `onMutate`'s
  `cancelQueries`, the stale read lands, and `onSuccess`'s guard then refuses the server's
  answer. The tab would show Automatic while the server stores 24h. The writer added the cancel,
  which the plan didn't name. My probe (mutant 2) shows it holds.
- **The field after a save.** `useUpdateDisplayName` writes `['user-profile', id]` before its
  first `await`. The per-call `onSuccess` (`setDraft(null)`) runs after the hook-level one has
  resolved, so the field shows the new name, not the old one. No test fails if the write goes.
- **Email violations stay errors.** `_is_name_conflict` compares `constraint_name` with
  `ux_users_display_name_key`. Nothing drives an email race at sign-in.
- **Deleted names are read at sign-in.** `_taken_keys` has no `deleted_at` filter. The only test
  is an outcome test, which the retry loop would pass anyway (test review).
- **`update_me` writes nothing for an unchanged avatar** (departure 5). No test covers it.

## Left for the human

- The assumed decisions: 12, 13, 15, 17/19/22, 25, 28, 29, 30, 34 and 37 (as the earlier reviews
  list).
- Plan-review 2's optional item is still open. Two clock saves that fail in a row restore a value
  the server never stored. The next visit reads from the server.
- The first real run, as the green report lists it. Sign out on `/settings` and back in. Watch
  that an afternoon time follows the clock in a channel, a thread summary and a search result.
- `origin/feature/gh-3-run1` edits the same files. Only one of the two branches can merge.

## Checked and sound

- The 409 body is the fixed sentence plus `errors.displayName`. No name is logged anywhere (no
  new log calls).
- Both PATCH routes are on `require_user`, and the row comes from `principal.user_id` (CH001).
- `GET /me/preferences` never inserts. `PATCH` validates everything before applying anything.
- The no-op check comes before validation, compares the trimmed NFC form with the stored name, and
  so lets a case-only change through to `rename_user`.
- `adopt()` reads `profileEdits` before `Promise.all`. `updateProfile` ignores another user and a
  signed-out session.
- The return path is written only from `location.state`. It is cleared on every `return false`,
  read once, and refused for `//`.
- `setQueriesData` maps only the renamer and leaves an empty entry as `undefined`.
- Mutant 3 (`resetLastChannel`) is caught.
- The docs read against the code: doc 01's suffix rule (clean, then suffix, then SAVEPOINT, then
  10 tries), doc 06 §5.2's order of writes, the D46 row's key and index, and §3's named reads.
  Each matches the code.
