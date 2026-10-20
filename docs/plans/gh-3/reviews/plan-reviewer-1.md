# Plan review — gh-3, round 1: changes_requested

A strong plan: every requirement, *Decided already* item, *Paths* row and *Where the rules meet* row
is met by a named test at the right layer, and the claims I checked (library source, line numbers,
fixtures, step phrases, ingress, truncation) hold. Two major findings remain, both in SPA races the
plan adds itself: decision 17's settle rule leaves the clock on the **older** choice when two saves
are answered in reverse order, which its own test pins; and decision 35 leaves a renewal able to
put the old name back in the sidebar, which the issue says must never happen.

## Expectations

Written from the issue, doc 01 §3–§4, doc 06 §5.2, Conventions §5, register D24/D26/D28, and
the code the issue names — before the plan was opened.

### Decisions any plan must make

- E1. **Where Req 1's 1–100 limit is checked.** `UpdateUserRequest.display_name` has
  `max_length=100, min_length=1` (schemas.py:132), which pydantic applies to the *raw* string. Req 1
  says the length is counted after trim and NFC. Is a 101-char raw input that is 100 after trimming,
  or an NFD `e`+U+0301 name at 101 code points that is 100 after NFC, accepted? Is the pydantic
  limit moved after normalisation?
- E2. **How the application and the database compare "the same way" (Req 2).** A Python pre-check
  (`str.lower()`/`casefold()`) beside a Postgres `lower()` index can disagree (`ß`, `İ`, the DB's
  `LC_CTYPE` — `postgres:18` official image, en_US.utf8; `lower()` under libc is per-character
  `towlower`). Does the plan rely on the index alone (catching the violation), or store a key
  column computed once in Python, or use PG 18 `casefold()`? And "the plan says whether lower()
  not being full case folding matters" (issue's assumption) — answered?
- E3. **Telling a name collision from any other `IntegrityError`** — `users.email` is also unique;
  which constraint name does the 409 / the suffix retry key on?
- E4. **What sign-in does with an IdP name Req 1 would refuse** — empty after trim, over 100, or
  holding Cf/default-ignorable characters. "Sign-in never refuses over a name" (Req 3): sanitised,
  replaced by the next fallback (`preferred_username`, email local part), or stored as is? Is the IdP
  name trimmed/NFC'd before the uniqueness check?
- E5. **Suffix pushing past 100**: `X` of 99–100 chars, then `X 2` is 101–102 — truncate the base?
- E6. **What the migration does with a stored name that Req 1 would refuse** (empty after trim, a
  zero-width char): left, fixed, or a CHECK constraint added? Req 4 says only trim+NFC+rename.
- E7. **Migration code reuse**: "the same code as Req 1" — does the migration import the app's
  normaliser (so a later change to it silently changes a historical migration), or copy it?
- E8. **Explicit `displayName: null`** — the issue says keep what the code does: code raises a 400
  (users.py:61–65, test_users.py:101). Kept?
- E9. **The "Saved"-and-no-op rule**: saving the name you already have "changes nothing" — does it
  still bump `version`/`updated_at` (today every PATCH does, users.py:73–74)? Changing only your
  own capitals must pass the unique index (own row) — how?
- E10. **Sign-in return route (issue assumption)**: `Protected` sends a signed-out user to
  `/sign-in` with no return path, and both `SignIn` and `Callback` go to `/` (App.tsx:26, 63, 83).
  So the path "`/settings` while signed out → back on `/settings`" is not met today. Does the plan
  say so and either build it (through the IdP redirect — needs storage) or record not building it?
- E11. **"Back to chat" to the last channel**: `ChannelView` clears `activeChannelId` on unmount
  (ChannelView.tsx:37–38), so it is null on `/settings`. Where does "last channel" come from, and
  where does the link go on a direct load with no last channel?
- E12. **Is `/settings` inside `ChatLayout`** (sidebar, socket) or a page of its own? Clicking
  `current-user` must reach it; does the sidebar stay?
- E13. **Preferences query key** — per user, not per workspace (Req 6, path "workspace switch →
  nothing changes"), against D24's "query keys carry the workspace id". Decision row?
- E14. **"Reads from the server on every visit"** vs TanStack cache: `staleTime 0`/`refetchOnMount
  'always'`, and does the form render before the fetch lands (cached copy) or wait?
- E15. **How the clock reaches three formatters** — a hook in each, a prop, or a context; and the
  12h/24h options (`hour12` vs `hourCycle: 'h23'` — `hour12:false` has given `24:05` in some ICU
  builds). SearchResult uses `dateStyle/timeStyle` — `hourCycle` is allowed with those.
- E16. **Optimistic clock**: "re-renders at once" then revert on failure — `onMutate` with
  `setQueryData` and rollback; what if two choices are made before the first settles?
- E17. **PATCH preferences concurrency** (two tabs, different keys both survive): a
  read-modify-write in Python loses one unless the row is locked or the merge is done in SQL
  (`prefs || :patch`, `- key`). First PATCH with no row: two concurrent inserts — `ON CONFLICT`?
  What does `version` do?
- E18. **Preferences validation shape**: unknown key and bad value → 400 `errors.<key>`; is the
  body a free JSON object or a pydantic model with `extra=forbid`? Empty body `{}`? Non-object?

### Conflicts in the issue

- C1. **Req 2 / Decided 4 (global uniqueness) against Conventions §5.4 + CLAUDE.md "a resource the
  caller may not see is 404"** — the issue resolves it (D46) and asks for the conventions doc to
  record the exception. Does the record task do it in this slice?
- C2. **Req 5 "author of their own messages at once"** against Decided 6 / doc 06 "Renames are not
  covered": the renamer's directory cache is written — for which workspaces' caches (the user is in
  several; `directoryKeys.members(ws)`)?
- C3. **Req 1 "1–100 characters"** — characters = code points? graphemes? UTF-16 units in the SPA
  validator (JS `.length`) vs Python `len()` for astral chars (`😀` is 2 in JS, 1 in Python). Does the
  SPA's "invalid" disable rule agree with the server?
- C4. **D28 🔴 → 🟢 in this slice**: the plan builds on it only because the issue decides it; the
  register row and ADR must be written in the same slice.

### Tests that must exist

- T1. Unit: the normaliser over every Req 1 example, both sides (5 refused, 6 accepted, NFD José
  stored precomposed, inner double space kept); the 100/101 boundary *after* trimming.
- T2. Integration: 409 + body naming nobody (assert `detail` and absence of other user/workspace);
  case-insensitive; NFC-only collision; own capitals; deleted account's name still taken; same name
  → 200 no change; concurrent rename (two real concurrent transactions, not sequential).
- T3. Integration: first sign-in suffix `X 2`, `X 3` (with `X 2` taken already, gap skipped), the
  workspace named from the result; two first sign-ins at once; rename racing sign-in.
- T4. Integration: the migration from 0001 with seeded duplicates — including ones equal only after
  NFC/trim/case, oldest by `created_at` kept, a suffix candidate already taken. Needs a DB at
  revision 0001 — no helper exists (`auth/migrations.py` only has `upgrade_to_head`).
- T5. Integration: preferences GET `{}` without creating a row; PATCH merge; `null` removes;
  unknown key; bad value; nothing changed after a 400; 404 deleted; two different keys concurrently.
- T6. Vitest: form disabled unchanged/invalid; 400/409 on field; "Saved"; session profile *and*
  directory updated; unmount mid-save still updates both; clock in all three formatters; revert.
- T7. BDD: Alan → "Alan Turing", Grace reload sees it; `alan` context + page fixture.

### Risks

- R1. **Renewal racing a rename**: `adopt()` re-reads `me()`; a renewal whose `me()` was answered
  before the PATCH commits and lands after the rename's session write puts the old name back.
- R2. **Directory fetch in flight** when the rename writes the cache — lands after and restores the
  old name unless cancelled first.
- R3. **Unmount mid-save**: per-call `mutate(…, {onSuccess})` callbacks don't run after the
  observer unmounts in TanStack v5; hook-level options do. Which does the plan use?
- R4. **First sign-in transaction**: the callback commits only at the end (federation.py:212); a
  unique violation on flush aborts the whole Postgres transaction — a retry needs a SAVEPOINT, and
  the second sign-in blocks on the first's uncommitted index entry while it does Redis work.
- R5. **Existing tests the index weakens**: `test_schema.py` inserts every user as "Ada Lovelace" —
  `test_email_uniqueness_ignores_case` will raise `IntegrityError` for the name, not the email, and
  still pass, proving nothing. RED work. Auth conftest `TABLES` must include `user_preferences`.
- R6. **BDD's Auth data survives** between scenarios and runs; the acceptance renames Ada and back.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 trim (`str.strip()`), NFC, 1–100 after normalising, the refused categories + DI, every example both sides, 400 `errors.displayName`, nothing changes, same name succeeds | Tasks 1, 2, 5, 7; decisions 23, 29; length bound moved after normalising (Task 7) | covered |
| Req 2 unique on stored form ignoring case, app and DB compare the same way, all workspaces, deleted included, 409 text naming nobody, own capitals, `josé`/`José` either typing | decisions 11–13; Task 2 `test_a_taken_name…`, `…normalisation_collide_both_ways`, `…capitals`, `…deleted…`, `…cannot_see…`, race | covered |
| Req 3 first free `X 2`, `X 3`…; workspace from the result; never refuses; never overwrites | decisions 14, 24, 25; Task 2 suffix, returning, two-at-once, both race orders | covered |
| Req 4 trim+NFC with Req 1's code, rename all but the oldest (`created_at`), suffix rule, one-way | decisions 26, 27; Task 6 migration; Task 2 `test_name_migration.py` | covered |
| Req 5 own tab at once (sidebar + own messages); others on next refetch; no broadcast | decision 16; ProfileSection + App tests; journey | covered — but see finding 2 |
| Req 6 Auth owns, one row per user, GET `{}` creating none, PATCH merge, `null` removes, 400 `errors.<key>` nothing changes, 404 deleted | decisions 15, 18, 30; Task 2 `test_preferences.py` | covered |
| Req 7 `clock` 12h/24h/absent; three formatters; saves at once; re-renders; failed save reverts + error | decisions 17, 19, 20; `time.test.ts`, `clockSites`, PreferencesSection | **misread in one ordering** — finding 1 |
| Req 8 page, Profile (prefill, Save disabled unchanged/invalid, Saved), Preferences, reached from `current-user`, Back to chat, server on every visit, direct load/reload | decisions 21, 28, 31, 32; App.test, ProfileSection | covered (decision 28 recorded: character rules server-only) |
| *Where the rules meet* — concurrency, rename vs sign-in, own view, token, workspace name, cached lists, two tabs | Task 2/3 tests named per row | covered; own-view row — finding 2 |
| *Paths* — all eight rows | App.test, PreferencesSection focus, `test_a_deleted_*`; row 7 existing tests + journey | covered |
| DA 1–11 | decisions 1–10, R1 test (DA 9), CH008 constraint (DA 11) | covered |
| *Tests* — pytest list, Vitest list, one journey with `alan` | Tasks 1–4 | covered |
| *Record* — D28 🟢, D46, two ADRs, doc 01 §3/§4/suffix, doc 06 §3/§5.2/§9, Conventions §5.4 | Task 9 | covered |
| *Not in this issue* | *Not in this plan* | covered |
| *Assumptions* 1–5 | Corrections 1–4, decision 20, *what no test covers* | settled |
| E1 length after normalising · E2 compare the same way · E3 which constraint | Task 7 drops `Field` bounds; decision 11–12 key column; `constraint_name` | settled |
| E4 invalid IdP name · E5 suffix past 100 · E6 bad stored names · E7 migration reuses `auth.names` | decisions 24, 25, 26; global constraints | settled (assumed, recorded) |
| E8 null → 400 · E9 same name / own capitals | Correction 3; decision 23; key on own row | settled |
| E10 return route · E11 last channel · E12 inside ChatLayout | Correction 1 + decision 34; decision 32; decision 21 | settled |
| E13 prefs key not per workspace · E14 server on every visit | decision 18; `refetchOnMount: 'always'` | settled; prefill on revisit — minor 3 |
| E15 formatters, `hourCycle` · E16 optimistic clock · E17 concurrent prefs · E18 prefs body | decisions 19, 20; 17; 15; 30 | E16 — finding 1; rest settled |
| C1 D46 vs §5.4 · C2 which directories · C3 code points JS/Python · C4 D28 record | Task 9; decision 16 "every cached"; `[...s].length`; Task 9 | settled |
| T1–T7 | Tasks 1–4 | covered |
| R1 renewal racing a rename | decision 35 — **assumed, not handled** | finding 2 |
| R2 in-flight directory fetch · R3 unmount mid-save · R4 SAVEPOINT · R5 `test_schema.py` · R6 KEEP_STACK | decisions 16, 14; file map; Correction 5 | settled |

## Findings

### 1. The clock's settle rule ends on the older choice when answers arrive in reverse — major
**Where:** Decisions row 17; Task 3 `PreferencesSection.test.tsx` "two choices answered in reverse
order end on the last". **Checked:** `@tanstack/query-core` 5.101.4 in the primary checkout,
`build/modern/mutation.js:102-144` and `mutationObserver.js:75-99`.

The rule is: `onSuccess`/`onError` write the response / restore the snapshot only when no other
preferences mutation is pending. Trace it with A = 12h then B = 24h, answered B first: B settles
while A is pending → B skips. A settles with nothing else pending → A writes **its own response,
`{clock: '12h'}`**. The tab ends on 12-hour while the user's last choice was 24-hour (and, if the
server applied them in sent order, while the server holds 24h). The plan's own reverse-order test
would fail against the design as written, so the code-writer would have to depart from a decision
row to pass it. Also, as the installed source shows, a mutation's `options.onSuccess` runs at
`mutation.js:123` *before* it dispatches `success` at `:144`, so it still counts itself in
`isMutating` — "no other pending" is a count of 1, not 0; worth saying so the build doesn't read it
as `=== 0` and never write.

**Settled when** the decision row gives a settle rule that ends on the last choice in both orders —
e.g. the last mutation to settle refetches (or invalidates) instead of writing its own response, or
only the most recently *started* mutation's result is written — and says how the failure path
restores "the previous choice" when an earlier save is still in flight.

### 2. A renewal can still put the old name back in the sidebar — major
**Where:** Decisions row 35; *What no test covers*; *Not in this plan*. **Checked:** `session.ts:76-94`
(`adopt` fetches `me()` then `set`s the whole session), `:122-138` (renewal), `:199-212`
(`changeWorkspace`); issue *Where the rules meet*, row 3.

The issue says the success updates the session profile and the directory "so the sidebar and their
own message authors **never disagree**". Row 35 accepts that a renewal (or a workspace switch —
`changeWorkspace` runs the same `adopt`, and *Paths* has a switch on `/settings`) whose `GET
/users/me` was answered before the rename committed lands after `updateProfile` and shows the old
name in the sidebar beside the new name on the user's messages — for up to ~14 minutes. That is a
recorded assumption that covers less than the issue's words, so it is a finding. The reason given,
"D38 territory", doesn't hold: D38 is about whether a network-failed renewal signs out; nothing in
it governs which profile wins. The fix is small and inside `session.ts`, which the plan already
changes (e.g. `updateProfile` bumps a counter that `adopt` captures before its `me()` and checks
before `set`, keeping the newer profile), and the harness can hold the `me()` reply the way
`scriptDirectory().hold` does for the directory.

**Settled when** the plan handles both orders (renewal's `me()` answered before / after the PATCH
commits) with a `session.test.ts` case for each, or argues from the issue why the sidebar
disagreeing is acceptable.

### 3. Profile prefill on a revisit can come from the cache — minor
**Where:** Interfaces `useProfile … refetchOnMount 'always'`; ProfileSection "prefills from the
server, not the session's copy". **Checked:** reading. On a direct load or reload the cache is empty,
so *Paths* row 1 holds. On a second visit in the same tab the cached `['profile','me']` renders at
once and the refetch follows; if the form copies its initial value once, a rename made on another
device shows the stale name in the field. Left for the test and code pair: say whether the field
waits for the fetch or follows it until edited.

### 4. Old Auth pods during a rolling deploy — minor
**Where:** Task 6 migration. **Checked:** `charts/collabhub/templates/auth/migrate-job.yaml:16`
(`pre-install,pre-upgrade` hook). After 0002 commits, pods still running the 0001 code insert
`users` rows with no `display_name_key` (NOT NULL) — a first sign-in fails until they are replaced —
and an old pod's `PATCH /users/me` would write a name without updating its key. Short-lived and
unused by today's SPA; worth a line in the migration's docstring or *Found while building*.

## Left for later stages

- Finding 3 (profile prefill on a revisit) — test and code pair.
- Finding 4 (rolling-deploy window) — code-writer and acceptance-reviewer, who deploy a preview with
  existing data.
- The plan quotes invisible characters literally (Task 1, line 222: U+200B, U+3164, U+034F, U+00A0);
  the test-writer should write them as `\u` escapes so a reader can see them.
- Doc 01 §4 should say the uniqueness counts deleted rows on purpose (Conventions §3's soft-delete
  rule), so a later `deleted_at` filter isn't "fixed" in.
- `directoryRefresh.ts`'s `load` keeps running after `cancelQueries` (the queryFn passes no signal);
  its bookkeeping stays sound (a newcomer is re-seen and refetched), but the code-reviewer should
  look at decision 16 against it.

## Checked and sound

- Base commit `2f1cc69` is `main` (`git worktree list`); baseline 1863 unit / Auth 59 matches
  `docs/test-report.md` at `1accafe`.
- Hook-level `onSuccess` runs from the `Mutation`, per-`mutate` only with listeners —
  `mutation.js:123`, `mutationObserver.js:77`; `skipToken` exported (`index.d.ts:34`); 5.101.4.
- `IntegrityError.orig.__cause__` is the asyncpg error — `sqlalchemy/dialects/postgresql/asyncpg.py:797`
  (`raise translated_error from error`), so `constraint_name` is reachable.
- Default_Ignorable ranges match Unicode 15.0's `DerivedCoreProperties.txt`; U+0600 is Cf-not-DI,
  U+3164/U+034F/U+FE0F/U+115F DI-not-Cf.
- `TRUNCATE … CASCADE` (`testkit/db.py:27`) reaches `user_preferences`; BDD truncation never touches
  Auth; `/api/v1/users` already in `ingress.yaml:50`; router registration at `main.py:119`.
- `test_schema.py` ripple caught (every user "Ada Lovelace"); `setupServer()` has no default handlers,
  so the default preferences stub is needed; every component test uses `renderWithProviders`, so
  `useClock` has a `QueryClient`.
- Corrections 1, 3, 4 confirmed: `App.tsx:26,63,83`; `users.py:61-65` + `test_users.py:101`; only
  `identities.py:101` and `test_schema.py:22` construct `User`.
- Cited helpers exist: `ProblemError.fieldError`, `scriptDirectory().hold`, `setPageAttention`
  (bubbling `visibilitychange`), `session.test.ts:315` location stub, `vi.resetModules` at
  `App.test.tsx:56`/`session.test.ts:51`, `_signed_in_context`, `_restore`, `send_message_and_wait`,
  `has_author` (`chat_page.py:256`), `delete_account` (`test_deleted_accounts.py:29`), `r1_down`.
- Step phrases reuse conftest's verbatim; `written by "{name}"` cannot collide with
  `test_message_steps.py:39`; vocabulary's next ruling is 35 and ruling 1's 🔴 is recorded as
  overruled by the issue (Correction 6). Journey ends on Grace's reload — the server's state.
- Expected reds are what the runtime reports (`ModuleNotFoundError` only where every test needs the
  module; `is not a function` for missing session exports; `ProgrammingError` for the absent column).
- Guards that pass today are named as guards of existing behaviour the issue lists.
- Workflow: exemplar sections and header; 580 lines; RED 1–4 before GREEN 5–8 with the
  test-reviewer gate; *Found while building* empty; no task commits; nothing built on a 🔴 (D28
  decided by the issue, recorded in Task 9); verification names lint, unit, integration and e2e;
  every file-map row is in its stage's write scope.
