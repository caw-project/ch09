# Plan review — gh-3, round 1: changes_requested

A strong plan: every Req, *Decided already* item and Test is covered, the library claims check
out against the installed sources, and the expected failures are right. Two majors: the
renamer's own view has unanswered races with fetches already in flight (the plan adds two new
writers to the session profile and the directory cache but answers none of the old writers), and
the new preferences GET reaches existing Vitest files the file map doesn't name.

## Expectations

Written from the issue, doc 01/06, conventions §5.4, register D28/D24/D2, and the code
(`routers/users.py`, `identities.py`, `oidc.py:248-252`, `schemas.py:129-133`,
`shared/problems.py:190-195`, `session.ts`, `WorkspaceSwitcher.tsx`, `useWorkspaceMembers.ts`,
`App.tsx`, `stores/chat.ts`, `ChannelView.tsx:37-38`, the three formatters, Dex test config,
`tests/bdd/steps/conftest.py`) — before the plan was opened.

### Decisions
- E1. Where does the 1–100 limit apply — after trim+NFC as Req 1 says? Today `UpdateUserRequest` has
  `min_length=1, max_length=100` on the raw input, which refuses `"  " + 100 chars` and counts an
  NFD `José` as 5. Counted in code points (Python `len`) or UTF-16 units (JS `length`)?
- E2. `Default_Ignorable_Code_Point` is not exposed by Python's `unicodedata`. Where does the set
  come from, which Unicode version, and is `Cn` judged by the Python runtime's `unicodedata`
  version? Does the SPA's "invalid" check (Req 8 Save disabled) use the same rule, and what
  happens where JS `\p{…}` and Python disagree (e.g. a newly assigned code point)?
- E3. How are uniqueness and its race enforced — a unique index on `lower(display_name)`
  (issue's assumption), and does the app pre-check? Does Python `str.lower()` vs Postgres
  `lower()` (libc ctype of the DB) ever disagree (`İ`, `ẞ`, final sigma), and does that matter
  to "the application and the database compare the same way"? What is the DB's ctype on
  `postgres:18` in Compose, testcontainers and the deps chart?
- E4. How is the IntegrityError mapped to 409 — and only for the name index, not any constraint?
- E5. "Saving the name you already have succeeds and changes nothing" — does `version`/`updated_at`
  still bump (today they always do)? Is a capitals-only change "the name you already have"?
- E6. Req 3: what does first sign-in do with an IdP name that is invalid under Req 1 (empty after
  trim, >100, a Cf char), and with `X` near 100 chars where `X 2` exceeds 100? Sign-in "never
  refuses".
- E7. Req 3 race: two first sign-ins named "X" — the losing INSERT aborts the transaction; savepoint
  and retry, or lock? And the rename-vs-sign-in race (Where the rules meet #2).
- E8. Req 4: order and tie-break when two accounts share `created_at`; a suffixed name colliding
  with an existing `X 2`; stored names that become invalid (empty, >100, forbidden chars) after
  trim+NFC; does the migration import live app code ("same code as Req 1"); downgrade?
- E9. Req 6: merge done atomically in SQL (jsonb `||`, upsert) or read-modify-write? First PATCH
  from two tabs at once (insert race)? What is `version` for? A non-object body, `{}`, all keys
  removed — row kept? What does PATCH return?
- E10. Req 7: `hour12` or `hourCycle` (`hour12:false` historically gave `24:05` at midnight in
  some engines)? Combined with `timeStyle` in `SearchResult`? Where does the clock come from in the
  three components — one TanStack query key (global, not per workspace)?
- E11. Req 7 optimistic save: cancel an in-flight preferences refetch; two quick choices where the
  first fails — what does "the previous choice" mean then?
- E12. Req 8 "Back to chat" to "the last channel": `activeChannelId` is cleared on ChannelView
  unmount — where is the last channel kept, and what on a direct load of `/settings`?
- E13. Req 8 / Paths: signed out on `/settings` → back on `/settings`. Today `Protected` sends to
  `/sign-in` and `Callback` navigates to `/` — build return-to, or say it doesn't (issue's
  assumption)?
- E14. Req 8 "reads the profile and preferences from the server on every visit" — a query that
  refetches on mount regardless of staleTime, not `session.profile`?
- E15. Req 8 "disabled while the value is unchanged" — unchanged compared raw, trimmed, or
  normalised? Is `current-user` turned into a link/button keeping its test id?
- E16. Req 5: how does the session profile get updated (new export on `session.ts`), and the
  directory cache — only `members(activeWs)` or every `['workspace-members', *]` key (another
  workspace's cached directory shows the old author name after a switch)?

### Conflicts
- C1. Req 8 "Save disabled while unchanged" against Tests' BDD "renaming to the name he already has
  is a no-op, so a KEEP_STACK rerun still passes" — on a rerun Alan's field is prefilled "Alan
  Turing", so Save is disabled and the step can't click it.
- C2. Req 2 / Decided 4 (global uniqueness, a 409 revealing a name in another workspace) against
  conventions §5.4 and the 404-not-403 rule — recorded as the D46 exception?
- C3. D28 is 🔴 in the register; the issue decides it (Decided 7). Plan records the register,
  doc 06 §9 and ADR in this slice?
- C4. Req 1 "1–100 after trimming" against the existing pydantic constraint on raw input.

### Tests
- T1. Every Req 1 example both sides, unit-level; NFC collision; capitals-only own rename; deleted
  account's name still taken; concurrent rename (two real connections); concurrent first sign-ins;
  migration with duplicates appearing only after normalisation and an existing `X 2`; prefs
  merge / null / unknown / bad value / `{}` no row (and no row created) / 404 deleted.
- T2. Vitest: form disabled states (unchanged and invalid each alone), 400 and 409 on the field,
  "Saved"; profile + directory updated on success, including after unmount; clock in all three
  formatters both ways; revert on failure.
- T3. BDD: Alan renames; Grace reloads and sees "Alan Turing" on Alan's message; `alan` fixtures.
- T4. Existing tests the change breaks: `MessageItem.test.tsx:53` computes the expected time;
  `test_users.py` cases on raw-length validation; BDD harness constants.

### Risks
- R1. IntegrityError text carries the name (`Key (lower(display_name))=(sam)`) — reaching the
  `_unhandled` logger would log PII (CH008, Decided 11).
- R2. A renewal's `adopt()` in flight during a rename returns the pre-rename `me` and overwrites the
  session profile with the old name.
- R3. The unmount-mid-save path relies on TanStack `useMutation` hook-level callbacks running
  after unmount — check the installed version.
- R4. Migration on a real DB: renaming duplicates also changes nothing about workspaces' names;
  one-way, so ordering of index creation vs data fix inside one transaction.
- R5. Preferences query refetch-on-focus overwriting an optimistic choice mid-save.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 rename yourself: trim, NFC, 1–100 after, refused categories + DICP, the 5 refused / 5 accepted examples, 400 `errors.displayName`, same name no-op | D3, D23, D24, Corr. 4; T1 unit (each example, each category, DICP apart, both sides of 100), T2 integration | covered |
| Req 2 unique everywhere, case-insensitive on stored form, deleted included, 409 naming nobody, own capitals, `josé`/`José` | D14–17; T2 409, NFC, capitals, deleted, two races both orders; schema test | covered (D15 casefold **assumed**, defensible) |
| Req 3 first sign-in suffix, workspace from result, never refuses/overwrites | D18–20; T1 `candidates`/`from_idp`; T2 four sign-in tests incl. two at once | covered |
| Req 4 migration: trim/NFC with Req 1's code, oldest keeps, Req 3 suffix, one-way | D21–22; T1 `dedupe`; T2 `test_migration_0002` | covered |
| Req 5 own tab at once (sidebar + own authors); others on next refetch; no broadcast | D31–32; T3 `useProfile` | misread in part — see F1 (in-flight fetches), F7 (second tab's sidebar) |
| Req 6 prefs store: `{}` no row, merge, null, 400 `errors.<key>`, 404 deleted | D25–27; T1, T2 route + merge files | covered |
| Req 7 clock in three formatters, saves at once, revert on failure | D29–30; T3 time, three components, revert both orders | covered; F3 minor |
| Req 8 page: prefill, Save disabled unchanged/invalid, Saved, clock radios, via `current-user`, Back to chat, fresh read, direct load | D33–36; T3 SettingsPage, App | covered |
| Decided 1–3, 5, 6, 8, 10, 11 | D1–13 | covered |
| Decided 4 / D46 vs Conventions §5.4 and the 404 rule (C2) | Global constraints; Task 9 §5.4 exception | settled |
| Decided 7 / D28 🔴 in the register (C3) | D9, D38; Task 9 register, ADR, doc 06 §9 | settled |
| Decided 9 fail-open | D11 | covered |
| Tests — pytest list, Vitest list, one BDD journey + `alan` fixtures | Test approach, Tasks 1–4 | covered |
| Record — register D28/D46, two ADRs, doc 01, doc 06, conventions §5.4 | Task 9 | covered |
| Not in this issue | *Not in this plan* | covered |
| Assumptions 1–5 (lower(), only `provision_user`, null 400, return path, hourCycle) | Corr. 1–3, D35, time tests + *what no test covers* | settled, each checked |
| E1 length after normalise, code points (C4) | D23, Corr. 4 | settled; F8 for the SPA's count |
| E2 DICP table / Unicode version | Task 1 table (matches UCD 15.0, checked); Cn version in *what no test covers* | settled |
| E3 index vs `lower()` | D14–15 | settled |
| E4 IntegrityError → 409 only for the name index | D17 | settled |
| E5 same name no-op / capitals | D24 | settled; F5 minor |
| E6 invalid / long IdP name | D19–20 | settled; F6 minor |
| E7 sign-in races | D18 | settled |
| E8 migration ties, held suffixes, invalid stored names | D21–22 | settled |
| E9 atomic merge, upsert race, version, empty | D25–27 | settled |
| E10 `hourCycle`, one query key | D28–29 | settled |
| E11 optimistic ordering, in-flight refetch | D30 | partly — F1, F3 |
| E12 last channel | D34 | settled |
| E13 return-to after sign-in | D35, Corr. 2 | settled |
| E14 fresh read on every visit | Task 3 `isFetchedAfterMount`, `fresh` | settled |
| E15 "unchanged" reading; `current-user` link | T3 `" ada "` disabled; D33 | settled in a test only — minor, under F4 |
| E16 how session + directory caches are written | D31–32 | settled; F1 for the races |
| C1 Req 8 disabled-when-unchanged vs the BDD KEEP_STACK no-op rerun | Task 4 `rename_to` returns when Save is disabled | settled in a task, not a row — F4 |
| T4 existing tests broken | `test_schema.py`, `MessageItem.test.tsx` named | missing — F2 |
| R1 PII in IntegrityError logs | Global constraints, D17 re-raise of others only | settled |
| R2 renewal `adopt()` vs rename | — | missing — F1 |
| R3 hook-level `onSuccess` after unmount | D31 (checked) | settled |
| R5 prefs refetch vs optimistic | — | missing — F1 |

## Findings

### 1. The renamer's own view races fetches already in flight — major
**Where:** Decisions 30–32, Task 8 · **Checked:** `session.ts:76-94` (`adopt` re-reads `me` on
every renewal and switch), `useWorkspaceMembers.ts` (refetch on focus, reconnect, unknown id),
the plan's text for `cancelQueries`/invalidation (none).
The plan adds a writer to `session.profile` (`updateProfile`) and to every
`['workspace-members', *]` entry (`applyRename`), and an optimistic writer to `['preferences']`,
but answers none of the existing writers of the same state:
- a renewal or workspace switch whose `GET /users/me` was answered before the rename committed,
  landing after `updateProfile`, puts the old name back in the sidebar for up to 15 minutes;
- a directory fetch in flight (focus, reconnect, an unknown id) landing after `applyRename` puts
  the old name back on the renamer's own messages until the next refetch — and the two together
  break *Where the rules meet* 3, "the sidebar and their own message authors never disagree";
- a `['preferences']` focus refetch in flight during a clock choice lands the old value over the
  optimistic one (and, if `onSuccess` doesn't write the response, leaves it there).
Each pair needs an answer in the plan — cancel the queries before writing, invalidate after the
write, guard `adopt`, or a row accepting the window with its reason — and the ones it fixes need a
Vitest test that holds the fetch (`auth.membersBy` can already return a promise) and proves the
new name survives.

### 2. The new preferences GET reaches tests the file map doesn't name — major
**Where:** Decision 28–29, Task 8 (`ChatLayout` primes with `usePreferences`), file map ·
**Checked:** `test/setup.ts:32` (`onUnhandledRequest: 'error'`), msw
`lib/core/utils/request/onUnhandledRequest.mjs:19-25` (throws `InternalError`), stubs are per test
(`test/api.ts:312`); `ChatLayout.attachments.test.tsx:78-82`, `CreateChannelDialog.test.tsx:104-114`
mount `ChatLayout` signed in; `ChatLayout.test.tsx` and `App.test.tsx` are in the map only for
new tests. Whether each existing test then fails outright or only logs and retries is
**unverified**.
After Task 8 every signed-in mount of `ChatLayout` (and of `MessageItem`/`ThreadSummary`/
`SearchResult`, if `useClock` fetches — the plan doesn't say whether it does) sends a GET nothing
stubs. The code-writer can't add the stub — it may not write a test. The plan should say whether
`useClock` only reads the cache or fetches, and give the RED task every existing file that will
now send the GET (a stub in each setup, or one default in `test/api.ts`), as the exemplar's
*Known ripple* asks.

### 3. Two failed clock saves leave a choice the server never held — minor
**Where:** Decision 30 · **Checked:** `mutation.js:88-115` (scope wait after `onMutate`).
From Automatic: 24h (held) then 12h; both fail. 24h's failure doesn't revert (cache holds 12h);
12h's failure reverts to its snapshot, 24h — never saved. An invalidate on error, or reverting to
the last *confirmed* value, settles it.

### 4. Req 8 vs the BDD rerun is settled in a page object, not a decision row — minor
**Where:** Task 4, `SettingsPage.rename_to` · **Checked:** issue Req 8 and *Tests*.
The handling is right (a fresh stack still fails at `Alan sees his name as`), but the conflict
belongs in a row so the test pair see it was chosen. Same for the reading of "unchanged" (compared
after trim + NFC, pinned by the `" ada "` test).

### 5. "Same stored form → return without writing" must not drop an `avatarAsset` — minor
**Where:** Decision 24, Task 6 · **Checked:** `routers/users.py:59-71`.
A PATCH carrying the unchanged name and a new avatar would lose the avatar if the early return is
taken literally. Scope the no-op to the name.

### 6. `from_idp` can return a non-NFC name — minor
**Where:** Decision 19 · **Checked:** reasoning — `e` + U+034F + U+0301 stays decomposed under
NFC (CGJ blocks composition); dropping the CGJ afterwards leaves `e` + U+0301. Normalise again
after dropping.

### 7. The renamer's second tab: sidebar vs authors — minor
**Where:** Paths row 6, Decision 32 · **Checked:** `session.ts:76-94`, `WorkspaceSwitcher.tsx:26`.
In another tab the authors update on the directory refetch, but `current-user` only on the next
renewal or reload. Defensible, but say so as an **assumed** row.

### 8. The SPA counts length in UTF-16 units — minor
**Where:** Decision 36 · **Checked:** Corr. 4 (server counts code points).
`s.length` disables Save for astral-plane names of 51–100 code points the server accepts; say
`[...s].length`.

### 9. `service_database` can't run inside an async test — minor
**Where:** Task 2, `test_migration_0002.py` · **Checked:** `testkit/databases.py:36-49`
(`asyncio.run`). Call it from a sync fixture, then `await upgrade_to(dsn, "head")` in the test.

## Left for later stages
Findings 3–9 if the writer keeps its text. For the code-writer: Task 10's
`docker compose up` first real run is the human's under its own agent file — it is the exemplar's
wording, not a finding.

## Checked and sound
- Base `b5f3ffd` is HEAD's parent (HEAD is the plan's own commit); 576 lines; RED 1–4 before
  GREEN; no task commits; *Found while building* empty; no 🔴 built on (D28 decided by the issue).
- SQLAlchemy asyncpg re-raise `from error` at `asyncpg.py:791-797` (installed); TanStack
  `onMutate` before the scope wait and hook-level `onSuccess` at `mutation.js:94-123`,
  `mutateOptions` only with listeners at `mutationObserver.js:77` (installed).
- DEFAULT_IGNORABLE table matches UCD 15.0 `DerivedCoreProperties.txt`.
- Corrections 2 and 3 true (`App.tsx:63,83`; `users.py:61-65`; only `User(` in `identities.py:101`
  and `test_schema.py:22`). `activeChannelId` cleared at `ChannelView.tsx:38`.
- Ingress `/api/v1/users` at `ingress.yaml:50`; `TRUNCATE … CASCADE` at `testkit/db.py:27`; auth
  conftest `TABLES` at line 34; no env var, chart or Compose change needed.
- Expected reds: `ModuleNotFoundError`/`ImportError` cases are whole-file and every test needs the
  module; a missing route's 404 has no `detail` (`problems.py:197-210`); "passes at red" guards
  each carry their positive.
- `ProblemException.conflict(..., errors=)` passes through (`problems.py:55-76`).
- Record task covers register, both ADRs, docs 00/01/06, vocabulary, stale docstrings; verification
  names `lint unit integration` and `e2e`.
