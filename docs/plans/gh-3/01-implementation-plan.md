# Display names, unique names and a preferences page — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A signed-in user renames themselves on a new `/settings` page; display names become
unique across CollabHub; Auth gains a per-user preferences store (D28) whose first key, `clock`,
drives every message, thread-summary and search-result time.

**Architecture:** One pure module, `auth/names.py`, owns every name rule — trim + NFC, the refused
characters, the comparison key, the suffix rule and the migration's de-duplication — and both the
app and the database compare through it: `users.display_name_key` holds `name_key(display_name)`,
set by the model on every assignment, under a plain unique index, so Postgres compares bytes and
never its own `lower()`. A race is settled by that index: a rename's `IntegrityError` is the 409, a
first sign-in retries the next suffix inside a SAVEPOINT. Preferences are a `user_preferences` row
merged by one atomic upsert. The SPA adds `/settings` (Profile + Preferences), a hook-level mutation
`onSuccess` that writes the session profile and every cached directory, an optimistic clock
preference read by the three formatters through `lib/time.ts`, and a return-to-route after sign-in.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, pytest + testcontainers · React 19,
TanStack Query 5.101, Zustand, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/gh-3/00-issue.md` — read it first. This plan argues from it and does not
repeat it. Requirement numbers (Req 1–8), *Decided already* items (DA 1–11) and the rows of
*Where the rules meet* and *Paths* are cited by those names.

**Worktree:** `/home/runner/work/ch09/caw-gh-3`, branch `feature/gh-3`, from `main` at `2f1cc69`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | Req 1–8 only (DA 1); no admin rename (DA 2); one global name per user (DA 3) |
| 2 | Uniqueness | Global, deleted accounts included; the 409 names nobody — new register **D46**, accepted tenancy leak (DA 4) |
| 3 | Lookalikes, ZWJ/ZWNJ | Not detected / refused respectively (DA 5); U+2800 stays allowed |
| 4 | Live push of a rename | None (DA 6, Req 5) |
| 5 | Preferences | Auth, table `user_preferences(user_id, prefs jsonb, version, updated_at)`, server-validated keys; SPA holds them in TanStack Query — **D28 🟢** (DA 7) |
| 6 | Keys | `clock` only (DA 8) |
| 7 | Auth on the routes | `require_user`, fail open (DA 9) |
| 8 | SPA client | Hand-typed in `lib/auth/api.ts`: `updateMe`, `preferences`, `updatePreferences` (DA 10) |
| 9 | Logs | No display name in any log line (DA 11) |
| 10 | The journey | Alan renames himself; Grace sees it after a reload; harness gains `alan` (issue *Tests*) |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 11 | How the database compares names | Column `users.display_name_key text NOT NULL` = `names.name_key(display_name)`, unique index `uq_users_display_name_key`; set by a SQLAlchemy `@validates("display_name")` on `User`, so no write path can forget it | The issue's own assumption asks whether `lower()` is enough: it is not. Postgres `lower()` follows the database's `LC_CTYPE` (ASCII only under `C`) and is not full case folding (`Straße`/`STRASSE`), so app and database would disagree — Req 2 forbids that. An expression index on `lower(display_name)` is the alternative; changing to it later is a migration and drops the casefold tests' strongest case |
| 12 | The key | `NFC(casefold(NFC(name)))` on the stored (already trimmed, NFC) name | Python `str.casefold()` is full Unicode case folding; NFC again because folding can denormalise |
| 13 | The rename race | No pre-check `SELECT`; the unique index decides. An `IntegrityError` on `uq_users_display_name_key` → rollback → 409; any other constraint re-raises | A pre-check still races; one decider. Exactly the *Where the rules meet* race row |
| 14 | First-sign-in race | `provision_user` tries `names.candidates(base)` in order, each insert in `session.begin_nested()`; the name-key violation rolls back the SAVEPOINT and tries the next | The index blocks the second insert until the first commits, then fails it: the retry is the only way "never refuses" holds |
| 15 | Preferences write | One `INSERT … ON CONFLICT (user_id) DO UPDATE SET prefs = (user_preferences.prefs \|\| :set) - :remove` | Row-locked, merges into the latest committed row, so two tabs on different keys keep both (*Where the rules meet*, two tabs) |
| 16 | Own-tab update on rename | In `useMutation({ onSuccess })` — not `mutate(…, { onSuccess })`: cancel in-flight directory fetches, write the new name into every cached `['workspace-members', *]` that has data, refetch any that has none; `session.updateProfile(profile)`; set `['profile','me']` | `@tanstack/query-core` 5.101.4: hook-level callbacks run from the `Mutation` (`build/modern/mutation.js:123`), per-`mutate` ones only while the observer has listeners (`mutationObserver.js:77`) — the *Paths* row "leaving mid-save". Cancel, because a directory fetch answered before the commit would land the old name after the write |
| 17 | Clock writes | **Serial and optimistic.** `useMutation({ scope: { id: 'preferences' } })`: each `onMutate` runs at the click (`mutation.js:94-105`, before `retryer.start()` at `:115`), but the PATCHes go one at a time in click order (`canRun`, `mutationCache.js:60-70`, `mutation.js:86`), so the server's last write is the last choice. Bookkeeping per `QueryClient` (a `WeakMap` in `usePreferences.ts`, so it outlives an unmount): `inFlight`, `latest` (a sequence number), `confirmed`. `onMutate`: cancel the query; if `inFlight === 0`, `confirmed = ` the cached map; `inFlight++`; write the choice; context `{ seq: ++latest }`. `onSuccess`: `confirmed = data`; write `data` only if `seq === latest`. `onError`: only if `seq === latest`, write `confirmed` and show the error. `onSettled`: `inFlight--`. Because the saves settle in order, when the latest settles `confirmed` is the server's last saved map. `isMutating` is not used (it counts the mutation itself inside its own callbacks, `mutation.js:123` before `:144`) | Ends on the last choice in every outcome: A ok + B ok → B; A ok + B fails → A (saved) + error; A fails + B ok → B, no error (**assumed** — the last choice was saved; showing A's error is one branch); both fail → the choice before either + error. A focus refetch landing mid-save can show the old value for a moment; the latest save's response puts it right. The alternative — let them run in parallel and have the last to settle refetch — costs a GET after every choice and can still end on a server order the user didn't choose |
| 18 | Preferences cache key | `['preferences', 'me']`, not per workspace | Per user and global (DA 3, DA 7); a different user means a full sign-in navigation, so a fresh `QueryClient` |
| 19 | How formatters get the clock | `useClock()` observes `['preferences','me']` with `queryFn: skipToken` (exported by query-core 5.101, `build/modern/index.d.ts:34`); `ChatLayout` and `/settings` fetch it | No prop threaded through `MessageList`, `ThreadPanel`, `SearchPage`; one fetcher per screen |
| 20 | 12/24-hour option | `hourCycle: 'h12'` / `'h23'`, never `hour12` | `hour12: true` is `h11` in `ja-JP`; `hour12: false` rendered "24:05" in older Chrome. `hourCycle` is allowed beside `timeStyle` (ECMA-402 forbids only component fields there) |
| 21 | Where `/settings` lives | Inside `Protected`/`ChatLayout`, so the sidebar (and `current-user`) stays on screen | Req 5's "sidebar shows it at once" is then visible on the page that renamed |
| 22 | The register | D28 → 🟢; new **D46** 🟢 | D45 is the highest ID in use |
| 23 | Saving the name you have — **assumed** | 200, the row untouched: no `version` or `updated_at` bump (a name-only PATCH whose normalised name equals the stored one) | Req 1 says "changes nothing". Bumping is the alternative; changing it is one branch and one test |
| 24 | An IdP name Req 1 would refuse — **assumed** | `names.provisional(raw, fallback)`: normalise, drop refused characters, strip, cut to 100; empty → the same on the email's local part; still empty → `"user"` | Req 3 says sign-in never refuses over a name, and Req 1 says stored names are valid. Refusing would break Req 3; keeping it raw breaks Req 1 |
| 25 | A suffix past 100 characters — **assumed** | `candidates()` cuts the base so `f"{base} {n}"` is ≤ 100, then right-strips the base | Nothing written; the alternative (refuse) breaks Req 3 |
| 26 | Stored names the migration meets — **assumed** | Trim + NFC only, as Req 4 says; a name empty after that takes the email's local part (the sign-in fallback, `oidc.py:250-252`); one still holding refused characters or over 100 is left for its owner to change. Renamed rows get `updated_at = now()`, `version + 1` | `PATCH` never trimmed, so `"   "` can be stored; two empties would otherwise become `""` and `" 2"`. Cleaning refused characters too is the alternative: a one-line change, but a wider one-way data change than the issue agreed |
| 27 | Duplicate order — **assumed** | Oldest by `(created_at, id)` keeps its name; ties on `created_at` broken by `id` | Req 4 names `created_at` only |
| 28 | The Save button — **assumed** | Disabled while the field, after JS `trim()` and `normalize('NFC')`, is empty, over 100 code points (`[...s].length`), or equal to the stored name. Character rules are the server's alone, shown from the 400 | Copying Req 1's categories into TypeScript is a rule in two places |
| 29 | 400 wording — **assumed** | `"A display name must be 1 to 100 characters."`, `"A display name cannot contain invisible or control characters."` — every rule broken is listed in `errors.displayName`, length first. Null keeps today's `"A display name is required"` | The issue gives the 409's text only |
| 30 | Preferences errors and `{}` — **assumed** | Unknown key → `errors.<key>: ["Unknown preference."]`; bad clock → `errors.clock: ['Must be "12h", "24h" or null.']`; every bad key reported at once; `PATCH {}` returns the stored map and writes nothing; a `PATCH` is what creates the row | Req 6 fixes the status and field only |
| 31 | "Saved" — **assumed** | Shown after a success until the field is edited | Req 8 doesn't say how long |
| 32 | "Back to chat" — **assumed** | `/c/<id>` of the last channel opened **in the active workspace** (a new `lastChannel {workspaceId, channelId}` in the chat store, never cleared on unmount); otherwise `/` | `activeChannelId` is cleared on unmount (`ChannelView.tsx:38`), and after a workspace switch the old channel is another tenant's |
| 33 | Workspace switch on `/settings` — **assumed** | The page stays mounted; an unsaved edit survives | *Paths*: "nothing changes" |
| 34 | Return to the route after sign-in — **assumed** | For every protected route, not only `/settings` (see *Corrections* 1) | One guard (`App.tsx:10-16` says protected routes share it). Narrowing to `/settings` is one condition |
| 35 | A renewal or workspace switch racing a rename | `session.ts` keeps `profileEpoch`, bumped by `updateProfile`. `adopt()` captures it before `api.me()`; when it sets the session, it uses the fetched profile only if the epoch is unchanged, and otherwise keeps the current session's profile, which is newer. The token, workspaces and `wsp` are always the fetched ones | The issue: the sidebar and the user's own messages "never disagree" (*Where the rules meet*, row 3). A `me()` answered before the PATCH committed would otherwise put the old name back for up to ~14 minutes. A `me()` answered after the commit already carries the new name, so either result is right. The epoch is per call, not a sticky flag, so a later rename from another device still arrives at the next renewal. Renewal's retry and sign-out-on-failure (D38) are untouched |
| 36 | The name field on a revisit — **assumed** | The Profile form renders only once this visit's fetch has landed (`useProfile(...).isFetchedAfterMount`), and seeds the field from it once. Until then the section shows `Loading…` | Req 8: "reads … from the server on every visit". Showing the cached name and then following the fetch until the user edits is the alternative: one more state, and the risk of overwriting what they typed |

Nothing here builds on a 🔴 entry. **D28** was 🔴 and the issue decides it (DA 7); this slice records
it 🟢. The nearest still-open entries are **D37/D38** (what the SPA does on a 401 and on a renewal
network failure): `session.ts` gains `updateProfile`, a return path and `adopt()`'s epoch check
(decision 35). None of these touches renewal's timing, retry or sign-out-on-failure. **D18** (notifications) is not a preference here (DA 8); **D13**
(avatar buckets) is untouched — `avatarAsset` keeps today's behaviour.

## Corrections to the issue

1. **The SPA's sign-in does not return to the route it started from** (issue *Assumptions* 4). `Protected`
   redirects with no memory (`App.tsx:83`) and `Callback` always goes to `/` (`App.tsx:63`). The *Paths*
   row "`/settings` while signed out" needs it, so this plan builds it, said here rather than
   silently: `Protected` passes `state={{ from }}`; `signIn(provider, returnTo)` keeps it in
   `sessionStorage` (`collabhub.returnTo`) across the IdP redirect; `Callback` navigates to
   `takeReturnTo()`. The URL stays `/sign-in`, so `session.feature:33`'s URL check is unchanged.
2. **A unique index on `lower(display_name)` is not enough** (issue *Assumptions* 1) — see decision 11.
3. **`displayName: null` is a 400 today** (issue *Assumptions* 3): `routers/users.py:61-65`, pinned by
   `test_users.py:101`. Kept.
4. **`provision_user` is the only place a `User` is created** (issue *Assumptions* 2): checked —
   `grep "User("` over `src/` finds `identities.py:101` and the test helper `test_schema.py:22` only;
   `link_identity` (`identities.py:168`) is its only caller, from `routers/federation.py:176`.
5. **Save is disabled for an unchanged name, so the KEEP_STACK rerun can't click it** (issue *Tests*
   says a rerun re-saves the same name). The page object returns early when the loaded field already
   holds the target name; a fresh stack still drives the whole rename.
6. **The scenario vocabulary says "Ada and Grace, and no one else"** (ruling 1, 🔴 for a third
   person). The issue — the human's answer — adds Alan. Task 9 records it as ruling 35.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey**, because this is a new capability a user sees through the SPA
and only a real browser shows a rename made in one session reaching another's message after a
reload (issue *Tests*). Write the journey first; everything under it goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Alan renames himself on Settings; his sidebar shows it; Grace sees it on his message after a reload | **BDD** | `tests/bdd/features/profile.feature` |
| Trim, NFC, length, refused characters, the key, suffixes, provisional names, de-duplication | unit | `auth/tests/unit/test_names.py` |
| Preference patch parsing | unit | `auth/tests/unit/test_preferences.py` |
| Rename over REST: 400/409, case, NFC collisions, deleted names, global scope, races, token claim, workspace name; first-sign-in suffixes and races | integration | `auth/tests/integration/test_display_names.py` |
| The key column and index | integration | `auth/tests/integration/test_schema.py` |
| Migration 0002 on seeded data | integration | `auth/tests/integration/test_name_migration.py` |
| Preferences routes, merge, concurrency, 404 | integration | `auth/tests/integration/test_preferences.py` |
| Both writes fail open with R1 down | integration | `auth/tests/integration/test_r1_unreachable.py` |
| Profile form, own-view update and its races | Vitest | `features/settings/ProfileSection.test.tsx` |
| Clock choice, revert, ordering, focus refetch, cached lists | Vitest | `features/settings/PreferencesSection.test.tsx` |
| The clock in all three formatters | Vitest | `lib/time.test.ts`, `features/settings/clockSites.test.tsx` |
| `updateProfile`, return path | Vitest | `lib/auth/session.test.ts` |
| `/settings` route, every *Paths* row through the real `App` | Vitest | `App.test.tsx` |

**What no test covers:** the Unicode-version drift of the hard-coded `Default_Ignorable_Code_Point`
table (it is checked against `unicodedata.unidata_version` by reading, Task 5); every locale's
12/24-hour rendering (the suite runs in one ICU locale; the acceptance check on the preview is the
browser's); *Paths* "Grace … until her directory refetches" — existing behaviour, already pinned by
`useWorkspaceMembers.test.tsx` and doc 06 §5.2, and the journey's reload; the rolling-deploy window
in which an old Auth pod meets the 0002 schema (Task 6).

**Baseline**, from `docs/test-report.md` at `1accafe`: unit 1863 passed (Auth 59, frontend 503);
integration 47 passed, `tools/delivery` only — Auth's integration count is not in the report; end-to-end
not run. Expected counts below are "N or more".

## Global constraints

- Workspace from `wsp` only (CH001); the routes are `/users/me…` — no id in the request at all.
- D46 is the one deliberate leak: the 409 body is exactly type/title/status/`detail`/`instance`/
  `traceId`/`errors.displayName`, both texts `"That name is already taken."`. Nothing else may differ
  between "taken in my workspace" and "taken elsewhere".
- No display name in any log call (CH008, DA 11) — an `IntegrityError`'s text carries the key
  (`Key (display_name_key)=(…)`): never log it, never put it in `detail` (CH007).
- `user_preferences.user_id` gets a real FK to `users.id` (same database).
- No new env var; no chart change — `/api/v1/users` is already in `charts/collabhub/templates/
  ingress.yaml:50`'s allow-list (checked).
- Migration 0002 imports `auth.names` on purpose (Req 4: "the same code as Req 1"); a later change to
  that module changes what a fresh install's 0002 does. Say so in the migration's docstring.

## File map

Paths shortened: `auth/` = `src/services/auth/`, `fe/` = `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `auth/tests/unit/test_names.py` · `test_preferences.py` | create | the pure rules | 1 |
| `auth/tests/integration/test_display_names.py` · `test_preferences.py` · `test_name_migration.py` | create | REST, SQL, races, migration | 2 |
| `auth/tests/integration/test_schema.py` | modify | `a_user()` gets a distinct name per email — two "Ada Lovelace" rows would now fail on the name key and pass `test_email_uniqueness_ignores_case` for the wrong reason; plus the key test | 2 |
| `auth/tests/integration/test_r1_unreachable.py` | modify | fail-open test | 2 |
| `fe/test/api.ts` | modify | `auth.updateMe/preferences/updatePreferences` stubs; a **default** `GET /users/me/preferences → {}` handler in `setupServer(...)`, because `ChatLayout` now fetches it and four existing files render `ChatLayout` (`App.test.tsx`, `ChatLayout.test.tsx`, `ChatLayout.attachments.test.tsx`, `CreateChannelDialog.test.tsx`) | 3 |
| `fe/lib/time.test.ts` · `fe/features/settings/{ProfileSection,PreferencesSection,clockSites}.test.tsx` | create | SPA red | 3 |
| `fe/lib/auth/session.test.ts` · `fe/App.test.tsx` | modify | new cases | 3 |
| `tests/bdd/features/profile.feature` · `steps/test_profile_steps.py` | create | the journey | 4 |
| `tests/bdd/conftest.py` · `pages/chat_page.py` | modify | `ALAN`, `alan_context`, `alan`; settings methods | 4 |
| `auth/auth/names.py` · `preferences.py` | create | rules; preference parse/read/apply | 5 |
| `auth/auth/models.py` · `alembic/versions/0002_unique_names_and_preferences.py` | modify · create | key column, `UserPreferences`, migration | 6 |
| `auth/auth/identities.py` · `schemas.py` · `routers/users.py` · `routers/preferences.py` · `main.py` | modify ×3 · create · modify | provisioning, rename, preferences routes | 7 |
| `fe/lib/auth/api.ts` · `session.ts` · `storage.ts` | modify | client calls, `updateProfile`, return path | 8 |
| `fe/App.tsx` · `stores/chat.ts` · `features/channels/{ChannelView,WorkspaceSwitcher,ChatLayout,MessageItem}.tsx` · `features/threads/ThreadSummary.tsx` · `features/search/SearchResult.tsx` | modify | route, return path, `lastChannel`, link, prefs fetch, three formatters | 8 |
| `fe/lib/time.ts` · `fe/features/settings/{SettingsPage,ProfileSection,PreferencesSection}.tsx` · `useProfile.ts` · `usePreferences.ts` | create | the page and its hooks | 8 |
| `docs/design/{00,01,06,07}-*.md` · two ADRs · `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · create · modify | the record | 9 |

Deliberately unchanged: `auth/tests/integration/conftest.py` — `TABLES` truncates `users` with
`CASCADE` (`testkit/db.py:27`), which reaches `user_preferences` through its FK; `tests/bdd/conftest.py`'s
truncation — it never touches Auth. `test_users.py` stays as it is: its empty/null 400s and its renames
to distinct names still hold.

Sweep results: no sibling branch (`git worktree list`: `main` and this one only); no `.env.example`
or chart change; stale "D28 🔴 / no preferences" text at `MessageItem.tsx:10-16`, `SearchResult.tsx:7-8`,
`ThreadSummary.tsx:6-7`, doc 06 §9 (`:479-486`) and §5.2 (`:316-318`), register `:164`, `models.py`
docstring — all Task 8/9.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing unit, integration, Vitest and BDD tests, each for the reason given — **test-reviewer gate** |
| GREEN — Auth | 5–7 | code-writer | Tasks 1–2 pass |
| GREEN — SPA | 8 | code-writer | Task 3 passes; `tsc` clean |
| Finish | 9–10 | code-writer | the record, then verification (the journey runs there) |

One RED phase: Auth's client is hand-typed, so Task 3's stubs follow Task 3's interfaces; `tsc` is red until Task 8.

---

## Task 1: The name and preference rules (RED)

**Files:** `auth/tests/unit/test_names.py`, `auth/tests/unit/test_preferences.py` (create)

**Interfaces** — `auth.names`:
- `MAX_LENGTH = 100`; `LENGTH_RULE`, `CHARACTER_RULE`, `TAKEN` — the strings of decisions 29 and the issue
- `class InvalidDisplayNameError(ValueError)` with `.messages: list[str]`
- `normalise(raw: str) -> str` — `unicodedata.normalize("NFC", raw.strip())`
- `is_refused(char: str) -> bool` — category in `{Cc, Cf, Cs, Co, Cn, Zl, Zp}` or `Default_Ignorable_Code_Point`
- `validate(raw: str) -> str` — the stored form, or raises with every rule broken (length counted in code points **after** normalising)
- `name_key(name: str) -> str` — decision 12
- `provisional(raw: str, fallback: str) -> str` — decision 24
- `candidates(base: str) -> Iterator[str]` — `base`, `f"{base} 2"`, `f"{base} 3"`, … each ≤ 100 (decision 25)
- `@dataclass(frozen=True) StoredName(id: UUID, display_name: str, email: str, created_at: datetime)`
- `deduplicate(rows: Iterable[StoredName]) -> dict[UUID, str]` — the new name of every row whose name changes (normalised, fallback, or suffixed); unchanged rows absent

`auth.preferences`:
- `KEYS: dict[str, Callable[[object], str | None]]` — `{"clock": …}`, a validator returning an error or `None`
- `UNKNOWN = "Unknown preference."`, `BAD_CLOCK = 'Must be "12h", "24h" or null.'`
- `@dataclass(frozen=True) Patch(set: dict[str, object], remove: frozenset[str])`
- `class InvalidPreferencesError(ValueError)` with `.errors: dict[str, list[str]]`
- `parse_patch(body: Mapping[str, object]) -> Patch`

| Test (`test_names.py`) | Proves | Expected red |
|---|---|---|
| `test_the_issues_refused_examples_are_refused` — param `"Grace​"`, `"Graceㅤ"`, `"Gr͏ace"`, `"Grace\x07"`, `" "`; asserts the message | Req 1's examples | `ModuleNotFoundError: auth.names` (whole file — every test needs it) |
| `test_the_issues_accepted_examples_are_stored_normalised` — `"José"` precomposed and `"José"` both → `"José"`; `"Zoë"`, `"李小龍"`, `"O'Brien"`, `"Ada  Lovelace"` unchanged | Req 1, both NFC inputs, inner spaces kept | same |
| `test_surrounding_whitespace_is_trimmed` — `"\t Ada \n"` → `"Ada"` | `str.strip()` | same |
| `test_each_refused_category_alone` — one char each, inside `"Ab?c"`: U+0007 Cc, U+0600 Cf (not DI), U+D800 Cs, U+E000 Co, U+0378 Cn, U+2028 Zl, U+2029 Zp, and DI-not-Cf U+3164, U+034F, U+FE0F, U+115F; plus **U+2800 accepted** | each input on its own; DA 5's positive | same |
| `test_length_is_counted_after_trimming_and_nfc` — 100 accepted, 101 refused; `" " + "a"*100 + " "` accepted; 99×`"a"` + `"é"` (101 code points raw, 100 after NFC) accepted | both sides; tells before-NFC from after | same |
| `test_a_name_breaking_both_rules_lists_both` — 101 chars with a U+200B | `messages`, length first | same |
| `test_the_key_ignores_case_and_normalisation` — `key("José") == key("JOSÉ") == key("josé")`; `key("Straße") == key("STRASSE")`; `key("Ada") != key("Ada 2")` | full casefold, not `lower()` | same |
| `test_provisional_cleans_cuts_and_falls_back` — `"Sam​"` → `"Sam"`; 150 chars → 100; `"​"` with fallback `"sam"` → `"sam"`; both empty → `"user"` | decision 24 | same |
| `test_candidates_are_the_name_then_numbered_suffixes` — first three of `"X"`; a 100-char base yields `≤ 100`-char `"… 2"` and `"… 10"` | Req 3, decision 25 | same |
| `test_deduplicate_keeps_the_oldest` — three `"Sam"` given **newest first**, created t1<t2<t3 → t2 `"Sam 2"`, t3 `"Sam 3"`, t1 absent | Req 4 order; input order ≠ age | same |
| `test_deduplicate_breaks_a_created_at_tie_by_id` | decision 27 | same |
| `test_deduplicate_finds_duplicates_only_normalising_reveals` — `" José "` (older) and `"JOSÉ"` → older `"José"`, newer `"JOSÉ 2"` | Req 4's hidden duplicates | same |
| `test_deduplicate_skips_a_suffix_someone_holds` — `"Sam"`, `"Sam"`, and a third account named `"sam 2"` → the newer Sam gets `"Sam 3"`, `"sam 2"` absent | free means no row's key | same |
| `test_deduplicate_gives_an_empty_name_the_email_local_part` — `"   "`, `grace@x` → `"grace"` | decision 26 | same |

| Test (`test_preferences.py`) | Proves | Expected red |
|---|---|---|
| `test_clock_takes_12h_and_24h` · `test_null_removes_a_key` | Req 6, 7 | `ModuleNotFoundError: auth.preferences` |
| `test_bad_clock_values_are_refused` — `"12"`, `"24H"`, `24`, `True`, `""` | each alone | same |
| `test_an_unknown_key_is_refused_by_name` — `{"theme": "dark"}` → `errors == {"theme": [UNKNOWN]}` | Req 6 | same |
| `test_every_bad_key_is_reported_at_once` — `{"clock": "x", "theme": 1}` | decision 30 | same |
| `test_an_empty_patch_is_empty` | decision 30 | same |

Every invisible character in these rows (U+200B, U+3164, U+034F, U+00A0) is written in the test as a
`\u` escape, so a reader can see it. House docstrings (one line on what breaks without the rule).
Leave uncommitted.

## Task 2: Auth over REST, SQL and the migration (RED)

**Files:** see the file map, Task 2 rows.

**Interfaces** — the wire contract Tasks 3, 7 and 8 depend on:

```
PATCH /api/v1/users/me   {displayName?: string, avatarAsset?: uuid|null}
  → 200 UserResponse (displayName stored trimmed + NFC)
  → 400 errors.displayName: [LENGTH_RULE?, CHARACTER_RULE?] | ["A display name is required"] (null)
  → 409 {detail: "That name is already taken.", errors: {displayName: ["That name is already taken."]}}
  → 404 "This account no longer exists."
GET   /api/v1/users/me/preferences  → 200 {clock?: "12h"|"24h"}  ({} with no row; never inserts)
PATCH /api/v1/users/me/preferences  {clock?: "12h"|"24h"|null}  → 200 the merged map
  → 400 errors.<key>; nothing written · 404 "This account no longer exists." for a deleted account
```

Helpers each file defines for itself (no `tests.` imports): `sign_in`, `bearer`, `me` as in
`test_users.py:24-33`; `delete_account` as in `test_deleted_accounts.py:29-34`. Production-style
isolation (no demo workspace) as `test_users.py:170-197` builds it.

| Test (`test_display_names.py`) | Proves | Expected red |
|---|---|---|
| `test_a_rename_is_stored_trimmed_and_nfc` — `"  José  "` → `"José"` in the response and `GET /me` | Req 1 | assertion: stored raw |
| `test_a_refused_name_is_400_on_display_name_and_changes_nothing` — param the 5 refused examples; asserts `errors.displayName`'s text and `GET /me` unchanged | Req 1 | assertion: 200 for four; `" "` is 200 today too (min_length 1 counts it) |
| `test_a_taken_name_is_409_and_names_nobody` — Ada → `"GRACE"`: 409, exact body keys and texts, no `"grace"`, no id, no email, no workspace in the body; Ada unchanged; then Ada → `"Grace Hopper"` 200 | Req 2, D46, guard's positive | assertion: 200 |
| `test_names_differing_only_in_normalisation_collide_both_ways` — Grace `"José"`, Ada `"JOSÉ"` 409; then Grace `"Zoë"` precomposed, Ada `"zoë"` 409 | Req 2's NFC clause, both directions | assertion: 200 |
| `test_changing_only_your_own_capitals_is_allowed` — Ada → `"ADA"` 200 stored `"ADA"`; Grace → `"ada"` 409 | Req 2 | first half passes today; red on the 409 |
| `test_saving_the_name_you_have_changes_nothing` — reads `version`, `updated_at` through `sessions` before/after; then a new name does bump | decision 23, positive | assertion: version bumped |
| `test_a_deleted_accounts_name_stays_taken` | Req 2 | assertion: 200 |
| `test_a_name_in_a_workspace_you_cannot_see_is_still_taken` — production app; Ada and Alan share nothing; Alan → `"ada"` 409 | global, not per workspace | assertion: 200 |
| `test_two_renames_to_one_name_at_once` — `asyncio.gather` of Grace and Alan → `"Sam"`; sorted statuses `[200, 409]`; one row named `"Sam"` | *Where the rules meet* row 1 | assertion: `[200, 200]` |
| `test_a_rename_leaves_the_users_workspace_name` | *Where the rules meet* | passes today — kept as the guard (the plan pins it); name it so |
| `test_the_name_claim_changes_at_the_next_refresh` — `/auth/userinfo` old after the rename, new after `/auth/refresh` | the token row | passes today; kept as the guard |
| `test_a_first_sign_in_with_a_taken_name_gets_the_first_free_suffix` — `provision_user(display_name="ADA")` with `"ada"` and `"ada 2"` taken → `"ADA 3"`, workspace `"ADA 3's Workspace"` | Req 3 | assertion: `"ADA"` |
| `test_a_returning_sign_in_never_overwrites_the_name` — rename, Dex sign-in again, still renamed | Req 3 | passes today; guard |
| `test_two_first_sign_ins_with_one_name_both_succeed` — two `sessions()`, `gather` of `provision_user("Sam")` + commit → `{"Sam", "Sam 2"}` | Req 3 race | assertion: `{"Sam"}` twice |
| `test_a_sign_in_behind_an_uncommitted_rename_takes_the_next_suffix` — session A sets Grace's `display_name="X"` and flushes, uncommitted; task B `provision_user("X")` started; A commits; B → `"X 2"` | rename/sign-in race, order 1 | assertion: `"X"` |
| `test_a_rename_behind_an_uncommitted_first_sign_in_is_409` — session A provisions `"X"` and flushes; `PATCH "X"` started; A commits → 409 | order 2 | assertion: 200 |
| `test_an_idp_name_with_refused_characters_is_cleaned` — `provision_user("Sam​")` → `"Sam"` | decision 24 | assertion |

Order-1/2 tests start B/the PATCH as a task, `await asyncio.sleep(0.2)` so it is blocked on the index,
then commit A — the holder decides the order, not the sleep (a fast B simply blocks earlier).

| Test (`test_schema.py`) | Proves | Expected red |
|---|---|---|
| `a_user(email)` → `display_name=f"Name of {email}"` | removes the second reason for an `IntegrityError` | — (helper) |
| `test_the_name_key_is_set_from_the_name` — `User(display_name="Straße").display_name_key == "strasse"`, and re-assigning updates it | decision 11 | `AttributeError: display_name_key` |
| `test_the_database_refuses_a_second_name_with_the_same_key` — `"Sam"` then `"SAM"` → `IntegrityError`; `"Sam 2"` inserts | the index, positive beside | first insert pair succeeds → no raise |

| Test (`test_name_migration.py`) — **sync** tests; each makes its own database with `service_database(postgres_server, "auth_mig_<n>", to_0001)` where `to_0001` runs `command.upgrade(alembic_config(dsn), "0001")` over a `run_sync` connection as `migrations._upgrade` does, seeds through `asyncio.run` with bound `text()`, then `asyncio.run(upgrade_to_head(dsn))` | Proves | Expected red |
|---|---|---|
| `test_every_name_is_trimmed_and_nfc` | Req 4 | assertion: unchanged (head is 0001) |
| `test_every_duplicate_but_the_oldest_is_renamed` — three `"Sam"`, the oldest **deleted**: it keeps `"Sam"` | Req 4, deleted included | assertion |
| `test_duplicates_only_normalising_reveals_are_renamed` | Req 4 | assertion |
| `test_an_empty_stored_name_takes_the_email_local_part` | decision 26 | assertion |
| `test_after_the_migration_every_key_is_set_and_unique` — `display_name_key` non-null; `user_preferences` exists | the schema | `ProgrammingError: column display_name_key does not exist` |

| Test (`test_preferences.py`) | Proves | Expected red |
|---|---|---|
| `test_no_row_reads_empty_and_creates_none` — `{}`, then `COUNT(*) = 0` | Req 6 | 404 (no route) |
| `test_patch_merges_and_get_reads_it_back` | Req 6 | 404 |
| `test_null_removes_a_key` | Req 6 | 404 |
| `test_an_unknown_key_is_400_and_nothing_changes` — store `12h`; `{"clock":"24h","theme":"dark"}` → 400 `errors.theme`; still `12h` | all-or-nothing | 404 |
| `test_a_bad_value_is_400_on_its_key` | Req 6 | 404 |
| `test_a_deleted_account_gets_404_on_both_and_no_row` — asserts the `detail` | Req 6, *Paths* | 404 without the detail → assertion |
| `test_preferences_are_per_user_not_per_workspace` — set, `switch-workspace`, read | DA 7 | 404 |
| `test_concurrent_patches_of_different_keys_keep_both` — `monkeypatch.setitem(preferences.KEYS, "probe", lambda v: None)`; gather `{clock}` and `{probe}`; both present, `version == 2` | two tabs, different keys | 404 |
| `test_concurrent_patches_of_one_key_lose_no_write` — gather `12h`/`24h`; final ∈ both; `version == 2` | last write wins | 404 |
| `test_preferences_need_a_token` | 401 | 404 → assertion |

`test_r1_unreachable.py`: `test_a_rename_and_a_preference_write_fail_open` — sign in on `reachable`, then
on `r1_down` both PATCHes are 200 (DA 9); expected red: the preferences half is 404.

Leave uncommitted.

## Task 3: The SPA's red (RED)

**Interfaces** — the code Task 8 writes, which these tests import:

```ts
// lib/auth/api.ts
export type Clock = '12h' | '24h'
export interface Preferences { clock?: Clock }
export function updateMe(accessToken: string, body: { displayName: string }): Promise<Profile>
export function preferences(accessToken: string): Promise<Preferences>
export function updatePreferences(accessToken: string, patch: { clock?: Clock | null }): Promise<Preferences>
// lib/auth/session.ts
export function updateProfile(profile: api.Profile): void   // signedIn only; bumps profileEpoch; notifies
export function signIn(provider?: string, returnTo?: string): Promise<void>  // stores or clears it
export function takeReturnTo(): string   // once; '/' if none, or not a same-origin path ('//…', 'http…')
// lib/time.ts
export function timeOfDay(iso: string, clock: Clock | null | undefined): string   // {hour:'2-digit',minute:'2-digit'}
export function dateAndTime(iso: string, clock: Clock | null | undefined): string // {dateStyle:'medium',timeStyle:'short'}
// features/settings/usePreferences.ts
export const preferenceKeys: { mine: readonly ['preferences', 'me'] }
export function usePreferences(accessToken: string, opts?: { refetchOnMount?: 'always' }): UseQueryResult<Preferences>
export function useUpdatePreferences(accessToken: string): UseMutationResult<Preferences, Error, { clock: Clock | null }>  // scope 'preferences'
export function useClock(): Clock | null
// features/settings/useProfile.ts
export const profileKeys: { me: readonly ['profile', 'me'] }
export function useProfile(accessToken: string): UseQueryResult<Profile>   // refetchOnMount 'always'
export function useUpdateDisplayName(accessToken: string): UseMutationResult<Profile, Error, string>
// features/settings/*.tsx
export function SettingsPage(props: { accessToken: string; workspaceId: string | null }): JSX.Element
export function ProfileSection(props: { accessToken: string }): JSX.Element
export function PreferencesSection(props: { accessToken: string }): JSX.Element
// stores/chat.ts
lastChannel: { workspaceId: string; channelId: string } | null; setLastChannel(v): void
```

Markup the tests query: heading `Settings`; `Profile` and `Preferences` headings; textbox labelled
`Display name`; button `Save`; text `Saved`; field errors with `role="alert"`; radiogroup `Clock` with
radios `Automatic`, `12-hour`, `24-hour`; link `Back to chat`; in the sidebar, a **link** whose name is
the user's display name (`current-user`). BDD-only `data-testid`s (never read here): `settings-page`,
`profile-name-input`, `profile-save`, `profile-saved`.

`test/api.ts`: `auth.updateMe(reply | fn)`, `auth.preferences(prefs)`, `auth.updatePreferences(reply | fn)`
(recorded; a function reply may return a promise to hold it), and the default handler (file map).
The session is module state: a test that needs it signed in resets modules and imports `session`
and the component under test fresh, as `session.test.ts:50-52` and `App.test.tsx:55-59` do.

| Test | Proves | Expected red |
|---|---|---|
| `time.test.ts`: `Automatic follows the browser locale` · `24-hour shows 15:07 for a local 15:07` · `12-hour shows 3:07 and not 15:07` · `a morning time reads 9:05 either way` — each for both functions; dates built from **local** parts (`new Date(2026, 8, 15, 15, 7)`) so any TZ works | Req 7 formats, both sides of noon | `Failed to resolve import "./time"` |
| `clockSites.test.tsx`: `a message time follows the stored clock` · `a thread summary time follows it` · `a search result time follows it` — `MessageItem` (with `replyCount`, `lastReplyAt`, `onOpenThread`) and `SearchResult`, cache seeded `{clock:'24h'}` then `{clock:'12h'}` | Req 7's three places | `Failed to resolve import "./usePreferences"` |
| `ProfileSection.test.tsx`: `prefills from the server, not the session's copy` (session `Ada Lovelace`, server `Ada L.`) | Req 8, *Paths* reload | module not found |
| · `on a revisit the field waits for this visit's fetch` — cache seeded `['profile','me']` = `Ada L.`, the GET held and answering `Ada M.`: no `Display name` textbox while it is held; then its value is `Ada M.` | decision 36; fails a build that seeds from the cache | same |
| · `Save is off while unchanged, blank or over 100, and on otherwise` — unchanged; `"  Ada L.  "`; `"   "`; 101 and 100 code points | decision 28, both sides | same |
| · `shows the 400 and the 409 on the field, and changes nothing` | Req 1, 2 | same |
| · `says Saved after a success, until the next edit` | Req 8, decision 31 | same |
| · `a success updates the session and every cached directory` — `session.restore()` signed in first; directories for two workspaces seeded | Req 5, *Where the rules meet* | same |
| · `a directory fetch answered before the rename cannot bring the old name back` — `scriptDirectory().hold` released with the old name **after** the PATCH resolves; and the other order | decision 16, races both ways | same |
| `PreferencesSection.test.tsx`: `shows the stored clock, read from the server` (cache seeded stale) | Req 8 | module not found |
| · `choosing saves at once with only that key` — body exactly `{clock:'24h'}`; Automatic sends `{clock:null}` | Req 7, two tabs | same |
| · `a failed save puts the previous choice back and shows the error` — PATCH held: radio is 24-hour while in flight; 500 → previous + alert | Req 7, *Timing* | same |
| · `a second choice waits for the first save, and the tab and the server end on the last` — both PATCHes held: 12-hour then 24-hour; `requests()` holds **one** PATCH and the radio reads 24-hour; release the first (it answers `{clock:'12h'}`) → the radio **still** reads 24-hour and the second PATCH is now recorded; release it → 24-hour; bodies in order `[12h, 24h]` | decision 17; fails a parallel build (two PATCHes while the first is held) and one where a non-latest response writes (12-hour after the first release) | same |
| · `a failed second save goes back to the first, which was saved` — first 200, second 500 → 12-hour and the alert | decision 17 | same |
| · `a failed first save under a successful second ends on the second, with no error` — first 500, second 200 → 24-hour, no alert | decision 17 (assumed half) | same |
| · `two failed saves go back to the choice before either` — start Automatic; both 500 → Automatic and the alert | decision 17; fails a build restoring the snapshot (12-hour) | same |
| · `choosing re-renders a time already on screen without refetching` — `MessageItem` beside the section; `requests()` holds only the PATCH | *Where the rules meet*, cached lists | same |
| · `refetches on window focus` — `test/page.ts`'s focus helper | *Paths*, second tab | same |
| `session.test.ts`: `updateProfile replaces the signed-in profile and notifies` · `updateProfile does nothing when signed out` | own view | `session.updateProfile is not a function` |
| · `a renewal that read the profile before a rename keeps the renamed one` — after `restore()`, `server.use` a `GET /users/me` handler that sets a flag and awaits a deferred (built like `answerSlowly()`, `:270-285`), answering `PROFILE`; refresh answers marker `renewed`; start `restore()`, `vi.waitFor` the flag, `updateProfile({...PROFILE, displayName: 'Ada L.'})`, release, await → `Ada L.` **and** the `renewed` token | decision 35, order 1; the token half shows the renewal still adopted | same |
| · `a renewal that read the profile after a rename takes the server's` — `updateProfile('Ada L.')`, then `auth.me({...PROFILE, displayName: 'Ada M.'})`, `restore()` → `Ada M.` | order 2; fails a sticky "renamed locally" flag | same |
| · `a workspace switch that read the profile before a rename keeps the renamed one` — as the first, through `changeWorkspace(AWAY)` → `Ada L.`, `activeWorkspaceId === AWAY` | *Paths*: a switch on `/settings` | same |
| · `signIn keeps a return path across the redirect, and clears an old one without it` | *Paths* | assertion: `sessionStorage` null |
| · `takeReturnTo gives the path once, then '/'; refuses '//evil.example' and 'https://evil.example'` | open redirect | `takeReturnTo is not a function` |
| `App.test.tsx` (each through the real `App`; red is `"No such page."` / a timeout unless said): `shows Settings on a direct load, from the server` · `clicking your name opens Settings` · `a signed-out visitor to /settings is asked to sign in, and the path is kept` (`location.assign` stubbed as `session.test.ts:315`) · `the callback lands on the kept path` (red: lands on `/`) · `Back to chat returns to the last channel in this workspace` · `…to the start after a workspace switch` · `…to the start when no channel was opened` · `a save still lands after leaving mid-save` (PATCH held, click Back to chat, release → sidebar link shows the new name) · `leaving with an unsaved edit drops it without asking` (`window.confirm` spy not called; reopening shows the stored name) · `a workspace switch on Settings changes nothing` (still `/settings`, same name, same clock, the unsaved edit kept) | Req 5, 8, every SPA *Paths* row | as said |

Leave uncommitted.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/profile.feature`, `tests/bdd/steps/test_profile_steps.py` (create);
`tests/bdd/conftest.py`, `tests/bdd/pages/chat_page.py` (modify)

```gherkin
@bdd
Feature: Display names

  A name is what everyone else reads beside your words, so it is yours to change and
  nobody else's. The window that changes it shows the new name at once; everyone else
  sees it the next time their copy of the workspace's names is fetched, which a reload
  always does.

  Background:
    Given Ada is signed in
    And Ada has created a public channel named "general"

  Scenario: Alan renames himself and Grace sees it after reloading
    Given Alan has sent "the machine is thinking" in "general"
    When Alan changes his display name to "Alan Turing"
    Then Alan's own name reads "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the machine is thinking" written by "Alan Turing"
```

- Reused verbatim: `Ada is signed in`, `Ada has created a public channel named`, `Grace reloads
  CollabHub`, `Grace opens the "{name}" channel` (all `steps/conftest.py`). Reload, then open — ruling 22.
- New, in `test_profile_steps.py`: `Given Alan has sent "{body}" in "{channel}"` (open, open channel,
  `send_message_and_wait`); `When Alan changes his display name to "{name}"`; `Then Alan's own name
  reads "{name}"`; `Then Grace sees "{body}" written by "{name}"` — the quotes keep it from matching
  `test_message_steps.py:39`'s `written by Ada`, and that phrase from matching it.
- `conftest.py`: `ALAN = "alan@collabhub.dev"` (in all three Dex configs already), `alan_context`
  (session scope, `_signed_in_context`) and `alan` (function scope, `_restore`), beside `ada`/`grace`.
- `ChatPage`: `change_display_name(name)` — click `current-user`, wait for `settings-page`, wait for
  `profile-name-input` visible; if its value already equals `name`, return (*Corrections* 5); else
  fill, click `profile-save`, expect `profile-saved` visible. `has_own_name(name)` — retrying
  `expect(current-user).to_have_text(name)`. `has_author` exists (`chat_page.py:256`).
- Expected red: collection passes and every step binds (`--generate-missing` prints nothing); at the
  e2e run, `change_display_name` times out waiting for `settings-page` (`current-user` is a `<p>`).

Leave uncommitted.

## Task 5: The pure rules (GREEN)

**Files:** `auth/auth/names.py`, `auth/auth/preferences.py` (`parse_patch` and its constants only here)

- [ ] `names.py` to Task 1's interface. The Default_Ignorable table, from `DerivedCoreProperties.txt`
  for `unicodedata.unidata_version` (15.0.0 on 3.12) — check it against that file and say which
  version in the docstring:
  ```python
  # Default_Ignorable_Code_Point — unicodedata has no property lookup for it.
  _DEFAULT_IGNORABLE = (
      (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160),
      (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
      (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
      (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
      (0xE0000, 0xE0FFF),
  )
  ```
- [ ] `deduplicate`: sort by `(created_at, id)`; normalise (fallback for empty); the first holder of a
  key keeps it; each later one takes the first `candidates()` entry whose key nobody holds — taken
  keys include every row's final name, so a later row's own name is reserved before suffixes are
  handed out (`test_deduplicate_skips_a_suffix_someone_holds`).
- [ ] `parse_patch` to Task 1's interface. Task 1: all pass (`uv run pytest src/services/auth/tests/unit`).
- [ ] Leave uncommitted.

## Task 6: The schema (GREEN)

**Files:** `models.py`, `alembic/versions/0002_unique_names_and_preferences.py`

- [ ] `User.display_name_key` (`String`, not null) with `Index("uq_users_display_name_key", …, unique=True)`
  in `__table_args__`; `@validates("display_name")` sets `self.display_name_key = names.name_key(value)`.
  `UserPreferences`: `user_id` PK + FK, `prefs` JSONB not null `'{}'`, `version` int `0`, `updated_at`.
- [ ] Migration — the lock and the order are the value:
  ```python
  def upgrade() -> None:
      bind = op.get_bind()
      # New first sign-ins wait here, so none can insert a duplicate between the read and the index.
      op.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
      op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))
      rows = bind.execute(sa.text("SELECT id, display_name, email, created_at FROM users")).all()
      renamed = names.deduplicate(names.StoredName(*row) for row in rows)
      # UPDATE … SET display_name = :name, updated_at = now(), version = version + 1 WHERE id = :id  (renamed)
      # UPDATE … SET display_name_key = :key WHERE id = :id  (every row, from its final name)
      op.alter_column("users", "display_name_key", nullable=False)
      op.create_index("uq_users_display_name_key", "users", ["display_name_key"], unique=True)
      op.create_table("user_preferences", …)  # as the model
  ```
  Bound parameters only (CH006). Downgrade drops the table, the index and the column; names stay
  renamed (one-way, Req 4) — say so in its docstring. Say there too that during a rolling deploy
  (the chart's `pre-upgrade` migrate Job, `templates/auth/migrate-job.yaml:16`) an Auth pod still on
  the old code fails a first sign-in (no `display_name_key`, NOT NULL) and could write a rename
  without its key, until it is replaced; the SPA on `main` never renames.
- [ ] Task 2's `test_schema.py` and `test_name_migration.py` pass. Leave uncommitted.

## Task 7: Provisioning, rename, preferences routes (GREEN)

- [ ] `identities.is_display_name_conflict(exc: IntegrityError) -> bool` — the constraint name from
  asyncpg's `UniqueViolationError.constraint_name` (`exc.orig.__cause__`), `== "uq_users_display_name_key"`.
- [ ] `provision_user`: `base = names.provisional(display_name, fallback=email.split("@")[0])`; for each
  `names.candidates(base)`: `async with session.begin_nested():` add a new `User` and flush; on a
  name conflict continue, else re-raise. Workspace named from the stored name.
- [ ] `UpdateUserRequest.display_name: str | None = None` (no `Field` bounds — they ran before
  trimming). `update_me`: null → today's 400; `names.validate` → 400 `errors.displayName = messages`;
  a name-only PATCH equal to the stored name returns without writing (decision 23); otherwise assign,
  bump, `commit()`; a conflict → `rollback()`, `ProblemException.conflict(names.TAKEN,
  errors={"displayName": [names.TAKEN]})`. Docstring: D46's leak, accepted.
- [ ] `preferences.read(session, user_id) -> dict` and `apply(session, user_id, patch) -> dict` — the upsert:
  ```sql
  INSERT INTO user_preferences (user_id, prefs, version, updated_at)
  VALUES (:uid, CAST(:set AS jsonb) - CAST(:remove AS text[]), 1, now())
  ON CONFLICT (user_id) DO UPDATE
     SET prefs = (user_preferences.prefs || CAST(:set AS jsonb)) - CAST(:remove AS text[]),
         version = user_preferences.version + 1, updated_at = now()
  RETURNING prefs
  ```
  Built with SQLAlchemy's `insert(...).on_conflict_do_update` or a bound `text()` — never formatted.
- [ ] `routers/preferences.py`: prefix `/api/v1/users/me/preferences`, `GET ""` and `PATCH ""` (body
  `dict[str, Any] = Body(...)`), both `require_user`, `find_user` → 404 first, `InvalidPreferencesError`
  → `validation_error(errors=…)`, an empty patch reads without writing. Register in `main.py:119`.
- [ ] Tasks 1–2 pass: `uv run pytest src/services/auth`. Leave uncommitted.

## Task 8: The SPA (GREEN)

- [ ] `api.ts`, `storage.ts` (`returnTo` beside `pkceVerifier`), `session.ts` to Task 3's interface.
  `completeSignIn`'s failure paths clear the return path. `adopt()` takes the epoch check of decision 35.
- [ ] `App.tsx`: `/settings` → `Protected` → `SettingsRoute`; `Protected` passes `state={{ from:
  pathname + search }}`; `SignIn` hands `from` to `signIn`; `Callback` → `takeReturnTo()`.
- [ ] `stores/chat.ts` `lastChannel`; `ChannelView` sets it when both ids are known.
  `WorkspaceSwitcher`: `current-user` becomes a `Link` to `/settings`. `ChatLayout` calls
  `usePreferences(current.accessToken)`.
- [ ] `lib/time.ts` (decision 20); `MessageItem`, `ThreadSummary`, `SearchResult` call
  `timeOfDay`/`dateAndTime` with `useClock()` and drop their local helpers and the D28 comments.
- [ ] `features/settings/*` to Task 3's interface and decisions 16, 17, 28, 31–33. TanStack for every
  server value; nothing server-side in Zustand (D24). Errors via `ProblemError.fieldError`.
- [ ] Task 3 passes: `npm --prefix src/frontend test`, then `npm --prefix src/frontend run typecheck`.
  Leave uncommitted.

## Task 9: The record

- [ ] Register: D28 🟢 (DA 7's text; "built 2026-10 against it: `clock`"); D46 🟢 global unique display
  names, the leak it accepts, the key column. Header "Settled" line for both.
- [ ] ADRs with the `adr-writer` skill: D28 (preferences in Auth, per user, validated keys, one upsert);
  D46 (global uniqueness over tenancy; the casefold key over `lower()`).
- [ ] Doc 01: §3 table + the two preferences routes and the 409/400s on `PATCH /users/me`; §4
  `display_name_key`, its index and `user_preferences`, and that the uniqueness counts deleted rows
on purpose (no `deleted_at` filter, Conventions §3); §5.1 the first-sign-in suffix rule.
- [ ] Doc 06: §3 `/features/settings`; §5.2 *Names* — the renamer's own tab updates at once; §9 D28
  decided; the return-to-route in §4.
- [ ] Conventions §5.4: the D46 exception, worded as the issue's *Record* says.
- [ ] Vocabulary: ruling 35 — Alan, why (issue *Tests*), the four new phrases.
- [ ] Sweep: `grep -rn "D28\|no user-preferences\|Renames are not covered" docs/design src/frontend/src`
  and the `models.py` docstring.

## Task 10: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — every layer the change
  reaches, once each: `integration` because Auth's SQL and migration change; `e2e`, the whole layer,
  because a journey is added and sign-in's redirect changes. Counts at or above the baseline.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; a waiver names every checker on its line.
- [ ] **First real run** on the Compose stack (`docker compose up -d --build`): before it, give two dev
  users one name in SQL so 0002 has a duplicate to rename; then rename in one browser and watch the
  sidebar; try another's name in capitals; choose 24-hour and look at a thread summary and a search
  result; sign out on `/settings` and sign back in. Expect it to find something; fix it with a test.
- [ ] Fill in *Found while building*. Leave the worktree dirty.

## Found while building

Round 1, code-writer (details in `03-green-report.md`):

1. **A test fault, sent back** (`reviews/code-writer-sendback-3.md`): `test_name_migration.py`'s
   `user()` builds `created_at = T0 + (100 - age)` days, so a lower `age` is the *newer* account,
   against its docstring; three migration tests (`…_but_the_oldest_is_renamed`,
   `…_only_normalising_reveals…`, `…_every_key_is_set_and_unique`) expect the opposite of Req 4.
   The code keeps the name on the oldest. Pinned by `names.deduplicate`'s unit tests; the fix is
   `T0 + timedelta(days=age)`.
2. **Imports the lint hook strips between edits.** Not a departure from the plan, but the Auth
   edits had to be made so that an import and its first use landed together.
3. **`update_me` with only an unchanged name returns early**; a PATCH that also carries
   `avatarAsset` still writes and bumps. (Decision 23 speaks of a name-only PATCH.) No test for the
   mixed case.
4. **A failed profile fetch** (plan-reviewer 2, decision 36): `ProfileSection` shows a
   `ProblemBanner` and no field, rather than seeding from a stale name. No test.
5. **`/settings` first-run by hand** (Task 10's real run on the Compose stack) was not done by this
   stage; see the green report's *Left for the human*.
6. `scripts/test.sh` prints `mktemp: too few X's in template` from `.claude/hooks/security.sh` in this
   environment (gitleaks and semgrep temp files); the script still reports clean. Not touched.

## Not in this plan

- Everything in the issue's *Not in this issue*; a live rename broadcast; TR39 confusables.
- Generating Auth's OpenAPI types (DA 10).

## Self-review

- **Issue coverage:** Req 1 → Tasks 1, 2, 5, 7; Req 2 → 1, 2, 6, 7; Req 3 → 1, 2, 7; Req 4 → 1, 2, 6;
  Req 5 → 3, 4, 8; Req 6 → 1, 2, 7; Req 7 → 3, 8; Req 8 → 3, 4, 8. *Where the rules meet* and *Paths*:
  every row named in Tasks 2–3. DA 9 → `test_r1_unreachable`; DA 11 → CH008.
- **Names** spelled one way throughout. **Known ripple** (`a_user`, the default preferences handler)
  is RED work, because no GREEN task writes a test.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** Decision 17: the saves share a mutation `scope`, so they go out serially in click
   order, and only the latest choice's response writes. A failure of the latest restores
   `confirmed`, not the snapshot. Each outcome pair has a Task 3 test; `isMutating` is not used.
2. **Fixed.** Decision 35: `adopt()` keeps the newer profile through `profileEpoch`. Three
   `session.test.ts` cases cover a renewal in both orders and a workspace switch.
3. **Fixed.** Decision 36 (assumed): the form waits for this visit's fetch, with a new test.
4. **Fixed.** The migration docstring and *What no test covers* name the rolling-deploy window.
   The *Left for later stages* notes are taken up too: Task 1 asks for `\u` escapes, and Task 9 notes the deleted rows.
