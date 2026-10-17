# Plan review — gh-3, round 1: changes_requested

The plan is sound and thorough. The stored, Python-computed key closes the app/DB comparison
gap, and the savepoint retry answers the sign-in race. Four major findings remain, all fixable
from the code: two race tests whose stated red is not what the runtime reports; rename
cache-write tests that can't tell the write apart from the refetch that follows it; three races
on state the plan adds that have no answer; and a third soft-delete read exception that is never
recorded in Conventions §3.

## Expectations

Written from the issue, doc 01 §3–§4, doc 06 §3/§5.2/§9, Conventions §3/§4.2/§5.1–§5.4,
register D2/D24/D26/D28, and the code the issue names — before the plan was opened.

### Decisions any plan must make
- E1. **Where the comparison key lives.** A unique index on `lower(display_name)`, a
  `citext`, or an app-computed key column? Postgres `lower()` follows the database's
  LC_CTYPE (postgres:18 image, libc) and is not Python's `lower()`/`casefold()` — which does
  the app use, and how is "the application and the database compare the same way" proven
  (a name the app passes that the index refuses → a 500, not a 409)?
- E2. **Order of trim and NFC**, and is the length counted in code points after both?
  Is the 100 limit checked before or after normalisation (`UpdateUserRequest` checks
  `max_length` on the raw string today)?
- E3. **Default_Ignorable_Code_Point** — Python's `unicodedata` has no such property, and
  no `regex`/ICU package is in the lock. Hand-coded table, or new dependency? Which
  Unicode version, and does it match `unicodedata.unidata_version` for Cn?
- E4. **Is `"   "` / `" "` a 400 from validation (`errors.displayName`)**, and is an
  explicit `displayName: null` kept as today's 400 (the issue's assumption) — checked in code?
- E5. **"Saving the name you already have succeeds and changes nothing"** — does it bump
  `version`/`updated_at` (it does today)? "Changes nothing" read literally says no.
- E6. **Race handling in PATCH**: catch `IntegrityError` → 409, or pre-check + index? The
  index is the only safe arbiter; what maps the violation, and only *that* constraint?
- E7. **First sign-in suffix under a race**: provision flushes inside the callback's
  transaction (commit after `issue_code`); a unique violation aborts the transaction.
  Savepoint and retry? Bounded? How is "first free" computed (scan `X 2…` vs loop)?
  Does a suffix push past 100 chars (`X` of 100 + " 2")? Is the IdP name itself normalised
  and validated (an IdP name with a ZWSP or empty after trim)?
- E8. **Migration**: data step in Python with the same code as Req 1 — imported from the
  `auth` package (packaged migrations) or copied (then it can drift)? An IdP-era name that
  fails Req 1's character rules or exceeds 100 — renamed, kept, or fail the migration?
  Downgrade — one-way; what does `downgrade()` do? Deleted accounts included in "oldest".
- E9. **Preferences**: PATCH body shape (JSON Merge Patch per Conventions §4), `version`
  column use, row created on first PATCH (upsert), validation of every key before any
  write; a PATCH that removes the last key — row kept with `{}`?; does `GET` 404 for a
  deleted account through the same `find_user`?
- E10. **SPA session profile write**: `session.ts` has no setter; a new exported function
  that updates `profile` — and what if a renewal's `adopt()` is in flight with the old name?
- E11. **Directory cache write on success**: `setQueryData` on `directoryKeys.members(ws)`
  only for the active workspace? What if the directory is not cached yet, or a refetch is
  in flight and lands with the old name after the write?
- E12. **Clock delivery** to the three formatters: a hook reading the preferences query,
  or a prop? Optimistic update via `setQueryData` + rollback in `onError`; what renders
  before preferences load (Automatic)? What does `SearchResult` (dateStyle/timeStyle) do
  with `hour12`/`hourCycle` — they conflict with `timeStyle` in some engines?
- E13. **`/settings` while signed out → back on `/settings`**: today `Protected` navigates to
  `/sign-in` and `Callback` always goes to `/`. Does the plan build a return-to, or say the
  assumption fails?
- E14. **"Back to chat" to the last channel** — where is "last channel" known from (it is
  not stored today)? A direct load of `/settings` with no last channel?
- E15. **Settings page layout**: inside `Protected`/`ChatLayout` (sidebar visible) or a full
  page? Is "reads from the server on every visit" `staleTime: 0`/`refetchOnMount: 'always'`?

### Conflicts
- C1. D28 is 🔴 in the register today; Decided already 7 decides it. The plan must record
  it 🟢 in this slice (register, doc 06 §9, ADR) — building on it before the record is
  the issue's own instruction, not a breach.
- C2. Req 2 / Decided already 4 vs Conventions §5.4 and CLAUDE.md's "404 not 403" tenancy
  rule — the 409 leaks existence; recorded as D46 and in Conventions §5.4.
- C3. Req 1 "nothing changes" on invalid vs Req 1 "saving the name you have changes nothing"
  vs today's unconditional `version += 1`.
- C4. Req 5 "author of their own messages at once" vs Decided already 6 / doc 06 §5.2
  "Renames are not covered" — the cache write is the exception, for the renamer's tab only.
- C5. Req 7 "re-renders the tab's times" vs "messages already in the cache… nothing refetches".
- C6. Req 4 one-way data change vs *Stopping for a human* ("drops or rewrites stored data")
  — the issue has decided it; the plan should say so rather than stop.

### Tests that must exist
- Unit (Python): every Req 1 example both sides, NFD José → NFC; length on boundary 100/101
  after trimming; the suffix rule as a pure function (X taken, X 2 taken → X 3; capitals).
- Integration: 409 with exact detail/`errors.displayName` and no other name in the body;
  case-only and NFC-only collisions; own-capitals change; deleted account's name taken;
  concurrent PATCH (two at once — exactly one 200); first sign-in suffix and two at once;
  migration on seeded duplicates incl. ones that collide only after normalisation and
  deleted-oldest; preferences GET/PATCH/merge/null/unknown/bad/{}/404 and "reading never
  creates a row" asserted on the table; two tabs different keys.
- Vitest: Save disabled unchanged *and* invalid (with enabled positive); 400 and 409 on the
  field; "Saved"; session profile and directory both updated; unmount mid-save still
  updates; clock in all three formatters with a fixed locale; revert on failed save.
- BDD: Alan renames, Grace **after a reload** sees "Alan Turing" on his message — needs an
  `alan` fixture; does Alan share a workspace/channel with Grace on the test stack?

### Risks
- R1. Unique violation surfacing as an unhandled `IntegrityError` → 500 in both PATCH and
  the OIDC callback; in the callback, after `issue_code` has stored a code in Redis.
- R2. App/DB comparison mismatch (E1) — a 500 instead of a 409, or a refused sign-in.
- R3. A refetch in flight overwriting the optimistic directory write with the old name.
- R4. `adopt()` on renewal re-reads `/users/me`, so it is fine; but a renewal started
  before the PATCH committed lands with the old name after the session write.
- R5. Existing BDD helpers that rely on names "ada"/"grace" (steps/conftest.py) — a
  scenario that renames must not leave the shared stack broken (KEEP_STACK reruns).
- R6. Migration on a DB with an IdP name over 100 chars or with forbidden chars.
- R7. `toLocaleTimeString` + `hour12`/`hourCycle` in jsdom/Node ICU vs Chromium.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 trim (`str.strip()`), NFC, 1–100, the refused categories + Default_Ignorable, the examples, 400 `errors.displayName`, nothing changes, the same name is a no-op | D13–15, Task 1 (every example, each category on its own, DI ranges outside Cf, both sides of 100), Task 2 `test_users` | covered. DI table checked against DerivedCoreProperties: it matches |
| Req 2 unique across workspaces and deleted accounts, stored form ignoring case, app = DB, 409 wording naming nobody, own capitals, `josé`/`José` | D11, 12 (casefold, **assumed**), 16; Task 2 | covered. Own-capitals test is a weak guard (finding 7) |
| Req 3 `X 2`, `X 3`…, workspace from the result, never refuse, never overwrite | D17–19, Task 2 `test_display_names` | covered, apart from a gap once the retries run out (finding 6) |
| Req 4 migration: same code, oldest kept, suffix rule, one-way | D20–22, Task 1 `dedupe`, Task 2 migration tests | covered. Normalisation-only duplicates are proven at unit level only, which is acceptable because the migration calls `dedupe` |
| Req 5 own tab at once (sidebar + own authors); everyone else on refetch; no broadcast | D5, 31; Task 4 | **misread in the tests**: finding 2. Races: finding 3 |
| Req 6 store: GET `{}`, no row on read, merge, null, 400 `errors.<key>`, 404 deleted | D23–26, Tasks 1, 2 | covered |
| Req 7 clock in all three places, saves at once, revert on failure | D32–34, Task 4 | covered. Server-side order of two saves: finding 3 |
| Req 8 page: prefilled, Save gating, Saved, sections, reached from `current-user`, Back to chat, server on every visit, direct load/reload | D27–30, 35; Tasks 3, 4, 9 | covered |
| *Where the rules meet* 1–7 | Self-review mapping, checked | covered (3: finding 2) |
| *Paths* rows | `SettingsPage.test`, `App.test`, *What no test covers* | covered. Switch mid-save: finding 3 |
| *Assumptions*: `lower()`, only `provision_user` inserts, null is 400, sign-in returns, `hourCycle` | D11, file-map note, D14, Correction 1, D33 | settled. I confirmed null → 400 at `users.py:60-65` and the return-path claim at `App.tsx:63,83` |
| Decided already 1–11 | D1–10 | covered. D4's tenancy exception goes into Conventions §5.4, but the deleted-row read never reaches §3 (finding 4) |
| Tests section (pytest list, Vitest list, one BDD journey + `alan`) | Test approach, Tasks 1–4 | covered |
| Record (register D28/D46, two ADRs, doc 01, doc 06, Conventions §5.4) | Task 11 | covered, apart from Conventions §3 (finding 4) and the README sweep (finding 9) |
| *Not in this issue* | *Not in this plan*, Decided 1 | covered |
| E1 comparison key / E2 order and length / E3 DI table / E4 null & blank | D11–14 | settled |
| E5 no-op / E6 409 mapping by constraint / E7 sign-in race and long names / E8 migration import, bad legacy names, downgrade | D15–22 | settled. Legacy names that fail Req 1: finding 8 |
| E9 merge upsert, `{}` / E12 clock delivery, `hourCycle` with `timeStyle` / E13 return path / E14 last channel / E15 placement, every visit | D24–35 | settled |
| E10 session profile vs `adopt()` in flight · E11 directory not yet cached or a refetch in flight | D31 answers a refetch in flight only | **missing**: finding 3 |
| C1–C6 | D6, D36, Task 11; D3/Task 11; D15; D5/D31; Task 4 clock test; D20 | settled |
| R1 IntegrityError → 500 in the callback | D19 savepoint retry, D16 | settled |

## Findings

### 1. Two race tests are stated to fail on an assertion, but at red they fail earlier — major
**Where:** Task 2, the `test_display_names.py` table, rows 2–3 · **Checked:** the plan's own test
descriptions against `identities.py` today (`rename_user` doesn't exist, and there is no index).
- `test_a_rename_racing_a_first_sign_in` gives its expected red as "assertion: B's user is `"X"`".
  Its first step calls `rename_user(grace, "X")`, which doesn't exist at red, so it fails with
  `AttributeError` before any assertion runs. (It still fails for a good reason, because every
  path needs `rename_user`, but the stated reason is wrong, and the test-reviewer gates on it.)
- `test_two_first_sign_ins_with_one_name` waits for "B seen blocked" by polling
  `pg_stat_activity`. At red there is no unique index, so B never blocks and the poll never
  succeeds. The plan gives the poll no bound, so the red run either hangs or ends in a poll
  timeout — not the stated "`"Sam"` twice" assertion.

**Settled when** each row gives the failure the runtime really reports, and the "seen blocked"
poll has a bound (and a message) that the plan says is the red reason wherever no lock exists
yet.

### 2. The rename's cache-write tests can't tell the write from the refetch after it — major
**Where:** D31, and Task 4's rows "a save updates the sidebar, the directory…" and "a directory
fetch in flight…" · **Checked:** `test/directory.ts` (`scriptDirectory`: `now` is mutable, and
every unscripted call answers it), `useWorkspaceMembers.ts`, `directoryRefresh.ts` (`load` doesn't
dedupe).
D31 calls `setQueriesData` and then `invalidateQueries(['workspace-members'])`, so the stub
answers one more directory fetch after the save. If that stub still answers the old name (as
`auth.members(...)` does), the cache of a correct build ends at the old name and the test fails.
If it answers the new name, a build that only invalidates — the "on next refetch" behaviour
Req 5 keeps for everyone else — passes both tests, and "at once" is never proven. Asserted at an
unpinned moment, the result depends on timing.
**Settled when** the tests say what the post-save directory call answers, and pin the write
itself: for example, hold the post-save refetch and assert the cache already holds the new name
while it is held. The race row has the same problem, and should say which call number it holds
(see finding 3 for call 1).

### 3. Three races on state the plan adds have no answer — major
**Where:** D31, D34, Task 9 `updateProfile` · **Checked:** `session.ts:76-94` (`adopt` sets
`profile` from a `me` fetched before `set`), `:199-212` (a switch adopts too), and TanStack v5's
`invalidateQueries`, which cancels only a fetch that already has data (unverified: no
`node_modules` in either checkout, lock 5.101.4).
- **Session profile.** A renewal (every ~14 min) or a workspace switch whose `me` is answered
  before the PATCH commits, but lands after `updateProfile`, puts the old name back in the
  sidebar until the next renewal. Meanwhile the directory shows the new one — exactly the
  disagreement *Where the rules meet* 3 forbids. The *Paths* row "workspace switch while on
  `/settings`" reaches it directly.
- **Directory not cached yet.** On a direct load of `/settings`, the first directory fetch can
  still be in flight when the save lands. `setQueriesData` has nothing to map, and the invalidate
  joins rather than cancels, so the old name lands.
- **Two clock saves.** D34 keeps the *cache* on the newest choice, but two PATCHes in flight can
  reach the server in the other order. The UI then shows 12-hour while the server stores
  24-hour, and the next visit "reads from the server".

**Settled when** each pair has an answer in the plan, either "harmless because …" or a rule
(for example a mutation `scope`, or `updateProfile` winning over an older `adopt`). Where a rule
is added, it gets a test.

### 4. Reading deleted users is a third soft-delete exception, and Conventions §3 never records it — major
**Where:** Global constraints (the CH009 waiver), D19, Task 11 · **Checked:** Conventions §3:67-84
("Two documented exceptions… A third exception should be a decision with a record, not a local
call", and the contract "wins the tie-break"). Task 11 edits §5.4 only.
The issue decides the behaviour (Req 2, "including deleted accounts"), so building it is right.
But the record the conventions require is missing. A later reviewer would read the waiver as a
local call.
**Settled when** Task 11 adds the exception to Conventions §3 (the name key and the taken-keys
read cover deleted rows, D46) and the D46 register entry names it.

### 5. The return path outlives a failed sign-in — minor
**Where:** D28, Task 9. `takeReturnPath()` runs only when `signedIn`, and the plan doesn't say
whether `signIn` without `returnTo` clears the stored path. A failed sign-in from `/settings`
followed by a plain sign-in later would land on `/settings`. Clear it on the error path (or on
every `signIn`), and test it.

### 6. Sign-in after 10 refused retries — minor
**Where:** D19. The plan doesn't say what happens once the retries run out. Re-raising
contradicts Req 3's "never refuses over a name". Say what happens: unreachable in practice, or a
fallback.

### 7. `test_changing_only_your_own_capitals_is_allowed` is a guard with no positive half — minor
**Where:** Task 2. It passes at red, and the plan says so. Adding Grace sending `"ada"` → 409
after Ada becomes `"ADA"` would make it fail at red and prove that the key was recomputed.

### 8. Legacy names that fail Req 1 can't be saved unchanged — minor
**Where:** D15, D22. The migration keeps names with refused characters, or longer than 100.
For those users `normalise_display_name` returns 400 before the no-op comparison, which
contradicts "saving the name you have succeeds". Say which wins. (Save is disabled when the
value is unchanged, so only a direct API call reaches it.)

### 9. Small inaccuracies — minor
- Task 2: defaulting `a_user`'s name from the email does **not** keep the names apart in
  `test_email_uniqueness_ignores_case`. `ada@…`/`ADA@…` casefold to one key, so the test relies on
  Postgres checking `users_email_key` first. Pass distinct names.
- Task 10's sweep misses `src/frontend/README.md:60-62` ("D28 🔴").
- Decision 31 cites `mutation.ts:246` / `mutationObserver.ts:164`, and decision 16 cites
  `asyncpg.py:789-797`. Neither checkout has the installed source, so these are **unverified**.
  The behaviour they describe matches SQLAlchemy 2.0.51 and TanStack 5.101 as I know them.

## Left for later stages
- Findings 5–9 if the writer leaves them. For the test pair: finding 2's "pin the write, not the
  refetch" applies equally to the clock's "fetches nothing" test (it must anchor its negative
  assertion after the re-render).
- Assumed decisions a human should see at the end: 12 (casefold, `ß` = `ss`), 13 (code points),
  17/22 (dropping refused characters from IdP names; keeping them in legacy names), 28 (return
  path in `sessionStorage`, which extends doc 06 §4's "only the PKCE verifier"), 29, 30, 34.

## Checked and sound
- Header: base `41bcc04` = `main` and `HEAD~1`. Sections and order as the exemplar. 522 lines.
- RED Tasks 1–4 come before GREEN, with the test-reviewer gate. *Found while building* is empty.
  No task commits. Task 12 names `lint unit integration` + `e2e`, with reasons.
- Write scopes: test helpers (`test/api.ts`, both conftests, `chat_page.py`) are all RED work. No
  GREEN task writes a test.
- Ripple: every test that renders `ChatLayout` (`App`, `ChatLayout`×2, `CreateChannelDialog`) gets the
  preferences stub. `SearchPage`/`MessageItem` tests render without the provider, so `null` keeps
  them. Ingress `/api/v1/users` is allowed (`ingress.yaml:50`). No env var. The migration numbers
  follow `0001`. BDD truncation doesn't reach Auth, as stated. `origin/feature/gh-3-run1` exists.
- Corrections 1–2 are true (`App.tsx:63,83`, and `users.display_name` has no index).
- No 🔴 is built on: D28 is decided by the issue and recorded in Task 11.
- BDD: the journey ends with Grace on a fresh load (server state). `Grace sees "{body}" written by
  "{name}"` sits beside `test_message_steps.py:39`'s `…written by Ada` without colliding.
  `alan@collabhub.dev` is in both Dex configs and `testkit.dex`. The shared workspace comes from
  `_signed_in_context`. A `KEEP_STACK` rerun is safe through the disabled-Save path.
- Expected reds otherwise right: `ModuleNotFoundError` for whole-file unit tests, `CommandError …
  '0002'`, the in-test import for the merge race, "is not a function" for `session.ts` additions,
  and `SettingsPage.test` importing only `App` so the file loads.
- Markup vs queries: `aria-label="Display name"` → textbox. `current-user` becomes a Link named by the
  display name. Vitest reads no test id.
- `hourCycle` beside `timeStyle` is allowed by ECMA-402, and the midnight test pins `h23`.
