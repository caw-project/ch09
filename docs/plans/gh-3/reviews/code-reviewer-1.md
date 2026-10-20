# Code review — gh-3, round 1: changes_requested

The code does what the plan says, and every check it names is green. I ran the SPA and Auth
unit suites, lint, the typecheck and the build myself, and checked the integration and e2e
evidence in `docs/test-report.md` and `e2e.xml`. Of 8 mutants, the tests caught 5; one survivor
is equivalent in this TanStack version, and the other two are held by reading or by a probe
that passes. One major finding blocks approval, and it is in the record only: the plan's own
Task 9 sweep left three places saying that D28 is open and that no preferences feature exists.
It is a docs-only fix. One probe found a small behaviour gap against decision 32. I've graded it
minor and left it for the human.

## Expectations                 (round 1 — written before the code was opened)

Read: the issue, the plan (decisions 11–36, Tasks 5–10), the red report, every earlier review,
and the pre-writer code at `08552a6` (`session.ts`, `App.tsx`, `routers/users.py`,
`identities.py`, `WorkspaceSwitcher.tsx`, `ChatLayout.tsx`, `stores/chat.ts`, `ChannelView.tsx`,
`useWorkspaceMembers.ts`, `directoryRefresh.ts`).

**Task 5 — `names.py`, `preferences.parse_patch`.**
- Not pinned: the docstring naming the Unicode version the DI table was checked against; the DI
  table's completeness beyond the code points the tests try (U+00AD, U+061C, U+180E, U+2060–206F,
  U+FFA0, U+1BCA0, U+E0000–E0FFF); `KEYS` read at call time.
- Wrong builds: `lower()` for `casefold()` (caught by Straße); length counted before NFC (caught);
  `deduplicate` not reserving later rows' own names before suffixing (caught by the "sam 2" test);
  `provisional` cutting to 100 *before* dropping refused characters (likely unpinned).

**Task 6 — model and migration 0002.**
- Not pinned: `LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE` before the read; bound parameters
  (CH006); renamed rows get `updated_at = now()` and `version + 1`; the docstring saying 0002
  imports `auth.names` on purpose, that the downgrade leaves names renamed, and the rolling-deploy
  window; `user_preferences.user_id` a real FK to `users.id`; `prefs` default `'{}'`.
- Takes for granted: `@validates("display_name")` fires on the constructor kwarg as well as on
  assignment (SQLAlchemy does run validators for constructor kwargs); nothing writes
  `display_name` through a Core `update()` that would bypass it (grep).
- Wrong build: the key computed from the *pre-dedup* name for renamed rows → the unique index
  creation fails on real duplicates (the migration tests should catch).

**Task 7 — provisioning, rename, preferences routes.**
- Not pinned: `is_display_name_conflict` checks the constraint *name*, re-raising every other
  IntegrityError (an email race in `provision_user` must not loop forever over an infinite
  `candidates()`); the 409's body exactly as Global constraints say, with no text from the
  IntegrityError (CH007) and no log of it (CH008); the `update_me` docstring stating D46's leak;
  preferences `find_user` → 404 *before* parsing; `PATCH {}` writes nothing; the upsert bound,
  never formatted.
- Takes for granted: `session.rollback()` after a failed commit leaves the request session usable
  for the error path; `begin_nested()` rolls back only the candidate's `User` and leaves earlier
  work in the outer transaction (the identity row is added after `provision_user`); the
  workspace named from the *stored* name, not the IdP's.
- Where it could go wrong: "saving the name you have" compared by key rather than exact string →
  a capitals-only change becomes a no-op (pinned by `test_changing_only_your_own_capitals`);
  the no-op path skipping the 404 for a deleted account; a non-object PATCH body on
  preferences (`[]`, a string) answering 500 or a non-Problem 422.

**Task 8 — the SPA.**
- Decision 16 (rename `onSuccess`): it must be the hook-level `useMutation({ onSuccess })`, and
  it must **await** `cancelQueries` before writing — TanStack's cancel with revert restores the
  state captured at fetch start, so an un-awaited cancel followed by `setQueriesData` lets the
  revert put the old name back. A directory with no data (initial load in flight, now cancelled
  and reverted to pending/idle) must be refetched, or its observers sit pending with nothing in
  flight. Likely unpinned: the no-data refetch; the `['profile','me']` write.
- Decision 17 (clock): `scope: { id: 'preferences' }`; the bookkeeping in a `WeakMap` per
  `QueryClient` (not module-global, not a `useRef`, which an unmount loses); `confirmed` snapshot
  only when `inFlight === 0`; non-latest responses never write. Pinned by the four outcome tests;
  the WeakMap-vs-ref choice probably is not.
- Decision 19: `useClock()` with `queryFn: skipToken`; `ChatLayout` fetches. Wrong build: a
  `useClock` that fetches itself (one GET per message row) — `clockSites`'s "no request" may catch.
- Decision 20: `hourCycle: 'h12' | 'h23'`, never `hour12`. **Unpinned** in an en-US ICU: `hour12`
  gives the same output there; reading is all that holds it.
- Decision 35 (`profileEpoch`): captured *before* `api.me()`; only the profile is kept, the token,
  workspaces and `wsp` always the fetched ones. Pinned by three session tests.
- Decision 36: render the form only once `isFetchedAfterMount`; seed once; a failed GET shows an
  error, not a stale or `undefined` field (earlier reviews ask for this; untested).
- Corrections 1 (return-to-route): `takeReturnTo` is single-use and refuses non-same-origin paths;
  `completeSignIn`'s failure paths clear it; `signIn` without a path clears an old one. Takes for
  granted: only `Protected` sets `from`, and its pathname always starts with one `/`.
- Decision 32: `lastChannel` set only when both ids are known, never cleared on unmount, used only
  when its workspace is the active one. Decision 33: a switch on `/settings` keeps the page
  mounted.
- Decision 28: Save disabled after JS `trim()` + NFC, code points counted with `[...s]`; a
  `.length` (UTF-16) build is wrong for astral characters — the 100/101 test uses ASCII, so
  likely unpinned.
- Rules: no server value in Zustand (D24) — `lastChannel` is client state; no `data-testid` read
  by Vitest; the four BDD test ids present.

**Task 9 — the record must say:** register D28 🟢 (Auth, `user_preferences`, validated keys, SPA
in TanStack), D46 🟢 (global, deleted included, the leak, the key column), header "Settled" line;
two ADRs; doc 01 §3 routes + 409/400s, §4 `display_name_key`/index/`user_preferences` and no
`deleted_at` filter on purpose, §5.1 suffix rule; doc 06 §3 settings, §4 return-to-route, §5.2 the
renamer's own tab, §9 D28 decided; conventions §5.4 the D46 exception; vocabulary ruling 35; no
stale "D28 🔴" or "Renames are not covered" left, and the D28 comments gone from the three
formatters.

**Task 10:** `docs/test-report.md` shows lint, unit, integration and e2e passed at this tree's
revision (or one with nothing since that is an input), the journey among the e2e passes.

## What ran

- `npm --prefix src/frontend test` printed **55 files, 556 passed**. `run typecheck` and
  `run lint` were clean, and `run build` printed ✓ built.
- `uv run pytest src/services/auth/tests/unit` printed **108 passed**.
  `uv run ruff check src/services/auth` printed "All checks passed!".
- `python3 .claude/hooks/checks/conventions.py` over the nine changed or new Auth files
  produced no output.
- **`scripts/test.sh` evidence.** `docs/test-report.md` shows Lint ✅, Unit ✅ (1973) and
  Integration ✅ (616) at `94bb82771969`. `git diff --name-only 94bb827 HEAD` lists only the plan
  dir and the report, so nothing that is an input has changed since. End-to-end shows ✅ 25 at
  `08552a6-dirty`, the code-writer's uncommitted tree. Since `d0e31cb`, where that code was
  committed, the only non-doc change is `test_name_migration.py`. That file is a test the e2e
  stack doesn't run, and the test-reviewer gated it in round 3. `build/test-results/e2e.xml`
  shows `tests="25" failures="0"` and names *Alan renames himself and Grace sees it after
  reloading*. The counts match the green report.
- **Mutants and probes**, in `build/sketch/frontend`:
  1. `useProfile.ts`: `await cancelQueries` → `void`. Ran `ProfileSection.test.tsx`: 8 passed,
     so it **survived**. It is **equivalent**: query-core 5.101's `retryer.cancel` calls
     `onCancel` synchronously, which reverts the state (`query.js:267-273`, `retryer.js:29-34`),
     and `setData` resets `#revertState` (`query.js:373`).
  2. `useProfile.ts`: dropped the refetch of directories with no data. Ran
     `ProfileSection.test.tsx` and `App.test.tsx`: 24 passed, so it **survived**. The probe in
     `probe.test.tsx` holds the directory's first fetch, renames, then releases the old answer,
     and expects the list to end loaded with "Ada L.". It **failed against the mutant** (no list
     items, so the query was left pending with nothing in flight) and **passed against the real
     code**.
  3. `usePreferences.ts`: snapshot `confirmed` on every click rather than only when
     `inFlight === 0`. **Caught** by "two failed saves go back to the choice before either".
  4. `usePreferences.ts`: every success writes the cache, not only the latest. **Caught** by
     "a second choice waits for the first save…".
  5. `usePreferences.ts`: removed `scope`. **Caught** by the same test.
  6. `lib/time.ts`: `hour12: clock === '12h'` in place of `hourCycle`. Ran `time.test.ts` and
     `clockSites.test.tsx`: 15 passed, so it **survived**. I did not probe it, because
     `timeOfDay` formats with the default locale (`[]`). The output differs only in locales such
     as `ja-JP`, and the test process fixes the locale, so no test can reach that without
     changing the code's locale argument. Reading shows the code uses `hourCycle`.
  7. `session.ts`: the epoch captured after `api.me()`. **Caught** by both "…read the profile
     before a rename keeps the renamed one" tests.
  8. `session.ts`: dropped the `//` guard in `takeReturnTo`. **Caught** by "takeReturnTo refuses
     //evil.example".
  - **Probe (decision 32)** in `App.test.tsx`'s copy: open `#general`, switch to Away while it is
    open, click your name, click Back to chat, and expect `/`. It **failed** and printed
    `Received: "/c/0199a000-…c001"`. See finding 2.
- `sketch.sh clean` was run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| 5 `names.py`: DI table, Unicode version in the docstring, `deduplicate` reserving kept names | `names.py` | as planned |
| 5 `preferences.parse_patch`, `KEYS` read at call time | `preferences.py:36,61` | as planned |
| 6 key column, `@validates`, unique index, `UserPreferences` with a real FK | `models.py` | as planned |
| 6 migration: lock first, bound SQL, `updated_at`/`version` on renamed rows, keys from final names, docstrings | `0002_…py` | as planned |
| 7 `is_display_name_conflict` by constraint name; other IntegrityErrors re-raised | `identities.py:61-68`, `users.py:96-104` | as planned |
| 7 `provision_user`: SAVEPOINT per candidate; workspace named from the stored name | `identities.py:120-137` | as planned |
| 7 `update_me`: validate, exact-string no-op, 409 with no exception text, D46 docstring | `users.py` | as planned; the no-op only for a name-only PATCH (departure 1, recorded) |
| 7 preferences routes: 404 first, all-or-nothing, `{}` writes nothing, one upsert | `routers/preferences.py`, `preferences.py` | as planned; `detail` text is departure 3 |
| 8 decision 16, hook-level `onSuccess`: cancel → write → refetch no-data → session → profile cache | `useProfile.ts:53-68` | as planned |
| 8 decision 17, scope + per-client WeakMap bookkeeping | `usePreferences.ts` | as planned |
| 8 decisions 19, 20: `useClock` with `skipToken`; `hourCycle` | `usePreferences.ts:73`, `time.ts` | as planned |
| 8 decisions 28, 31, 36: Save rules in code points, "Saved", wait for this visit's fetch, error banner | `ProfileSection.tsx` | as planned (departure 2) |
| 8 decision 32: `lastChannel`, Back to chat | `ChannelView.tsx:41-46`, `SettingsPage.tsx` | as planned literally; wrong after a switch made on a channel page (finding 2) |
| 8 decisions 33–35, Correction 1: return path, epoch | `App.tsx`, `session.ts`, `storage.ts` | as planned |
| 8 the three formatters; D28 comments removed | `MessageItem`, `ThreadSummary`, `SearchResult` | as planned |
| 9 register, two ADRs, docs 00/01/06, vocabulary | as diffed | as planned, except the sweep (finding 1) |
| 10 verification, *Found while building* | report and plan | as planned; the first real run is left for the human |

## Findings

### 1. The D28 sweep left three statements that preferences don't exist and D28 is open — major
**Where:** `docs/design/06-frontend-spa.md:39` (stack table, Styling row), `src/frontend/src/index.css:7-14`,
`README.md:45` · **Checked:** Grep for `no user-preferences|D28 is open|…` over the tree.
- Doc 06 line 39 still says "there is no user-preferences feature to store a theme choice in (§9)".
  But §9 now says D28 is decided.
- `index.css` says "there is no user-preferences feature in the design at all… Revisit when
  preferences exist."
- The root `README.md` lists D28 under "Still open… there is no user-preferences feature
  anywhere".

The register now says 🟢, and each of these contradicts it. The first two are inside the plan's
own Task 9 sweep (`grep -rn "…no user-preferences…" docs/design src/frontend/src`). The README
is outside that grep but says the same false thing. Reword each the way
`src/frontend/README.md` was reworded: preferences exist in Auth (D28), a theme is not one of
their keys, and the palette stays light-only. That needs no test. The two ADRs that mention it
(`260815-tailwind-v4…`) are history and should stay as they are.

### 2. Back to chat after a switch made on a channel page goes to the other workspace's channel — minor
**Where:** `features/channels/ChannelView.tsx:44-46` · **Checked:** probe (above), which failed.

A workspace switch leaves `ChannelView` mounted on the old `channelId`. Its effect then
re-runs with the new `workspaceId` and records `{new workspace, old channel}`, a pair that was
never opened. Decision 32 exists to send that case to `/`. What the user sees is the old
channel's 404 in the new workspace, which is where they already were before they opened
Settings. No data crosses tenants. The fix is to record the channel only once its detail query
has loaded, or only when `channelId` changes. It needs a red test first (D32), so I'm leaving it
for the human rather than sending it back.

### 3. A failed background refetch on Settings drops an edit in progress — minor
**Where:** `ProfileSection.tsx:45` · **Checked:** read.

`profile.isError` is checked before the form, and a failed focus refetch sets it while `data` is
still present. The field is then replaced by the banner and the typed text is lost. Gating the
banner on `data === undefined` would keep the form. This path is untested.

## Unpinned

- Mutant 2: the refetch of a directory that had no data when the rename landed. The probe
  shows the real code is right, but no approved test holds it.
- Mutant 6: `hourCycle` over `hour12`. Only reading holds it; the suite's single ICU locale
  can't tell them apart.
- `is_display_name_conflict` re-raising every *other* IntegrityError. Read only. Without it,
  an email race in `provision_user` would loop forever over the endless `candidates()`. The
  positive half is pinned by the rename-race tests, which would answer 500 if the constraint
  name were wrong.
- The migration's `LOCK TABLE` and the `version`/`updated_at` bump on renamed rows. Read only.
- `completeSignIn` clearing the return path on each failure branch. Read only: each of the
  three branches calls `returnTo.clear()`.

## Left for the human

- Findings 2 and 3 above, both minor. Each wants a red test from the test pair before the fix.
- The ProfileSection field error stays after the user edits the field, until the next save.
  Cosmetic.
- The first real run on the Compose stack, as the green report lists, including a 0002
  upgrade over seeded duplicates and the rolling-deploy window the migration docstring names.
- 12/24-hour rendering in a non-en locale (e.g. `ja-JP`), in the browser.

## Checked and sound

- The 409 body holds `names.TAKEN` only, raised `from None`, so no exception text is returned
  or logged. No display name appears in any log call.
- Saving the name you have compares the exact stored string, so a change of capitals still
  writes. A deleted account gets a 404 before the no-op path.
- `@validates` covers the constructor kwarg in `provision_user`. Nothing writes `display_name`
  through Core.
- The upsert and both migration UPDATEs are bound `text()`. The FK is real, and the index has no
  `deleted_at` filter on purpose (doc 01 §4 says so).
- `/users/me/preferences` is not shadowed by `/users/{id}`.
- `useClock`'s `skipToken` observer is never chosen for a focus refetch. `onFocus` picks an
  observer whose `shouldFetchOnWindowFocus` holds, and `skipToken` makes it disabled.
- No server state in Zustand (`lastChannel` is client state). Vitest reads no `data-testid`.
  The four BDD ids are present.
- Mutants 3, 4, 5, 7 and 8 were caught.
- No test, helper or fixture changed since the test gate except the round-3 seed fix, which the
  test-reviewer approved. Every changed file is in the file map, apart from
  `src/frontend/README.md`, which is a recorded sweep item.
