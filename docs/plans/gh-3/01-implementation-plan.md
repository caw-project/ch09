# Display names, unique names and a preferences page — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A signed-in user renames themselves on a new `/settings` page; display names are unique
across CollabHub; the same page sets the first per-user preference, a 12/24-hour clock (D28).

**Architecture:** Auth gains `users.display_name_key` — a case-folded NFC key computed in Python by
one function and set by a SQLAlchemy validator on every write — under a unique index that also
covers deleted accounts. The index is the whole concurrency story: a rename that loses gets a 409,
a first sign-in that loses retries the next suffix inside a savepoint. Migration `0002` normalises
and de-duplicates stored names, then builds the index, and creates `user_preferences`, merged by one
upsert. The SPA adds `/settings` inside the chat shell, a clock that reaches the three time
formatters through one hook, and a sign-in that returns to the page it started from.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, pytest +
testcontainers · React 19, TanStack Query v5, Zustand, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/gh-3/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `/home/runner/work/ch09/caw-gh-3`, branch `feature/gh-3`, from `main` at `b5f3ffd`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | Req 1–8; *Not in this issue* stays out |
| 2 | Who renames whom | Only yourself; one global name per user |
| 3 | The name rules | `str.strip()`, NFC, 1–100 characters, none of Cc Cf Cs Co Cn Zl Zp or `Default_Ignorable_Code_Point` |
| 4 | Uniqueness (D46) | Global, ignoring case, deleted accounts included; 409 `"That name is already taken."` naming nobody |
| 5 | Lookalikes, ZWJ/ZWNJ, U+2800 | Not handled / refused / allowed, as Decided 5 says |
| 6 | First sign-in | `X 2`, `X 3`, …; workspace named from the result; never refused, never overwrites |
| 7 | Existing duplicates | Oldest account keeps the name; the migration is one-way |
| 8 | Broadcast | None; the renamer's own tab only |
| 9 | Preferences (D28) | Auth, `user_preferences (user_id, prefs jsonb, version, updated_at)`, per user, validated keys; TanStack Query, never Zustand |
| 10 | The one preference | `clock`: `"12h"`, `"24h"` or absent |
| 11 | Fail-open | Both PATCH routes `require_user`, not in Conventions §5.2's set |
| 12 | Auth client | Hand-typed in `lib/auth/api.ts` |
| 13 | Logs | No display name is ever logged (CH008) |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 14 | How uniqueness is enforced | A `display_name_key text NOT NULL` column under unique index `ux_users_display_name_key`, **not partial**, computed by `auth.names.name_key()` | Postgres `lower()` depends on the database's ctype and provider, which differ between the Compose image, testcontainers and a managed Postgres — so app and database could disagree. Computing the key once in Python and letting the database compare bytes makes "the application and the database compare the same way" true by construction (see *Corrections* 1). Alternative: an expression index on `lower(display_name)` |
| 15 | What "ignoring case" means — **assumed** | `name_key(n) = NFC(n.casefold())`: full Unicode case folding, so `Straße` collides with `STRASSE` | The issue asks whether `lower()`'s gaps matter; for impersonation they do. Moving later to `lower()` only splits collisions (one function and a key recompute); moving the other way would need renames. Alternative: `str.lower()` |
| 16 | Where the key is set | `@validates("display_name")` on `User` sets `display_name_key` | Every write — `provision_user`, the rename, any test constructing `User(...)` — goes through one function. The migration uses raw SQL and calls `name_key` itself |
| 17 | The rename race | Flush the update; an `IntegrityError` whose `orig.__cause__.constraint_name == "ux_users_display_name_key"` becomes the 409, any other is re-raised | SQLAlchemy's asyncpg adaptor re-raises with the asyncpg error as `__cause__` (`sqlalchemy/dialects/postgresql/asyncpg.py:791-797`), and asyncpg's `UniqueViolationError` carries `constraint_name`. A second writer blocks on the index until the first settles, so "exactly one succeeds" needs no lock |
| 18 | The first-sign-in race | `provision_user` tries `names.candidates(base)` in order, each insert inside `session.begin_nested()`; a name-index violation rolls back the savepoint and tries the next | The callback commits only at its end (`routers/federation.py:212`), so a pre-check would race. An uncommitted holder blocks the insert until it commits (next suffix) or rolls back (the name). Alternative: a per-key advisory lock — it would also have to cover renames |
| 19 | An IdP name that breaks Req 1 — **assumed** | `names.from_idp(raw, email)`: normalise, drop refused characters, **normalise again** (dropping a CGJ can leave `e` + U+0301 uncomposed), cut to 100; if empty, the email's local part the same way; if still empty, `"user"` | "Sign-in never refuses over a name" (Req 3). Changing it is one function |
| 20 | A suffix past 100 characters — **assumed** | `candidates` cuts the base to `100 - len(" n")` and right-strips it before appending | Every candidate stays a valid name. One function |
| 21 | Stored names the migration finds invalid — **assumed** | Only trimmed and NFC-normalised (Req 4); one empty after trimming becomes `"user"`; nothing else is rewritten | Req 4 names only trim and NFC. A legacy name with refused characters stays until its owner renames. Changing it later is another data migration |
| 22 | "Oldest" and taken suffixes in the migration — **assumed** | Oldest by `(created_at, id)`; a duplicate gets the first candidate not held by **any** row's own normalised name nor assigned earlier — `Sam, Sam, Sam 2` → `Sam, Sam 3, Sam 2` | The fewest renames; the tie-break makes it deterministic. The alternative renames the third row too |
| 23 | Where name validation happens | In the route, through `names.normalise_display_name`; `UpdateUserRequest.display_name` loses `min_length`/`max_length` | Length is counted after trimming and NFC; a Pydantic constraint counts raw input and prefixes messages with "Value error,". Null stays the 400 it is today (`routers/users.py:61-65`) |
| 24 | Saving the name you have — **assumed** | Same stored form exactly: the name is not assigned; when the request changes nothing else either, 200 with no write — `version` and `updated_at` unchanged. An `avatarAsset` beside it is still applied and written. Capitals-only: written | "Succeeds and changes nothing" (Req 1), scoped to the name so an avatar is never dropped. One branch |
| 25 | The preferences merge | One statement: `INSERT … ON CONFLICT (user_id) DO UPDATE SET prefs = (user_preferences.prefs \|\| EXCLUDED.prefs) - CAST(:remove AS text[])`, `version + 1` | Two tabs on different keys can't lose each other's write; on one key the last commit wins. A read-modify-write in Python would lose one |
| 26 | Preferences wire shape | Flat object both ways: `GET → {"clock": "24h"}` or `{}`; `PATCH {"clock": "24h" \| null}` → the merged object. Errors `errors.<key>`: `["Unknown preference."]`, `['Must be "12h" or "24h".']` | Mirrors the stored `jsonb`; no envelope to version |
| 27 | A PATCH that removes everything — **assumed** | Still upserts the row (as `{}`) | Only *reading* must not create a row (Req 6) |
| 28 | The SPA's preferences key | `['preferences']`, not per workspace or user; `staleTime` 5 minutes, refetch on focus and reconnect | Per user, so a workspace switch must not touch it (Paths). One `QueryClient` never spans two users: sign-in is always a full-page navigation (`session.ts:159-163`). 5 minutes matches the directory, so another tab sees the clock "on its next refetch" |
| 29 | How the clock reaches the formatters | `useClock()` in `MessageItem`, `ThreadSummary`, `SearchResult`, through pure `formatTime` / `formatDateTime(iso, clock?, locale?)` in `src/lib/time.ts`, with `hourCycle: 'h12' \| 'h23'` | One function for the family of three. A cache write re-renders; nothing refetches |
| 30 | A clock save, its failure and fetches in flight | `useUpdateClock`: `mutationKey: ['preferences']`, `scope: { id: 'preferences' }`. `onMutate`: `await cancelQueries(['preferences'])`, snapshot, write the choice. `onError`: put the snapshot back **only if the cache still holds this mutation's choice**. `onSettled`: **if `isMutating({ mutationKey: ['preferences'] }) === 1`** (only this one left) `invalidateQueries(['preferences'])`, so the server's value has the last word | `onMutate` runs before the scope wait (`query-core/build/modern/mutation.js:94-115`), so a later choice is already in the cache when an earlier one fails; the scope keeps the PATCHes in order. The cancel stops a focus refetch already in flight landing the old value; the final invalidate repairs one *started* mid-save, and two failures in a row (F3: Automatic → 24h → 12h, both fail, ends on Automatic, not the never-saved 24h). `onSettled` runs before the `success`/`error` dispatch (`mutation.js:137-144`), and `isMutating` counts `pending` (`queryClient.js:60-61`), so the settling mutation counts itself. Cost: one GET after a burst of choices |
| 31 | A rename that lands after the page unmounts | The session and cache writes are in **`useMutation`'s** `onSuccess` | Hook-level callbacks run in `Mutation.execute` (`mutation.js:123`); `mutate()`-level ones only while an observer listens (`mutationObserver.js:77`) |
| 32 | Which caches a rename writes, and fetches in flight | `applyRename(queryClient, profile)`: `setQueryData` on every cached `['workspace-members', *]` entry (the renamer's row only) and on `['profile','me']`, **then** `invalidateQueries` on both prefixes | A name is global; the user may have several workspaces cached. `invalidateQueries` refetches active queries with `cancelRefetch: true` (`queryClient.js:168`), which cancels a fetch already in flight (`query.js:188-189`) — a focus, reconnect or unknown-id fetch answered before the commit can't land the old name; the refetch is sent after the commit, so it carries the new one. Inactive workspaces' caches are marked stale and refetch on their next mount. Cost: one directory GET per rename |
| 33 | Where `/settings` lives | Inside `Protected` / `ChatLayout`; `current-user` becomes a `<Link>` | The sidebar and socket stay up; the name in the sidebar is the one the page changes |
| 34 | "Back to chat" | `lastChannelId` in the chat store, set by `ChannelView`, kept when it unmounts, cleared on a workspace switch; `/` when none | `activeChannelId` is cleared on unmount (`ChannelView.tsx:38`), so it is gone by the time `/settings` renders. Client state, so Zustand (D24) |
| 35 | Returning to `/settings` after sign-in | Built (see *Corrections* 2): `Protected` passes the path in router state; `session.signIn(provider, returnTo)` keeps it in `sessionStorage` beside the PKCE verifier; the callback navigates to `session.takeReturnPath()` | **assumed:** for every protected route, since the guard is one component. Only a same-origin path is honoured (`/` first, not `//`, not `/\`); anything else is `/`. Narrowing to `/settings` is one condition |
| 36 | Save's "invalid" in the browser — **assumed** | Empty or over 100 **code points** (`[...s].length`, as the server's `len()`) after `trim().normalize('NFC')`; the characters are the server's to judge (400 on the field) | A convenience, not a second copy of the rule; `s.length` counts UTF-16 units and would disable names the server accepts |
| 37 | A third persona | Alan, as the issue's *Tests* says | Vocabulary §1 calls a third person a contract question; the issue settles it. Task 9 records it there |
| 38 | Register | D28 🟢 and new **D46** 🟢, with two ADRs | As *Record in this slice* |
| 39 | A renewal or switch in flight during a rename | `session.ts` counts `updateProfile` calls; `adopt` notes the count before its `api.me`, and if it changed meanwhile and the session is still the same user's, keeps the session's profile instead of the fetched one | A `GET /users/me` answered before the commit would otherwise put the old name back in the sidebar for up to 15 minutes, against *Where the rules meet* 3. The PATCH response is the newest committed name this tab knows. Alternative: re-read `me` after every rename — a second request for the same answer |
| 40 | The renamer's other tabs — **assumed** | Their message authors update on the directory's next refetch (Req 5); their sidebar `current-user` on the next renewal (≤ 15 minutes), switch or reload | Req 5 says other tabs are "like anyone else"; the sidebar has no refetch of its own today, and adding one is more than the issue asks. Changing it later: refetch `me` on focus in `session.ts` |
| 41 | Req 8 "Save disabled while unchanged" vs *Tests*' "a KEEP_STACK rerun is a no-op" — **assumed** | "Unchanged" compares the field after `trim().normalize('NFC')` with the stored name; the journey's `SettingsPage.rename_to` returns without clicking when Save is disabled (the name is already Alan's) | The issue's two sentences can't both mean a click. A fresh stack still fails at `Alan sees his name as` if the rename didn't happen, so the shortcut hides nothing |
| 42 | Who fetches `['preferences']` | `ChatLayout` primes it with `usePreferences(token)` (enabled); `useClock()` only reads — `useQuery({ queryKey: ['preferences'], queryFn: skipToken, select })` — so `MessageItem`, `ThreadSummary`, `SearchResult` never send a request | `skipToken` disables the observer (`query-core/build/modern/utils.js:224-236`); invalidation refetches only enabled queries (`queryClient.js:171`). Every existing test that mounts `ChatLayout` therefore needs a GET stub — a RED task (Task 3, *Known ripple*) |

Nothing here builds on a 🔴 entry. The nearest are **D37** (what the SPA does with a 401) — a
settings save with a revoked token shows its Problem like every other call, no new behaviour —
and **D18** (notifications), which Decided 8 keeps out.

## Corrections to the issue

1. **"A unique index on the lower-cased stored name is enough."** Not reliably: `lower()` follows
   the database's locale, which this plan does not control across environments. Decision 14
   replaces it with an application-computed key.
2. **"The SPA's sign-in returns to the route it started from."** It doesn't: `Callback` always
   navigates to `/` (`App.tsx:63`) and `Protected` drops the path (`App.tsx:83`). Decision 35
   builds it, because the *Paths* row requires it.
3. Confirmed, no change: an explicit `displayName: null` is a 400 (`routers/users.py:61-65`,
   `test_users.py:101-109`); `provision_user` is the only place a user row is created
   (`identities.py:101`; the only other `User(` is `test_schema.py:22`).
4. "Characters" in Req 1 are code points after NFC (`len()` of the stored form).

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey,** as the issue asks: a new page a user sees, and a rename that
only a second browser after a reload can show came from the server. Everything else goes down the
pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Alan renames himself on Settings; Grace, after a reload, sees the new name on his message | **BDD** | `tests/bdd/features/settings.feature` |
| Trim, NFC, length, refused characters, the key, suffixes, IdP fallback, migration de-dup | unit | `auth/tests/unit/test_names.py` |
| Preference validation | unit | `auth/tests/unit/test_preferences.py` |
| Rename over REST: stored form, 400s, 409s, races, deleted names, workspace and token names | integration | `auth/tests/integration/test_display_names.py` |
| First sign-in suffixing and its races | integration | same file |
| Preferences routes and 404 | integration | `auth/tests/integration/test_preferences.py` |
| The merge and its race (two tabs) | integration | `auth/tests/integration/test_preferences_merge.py` |
| Migration 0002 on seeded data | integration | `auth/tests/integration/test_migration_0002.py` |
| The key's index, deleted rows included | integration | `auth/tests/integration/test_schema.py` |
| Formatters; the clock in three components | Vitest | `lib/time.test.ts`, `MessageItem.clock.test.tsx`, `ThreadSummary.test.tsx`, `SearchResult.test.tsx` |
| The page: freshness, Save states, errors, Saved, clock save and revert, back link, token change | Vitest | `features/settings/SettingsPage.test.tsx` |
| Rename writes session + directories, also after unmount and over a fetch in flight; clock ordering, failures and fetches in flight | Vitest | `useProfile.test.ts`, `usePreferences.test.ts` |
| `updateProfile`, a renewal or switch in flight over a rename, return path | Vitest | `lib/auth/session.test.ts` |
| Routes: direct load, the link, signed-out return, callback | Vitest | `App.test.tsx` |
| A workspace switch forgets the last channel | Vitest | `ChatLayout.test.tsx` |

**What no test covers:** 12/24-hour output in *every* locale (`time.test.ts` has `en-US`, `en-GB`);
that a newer Python's `unicodedata` shrinks Cn (Python 3.12 is Unicode 15.0).

**Baseline**, from `docs/test-report.md` at `1accafe`: unit 1863 passed (Auth 59, frontend 503);
Auth integration was not in that run (the report's integration row is `tools/delivery` only), so
Task 10 records its count fresh; end-to-end not run. Counts below are "N or more".

## Global constraints

- `require_user` on all four user routes; the edited row comes from `principal.user_id`, never the
  body (CH001). No `require_service`.
- A deleted account: `/users/me*` routes answer **404 `"This account no longer exists."`** as
  `me` does today (`routers/users.py:31-34`).
- The 409 body is `{type, title, status, detail, instance, traceId, errors}` and names no user,
  id or workspace. D46 makes this the documented exception to Conventions §5.4 (Task 9).
- No display name in any log call, including the savepoint retry (CH008).
- `user_preferences.user_id` gets a real FK to `users.id` — both ends are Auth's.
- No new environment variable, chart or Compose change: `/api/v1/users` is already routed
  (`charts/collabhub/templates/ingress.yaml:50`).

## File map

Paths shortened: `auth/` = `src/services/auth/`, SPA paths under `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `auth/tests/unit/test_names.py` · `test_preferences.py` | create | the rules | 1 |
| `auth/tests/integration/test_display_names.py` · `test_preferences.py` · `test_preferences_merge.py` · `test_migration_0002.py` | create | routes, SQL, races, migration | 2 |
| `auth/tests/integration/test_schema.py` | modify | the key index; `a_user()` gains a `name` so the email test stops colliding on names | 2 |
| `lib/time.test.ts` · `features/channels/MessageItem.clock.test.tsx` · `features/threads/ThreadSummary.test.tsx` · `features/search/SearchResult.test.tsx` | create | the clock | 3 |
| `features/settings/SettingsPage.test.tsx` · `useProfile.test.ts` · `usePreferences.test.ts` | create | the page and its hooks | 3 |
| `lib/auth/session.test.ts` · `App.test.tsx` · `features/channels/ChatLayout.test.tsx` | modify | session, routes, last channel | 3 |
| `test/api.ts` | modify | `auth.updateMe`, `auth.preferences`, `auth.preferencesBy`, `auth.updatePreferences`, `auth.meBy`, typed from `lib/auth/api.ts` | 3 |
| `features/channels/ChatLayout.attachments.test.tsx` · `CreateChannelDialog.test.tsx` (and the `App.test.tsx`, `ChatLayout.test.tsx` setups above) | modify | `auth.preferences({})` beside their existing Auth stubs — every signed-in `ChatLayout` mount now sends the GET (Decision 42) | 3 |
| `tests/bdd/features/settings.feature` · `steps/test_settings_steps.py` · `pages/settings_page.py` | create | the journey | 4 |
| `tests/bdd/conftest.py` · `pages/chat_page.py` | modify | `ALAN`, `alan_context`, `alan`; `open_settings`, `own_name` | 4 |
| `auth/auth/names.py` · `preferences.py` | create | the pure rules; `merge`, `read` | 5 |
| `auth/auth/models.py` · `migrations.py` · `alembic/versions/0002_unique_names_and_preferences.py` | modify · modify · create | key, validator, `UserPreferences`; `upgrade_to` | 5 |
| `auth/auth/identities.py` · `routers/users.py` · `schemas.py` | modify | suffixing provision; rename, 409, preferences routes | 6 |
| `lib/auth/api.ts` · `session.ts` · `storage.ts` · `lib/time.ts` · `stores/chat.ts` | modify ×4 · create | client calls, `updateProfile`, return path, formatters, `lastChannelId` | 7 |
| `App.tsx` · `features/settings/SettingsPage.tsx` · `useProfile.ts` · `usePreferences.ts` | modify · create ×3 | the route and page | 8 |
| `WorkspaceSwitcher.tsx` · `ChatLayout.tsx` · `ChannelView.tsx` · `MessageItem.tsx` · `ThreadSummary.tsx` · `SearchResult.tsx` | modify | link, prefs priming + reset, last channel, `useClock` | 8 |
| `docs/design/00-…`, `01-…`, `06-…`, `07-…`, two ADRs, `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · create | the record | 9 |

Deliberately unchanged: Auth's integration `conftest.py` `TABLES` (truncating a table missing at
red would error every test; `TRUNCATE users … CASCADE`, `testkit/db.py:27`, reaches it by FK);
the BDD truncation (Auth is kept, on purpose); `.env.example`, charts, Compose. No sibling branch.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing unit, integration and Vitest tests and a bound journey, each failing as given — **test-reviewer gate** |
| GREEN — Auth | 5–6 | code-writer | Tasks 1–2 pass |
| GREEN — SPA | 7–8 | code-writer | Task 3 passes, `tsc` clean |
| Finish | 9–10 | code-writer | the record, then verification and the journey |

One red phase: Auth's client is hand-typed, so `tsc` is red until Task 7.

---

## Task 1: The name and preference rules (RED)

**Files:** `auth/tests/unit/test_names.py`, `auth/tests/unit/test_preferences.py` (create)

**Interfaces** — `auth.names`, pure, no I/O:
- `MAX_LENGTH = 100`
- `class InvalidDisplayNameError(ValueError)` — `str(exc)` is the message for `errors.displayName`:
  `"A display name is required."` · `"A display name is at most 100 characters."` ·
  `"A display name cannot contain invisible or control characters."`
- `normalise(raw: str) -> str` — `unicodedata.normalize("NFC", raw.strip())`, no checks
- `is_refused(ch: str) -> bool` — category in `{Cc, Cf, Cs, Co, Cn, Zl, Zp}` or in
  `DEFAULT_IGNORABLE`, a hard-coded range table from Unicode 15.0 `DerivedCoreProperties.txt`
  (Python's `unicodedata` has no such property): `00AD 034F 061C 115F-1160 17B4-17B5 180B-180F
  200B-200F 202A-202E 2060-206F 3164 FE00-FE0F FEFF FFA0 FFF0-FFF8 1BCA0-1BCA3 1D173-1D17A
  E0000-E0FFF`
- `normalise_display_name(raw: str) -> str` — `normalise`, then empty → required, `len > 100` →
  too long, any `is_refused` → invisible; returns the stored form
- `name_key(name: str) -> str` — `unicodedata.normalize("NFC", name.casefold())`
- `candidates(base: str) -> Iterator[str]` — `base`, then `f"{cut} {n}"` for n = 2, 3, … where
  `cut = base[: MAX_LENGTH - len(f" {n}")].rstrip()`
- `from_idp(raw: str, email: str) -> str` — Decision 19
- `dedupe(rows: Sequence[tuple[UUID, str]]) -> dict[UUID, str]` — rows oldest first; returns the
  new stored name of every row whose name changes (normalised, `"user"` for empty, or suffixed),
  per Decisions 21–22

`auth.preferences`, pure part:
- `CLOCK_VALUES = ("12h", "24h")`
- `@dataclass(frozen=True) class PreferencesPatch: set: dict[str, str]; remove: list[str]`
- `class InvalidPreferencesError(ValueError)` with `.errors: dict[str, list[str]]` — every bad key
- `parse_patch(raw: Mapping[str, object]) -> PreferencesPatch`

| Test (`test_names.py`) | Proves |
|---|---|
| `test_the_issues_refused_examples_are_refused` — param `"Grace​"`, `"Graceㅤ"`, `"Gr͏ace"`, `"Grace\x07"`, `" "` | Req 1's five, each alone |
| `test_the_issues_accepted_examples_are_stored_as_given` — `"José"` precomposed and `"José"` both → `"José"`; `"Zoë"`, `"李小龍"`, `"O'Brien"`, `"Ada  Lovelace"` unchanged | NFC and the inner spaces |
| `test_each_refused_category_on_its_own` — `"\x07"` Cc, `"‎"` Cf, `"\ud800"` Cs, `""` Co, `"͸"` Cn, `" "` Zl, `" "` Zp, each between `"A"` and `"B"` | each category, not just one |
| `test_default_ignorables_outside_those_categories_are_refused` — `"ᅟ"` (Lo), `"ﾠ"` (Lo), `"️"` (Mn) | the property, apart from the categories |
| `test_visible_blank_symbols_are_allowed` — `"⠀"` and `"A⠀B"` accepted | Decided 5's positive |
| `test_whitespace_is_trimmed_from_both_ends_only` — `"  Ada\n"` → `"Ada"`, `"Ada  L"` kept | trim, not collapse |
| `test_length_is_counted_after_normalising` — `"é" * 100` accepted (100 after NFC, 200 raw); `"x" * 100` accepted, `"x" * 101` refused; `" " + "x" * 100 + " "` accepted | both sides of 100, after trim and NFC |
| `test_empty_after_trimming_is_required` — `""`, `"   "` | the message is the "required" one |
| `test_the_key_ignores_case_and_form` — `name_key("José") == name_key("JOSÉ")`; `name_key("Straße") == name_key("STRASSE")` | Decision 15 |
| `test_the_key_keeps_different_names_apart` — `"Ada"` vs `"Ada L"`, `"Ada Lovelace"` vs `"Ada  Lovelace"` | the guard's positive |
| `test_candidates_count_from_two` — first three of `candidates("Sam")` | `Sam`, `Sam 2`, `Sam 3` |
| `test_a_suffix_never_makes_a_name_too_long` — `candidates("x" * 100)` second is `"x" * 98 + " 2"`; a base whose cut ends in a space has it stripped | Decision 20 |
| `test_an_idp_name_is_cleaned_not_refused` — `from_idp("Grace​", …)` → `"Grace"`; 150 characters → 100 | Decision 19 |
| `test_an_idp_name_is_composed_after_dropping` — `from_idp("e͏́", …)` → `"é"` (U+00E9), and `normalise("e͏́")` keeps the CGJ | Decision 19's second NFC, with its positive |
| `test_an_unusable_idp_name_falls_back_to_the_email_then_user` — `("​", "zed@x.dev")` → `"zed"`; `("​", "​@x.dev")` → `"user"` | both fallbacks |
| `test_dedupe_keeps_the_oldest_and_suffixes_the_rest` — `[Sam, sam, SAM]` → `{2: "sam 2", 3: "SAM 3"}` | Req 4 |
| `test_dedupe_finds_duplicates_only_normalising_reveals` — `["José", " josé"]` → `{2: "josé 2"}` | NFC before comparing |
| `test_dedupe_skips_a_suffix_another_row_holds` — `[Sam, Sam, Sam 2]` → `{2: "Sam 3"}` | Decision 22 |
| `test_dedupe_reports_a_trimmed_name_that_collides_with_nothing` — `[" Ada "]` → `{1: "Ada"}`; `["Ada"]` → `{}` | changed rows only, both sides |

| Test (`test_preferences.py`) | Proves |
|---|---|
| `test_each_clock_value_is_set` — `"12h"`, `"24h"` | the values |
| `test_null_removes_the_key` | `remove == ["clock"]`, `set == {}` |
| `test_an_unknown_key_is_refused_by_name` — `{"theme": "dark"}` | `errors == {"theme": ["Unknown preference."]}` |
| `test_a_bad_clock_is_refused` — `"25h"`, `24`, `""`, `True` | `errors["clock"]` |
| `test_one_bad_key_refuses_the_whole_patch` — `{"clock": "24h", "theme": "x"}` | raises; only `theme` in errors |
| `test_an_empty_patch_is_empty` | `PreferencesPatch({}, [])` |

**Expected red:** both files fail to load — `ModuleNotFoundError: No module named 'auth.names'` /
`'auth.preferences'`. Every test in each file needs its module, so nothing is hidden.

## Task 2: Auth over REST and SQL (RED)

**Files:** `test_display_names.py`, `test_preferences.py`, `test_preferences_merge.py`,
`test_migration_0002.py` (create);
`test_schema.py` (modify). Helpers `sign_in`, `bearer`, `delete_account` are copied per module as
the existing files do (no cross-test imports, TID251).

**Interfaces** — the wire contract Tasks 3, 6, 7 depend on:

```
PATCH /api/v1/users/me {displayName?, avatarAsset?}  → 200 UserResponse (displayName stored form)
      400 errors.displayName: [<names message>]        nothing changed
      409 detail+errors.displayName "That name is already taken."   nothing changed
GET   /api/v1/users/me/preferences  → 200 {"clock"?: "12h"|"24h"}   ({} with no row; no row created)
PATCH /api/v1/users/me/preferences {"clock": "12h"|"24h"|null}  → 200 merged object
      400 errors.<key>; nothing changed · deleted account: 404 "This account no longer exists." on both
```

`auth.preferences` I/O part: `read(session, user_id) -> dict[str, str]`;
`merge(session, user_id, patch: PreferencesPatch) -> dict[str, str]` (Decision 25, no commit).
`auth.migrations.upgrade_to(dsn: str, revision: str) -> Awaitable[None]`;
`upgrade_to_head(dsn)` becomes `upgrade_to(dsn, "head")`.

**Holding a race.** `hold_name(sessions, email, name)` opens a session, loads the user, sets
`display_name`, `flush()`es and does **not** commit; `wait_until_blocked(engine)` polls
`pg_stat_activity` for a backend with `wait_event_type = 'Lock'`, every 50 ms, failing after 5 s
with `"the request never waited on the held name"`. Every race test runs **both orders**: the
holder commits (the request loses) and the holder rolls back (the request wins).

| Test (`test_display_names.py`) | Proves | Expected red |
|---|---|---|
| `test_a_rename_is_stored_trimmed_and_composed` — `"  José  "` → `"José"` in the response, `GET /me` and the row | Req 1 | response is `"  José  "` |
| `test_each_refused_example_is_400_on_the_field` — param the five; `errors.displayName` present; `GET /me` still `"ada"` | Req 1 refusals | 200 for four; `" "` passes today's `min_length=1`, so also 200 |
| `test_a_101_character_name_is_400_and_100_is_not` — `"x"*101` → 400; `" " + "x"*100 + " "` → 200 `"x"*100` | the boundary, counted after trimming | the padded 100 is 400 today: `max_length` counts the raw 102 |
| `test_a_taken_name_is_409_and_names_nobody` — Ada → `"GRACE"`; `detail` and `errors.displayName` equal the sentence; body contains no `"grace"` (any case), no user id, no workspace id; Ada still `"ada"` | Req 2, D46 | 200 |
| `test_names_that_collide_only_once_composed_are_taken` — Grace → `"José"`, then Ada → `"josé"` → 409 | key on NFC | 200 |
| `test_changing_only_your_own_capitals_is_allowed` — Ada → `"ADA"` → 200 `"ADA"` | not a collision with yourself | passes at red — guard; becomes meaningful once the index exists |
| `test_saving_the_name_you_have_writes_nothing` — Ada → `"ada"`: `version`, `updated_at` unchanged; then `"Ada"`: `version + 1` | Decision 24, both sides | `version` bumped on the same-name save |
| `test_the_same_name_with_a_new_avatar_saves_the_avatar` — Ada PATCHes `{"displayName": "ada", "avatarAsset": <uuid7>}` → 200, `avatarAsset` stored, `version + 1` | Decision 24 scoped to the name | passes at red — guard against an early return that drops the avatar |
| `test_a_deleted_accounts_name_stays_taken` — Grace deleted in SQL, Ada → `"grace"` → 409; Ada → `"grace2"` → 200 | Req 2, deleted included | 200 |
| `test_a_rename_racing_a_held_rename` (commit / rollback) — Alan holds `"Sam"`, Ada PATCHes `"sam"` | Where the rules meet 1, both orders | the poll fails: nothing waits |
| `test_two_renames_at_once_one_wins` — Ada and Grace PATCH `"Sam"` via `asyncio.gather` | statuses `{200, 409}`; one row keyed `"sam"` | `{200, 200}` |
| `test_a_rename_leaves_the_workspace_name` — `GET /workspaces` owner row still `"ada's Workspace"` | Where the rules meet 5 | passes at red — guard, paired with the rename's 200 in the same test |
| `test_the_token_keeps_the_old_name_until_renewed` — `/auth/userinfo` old name with the old token, new after `/auth/refresh` | Where the rules meet 4 | passes at red — pins existing behaviour |
| `test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix` — users `Sam`, `Sam 2`; `link_identity(display_name="sam")` → `"sam 3"`, workspace `"sam 3's Workspace"` | Req 3 | `"sam"` |
| `test_a_return_sign_in_keeps_a_renamed_name` — Ada → `"Ada L"`, signs in through Dex again → still `"Ada L"` | Req 3 never overwrites | passes at red — guard with a positive rename in it |
| `test_a_first_sign_in_racing_a_held_rename` (commit / rollback) — Grace holds `"Sam"`; `link_identity("Sam")` in another session | Where the rules meet 2 | the poll fails |
| `test_two_first_sign_ins_with_one_name` — two `link_identity("Sam")`, different emails, gathered, each committed | `{"Sam", "Sam 2"}` | `{"Sam"}` twice |
| `test_an_unusable_idp_name_still_signs_in` — `display_name="​"`, `zed@example.com` → `"zed"` | Decision 19 | `"​"` |

| Test (`test_preferences.py`) | Expected red |
|---|---|
| `test_no_row_reads_as_empty_and_creates_none` — `{}` and `count(*) = 0` | 404 (no route) |
| `test_a_patch_is_stored_and_read_back` · `test_null_removes_the_key` | 404 |
| `test_an_unknown_key_is_400_and_changes_nothing` — after `24h`, PATCH `{"clock": "12h", "theme": "x"}` → 400 `errors.theme`; GET still `24h` | 404 |
| `test_a_bad_value_is_400` | 404 |
| `test_each_write_bumps_the_version` | 404 |
| `test_a_deleted_account_gets_404_on_both` — asserts `detail == "This account no longer exists."` | detail is absent on a missing route |
| `test_the_routes_need_a_token` — 401 on both | 404 |

`test_preferences_merge.py` is its own file because it imports `from auth.preferences import
PreferencesPatch, merge` — in the route file, that import would stop the route tests above from
running. `merge` is called directly with keys the route would refuse, because `clock` is the only
key there is and the rule is about two keys.

| Test (`test_preferences_merge.py`) | Proves |
|---|---|
| `test_merges_on_different_keys_both_survive` (commit / rollback of the holder) — session H merges `{"a": "1"}` and holds; session B merges `{"b": "2"}`, `wait_until_blocked`, H settles | committed: `{"a": "1", "b": "2"}`; rolled back: `{"b": "2"}` |
| `test_on_one_key_the_later_commit_wins` | `{"a": "2"}` after `"1"` then `"2"` |
| `test_a_removal_and_a_set_in_one_patch` | `- text[]` after `\|\|` |

**Expected red:** the file fails to load — `ModuleNotFoundError: No module named
'auth.preferences'`; all three need it.

| Test (`test_migration_0002.py`) — each on a fresh database `auth_mig_<hex8>` from a **sync** function-scoped fixture `at_0001(postgres_server)` that calls `service_database(postgres_server, name, partial(upgrade_to, revision="0001"))` (it calls `asyncio.run`, so never from inside an async test — `testkit/databases.py:36-49`); the async test seeds rows in SQL with spread `created_at` where id order disagrees, then `await upgrade_to(dsn, "head")` |
|---|
| `test_stored_names_are_trimmed_and_composed` · `test_duplicates_are_renamed_except_the_oldest` (oldest by `created_at` has the larger id) · `test_duplicates_only_normalising_reveals` · `test_a_deleted_account_counts_as_the_oldest` · `test_a_suffix_another_row_holds_is_skipped` · `test_an_empty_name_becomes_user` · `test_the_index_refuses_a_duplicate_afterwards` |

**Expected red:** the whole file fails to load — `ImportError: cannot import name 'upgrade_to'
from 'auth.migrations'`; every test needs it.

`test_schema.py`: `a_user(email, name="Ada Lovelace")`; `test_email_uniqueness_ignores_case`
gives the second user `name="Grace Hopper"`, or it would raise for the name and pass for the wrong
reason. New `test_the_name_key_is_unique_including_deleted_accounts` — `"José"` with `deleted_at`
set, then `"JOSÉ"` → `IntegrityError` naming `ux_users_display_name_key`; and
`"Ada"`/`"Ada L"` both insert. **Red:** `DID NOT RAISE`.

## Task 3: The SPA's red (RED)

**Files:** as the file map. `test/api.ts` gains, beside `auth.me`:
`auth.updateMe(reply: Profile | ((body) => Profile | Promise<Profile>))`,
`auth.preferences(prefs: Preferences)`, `auth.updatePreferences(reply)` — recorded like the rest —
and, shaped like `membersBy` (recorded on arrival, `call` from 1, a promise holds the reply),
`auth.preferencesBy(reply: (call: number) => Preferences | Promise<Preferences>)` and
`auth.meBy(reply: (call: number) => Profile | Promise<Profile>)`.

**Interfaces** — Tasks 7–8 implement exactly these:
- `lib/auth/api.ts`: `type Clock = '12h' | '24h'`; `interface Preferences { clock?: Clock }`;
  `interface PreferencesPatch { clock?: Clock | null }`; `updateMe(token, { displayName }) →
  Promise<Profile>`; `preferences(token) → Promise<Preferences>`; `updatePreferences(token, patch)
  → Promise<Preferences>`.
- `lib/auth/session.ts`: `updateProfile(profile: Profile): void` — replaces `session.profile` and
  notifies, only when signed in **as that id**; `signIn(provider = 'dex', returnTo?: string)` —
  writes `collabhub.returnPath` when given, clears it when not; `takeReturnPath(): string` — reads
  and clears it, returning it only if it starts with `/` and not `//` or `/\`, else `'/'`.
  `adopt` keeps the session's profile over the fetched one when `updateProfile` ran while it was
  fetching and the ids match (Decision 39).
- `lib/time.ts`: `formatTime(iso, clock?, locale: string | string[] = [])` (`hour`, `minute`
  2-digit); `formatDateTime(iso, clock?, locale = [])` (`dateStyle: 'medium'`, `timeStyle:
  'short'`); `hourCycle` `'h12'`/`'h23'` when a clock is set, nothing when not.
- `features/settings/usePreferences.ts`: `preferencesKeys.mine() → ['preferences']`;
  `usePreferences(token: string | null, { fresh }?)` (`fresh` → `refetchOnMount: 'always'`);
  `useUpdateClock(token)` → `useMutation<Preferences, Error, Clock | null>` with
  `mutationKey: ['preferences']`, `scope: { id: 'preferences' }` and Decision 30's three callbacks;
  `useClock(): Clock | undefined` — reads only, `queryFn: skipToken` (Decision 42).
- `features/settings/useProfile.ts`: `profileKeys.me() → ['profile', 'me']`;
  `useProfile(token, { fresh }?)`; `useUpdateDisplayName(token)` → `useMutation<Profile, Error,
  string>`; `applyRename(queryClient, profile)` — write, then invalidate (Decision 32).
- `features/settings/SettingsPage.tsx`: `SettingsPage({ accessToken })`. Headings "Settings",
  "Profile", "Preferences"; textbox labelled "Display name"; button "Save"; status "Saved";
  the field error as `role="alert"`; radiogroup "Clock" with radios "Automatic", "12-hour",
  "24-hour"; link "Back to chat". The form renders only once this visit's own GETs have answered
  (`isFetchedAfterMount`). `data-testid`s for the journey: `settings-page`,
  `settings-display-name`, `settings-save`, `settings-saved`, `settings-back`.
- `stores/chat.ts`: `lastChannelId: string | null`, `setLastChannel(id)`.

Literal values, not imports, wherever the module is new — `['preferences']`, `['profile','me']`,
`'collabhub.returnPath'` — so an existing file never fails to load for a missing module.

A time for these tests is `new Date(2026, 9, 19, 15, 5).toISOString()` — 15:05 local in any
time zone.

| Test | Proves | Expected red |
|---|---|---|
| `time.test.ts`: `24h` in `en-US` → `15:05`; `12h` in `en-GB` → `/3:05\s?pm/i`; absent in `en-GB` → `15:05`, in `en-US` → `/PM/`; the same four for `formatDateTime` | each clock overrides each locale's default | load failure: `./time` |
| `MessageItem.clock.test.tsx`: cache `['preferences']` `{clock:'24h'}` → `message-time` text contains `15:05`; `{clock:'12h'}` → not; then `setQueryData` to `24h` re-renders it and `requests()` gains nothing | the wiring, and no refetch | one of the pair fails in any locale: today's code ignores the cache |
| `ThreadSummary.test.tsx` · `SearchResult.test.tsx`: the same pair | the family of three | same |
| `SettingsPage`: `shows only what this visit fetched` — cache seeded `Old`/`12h`, GET me held: no "Display name" field while held; after: `ada`, "24-hour" checked | Paths 1 | load failure: `./SettingsPage` (all tests need it) |
| `Save is enabled only for a changed, possible name` — unchanged, `" ada "`, `"   "`, 101 chars: disabled; 100 chars, `"😀".repeat(60)` (60 code points, 120 UTF-16 units) and `"Ada"`: enabled | Req 8, Decisions 36, 41 | same |
| `a 409 shows on the field and keeps the typed name` · `a 400 shows on the field` | Req 2, 1 | same |
| `Saved shows after success and goes on the next edit` | Req 8 | same |
| `choosing a clock saves at once` — 24-hour → body `{clock:'24h'}`; Automatic → `{clock:null}` | Req 7 | same |
| `a failed clock save puts the previous choice back and shows the error` — from `12h` | Req 7, timeline 3 | same |
| `Back to chat goes to the last channel, or home` — store `c1` → `/c/c1`; `null` → `/` | Req 8 | same |
| `a new token leaves an unsaved edit and fetches nothing` — rerender with another token | Paths: workspace switch | same |
| `useProfile`: `a rename updates the session and every cached directory` — session restored via stubs; directories for two workspaces; Grace's rows untouched | Where the rules meet 3, Decision 32 | load failure |
| `the update lands after the page unmounts` — PATCH held, `unmount()`, release; wait on `session.snapshot()` | Paths: leaving mid-save | same |
| `a failed rename changes neither` — and a successful one afterwards does | guard with its positive | same |
| `a directory fetch in flight cannot put the old name back` — `membersBy`: call 1 `Ada Lovelace`; call 2 (a `refetchQueries` started before the rename) held, answering `Ada Lovelace`; call 3+ `Ada L`. Rename succeeds, release call 2 → name stays `Ada L`, and call 3 was sent; `['profile','me']` holds `Ada L` | Decision 32, F1 | same |
| `usePreferences`: `a failure is reverted only if nothing newer was chosen` — (a) from Automatic: `24h` held, `12h` chosen, `24h` fails → `12h` stays, then `12h` is sent; (b) from `12h`: `24h` succeeds, then Automatic fails → back to `24h` | Decision 30, both orders | load failure |
| `two failed choices end on what the server holds` — a stateful fake: `preferencesBy` answers a `stored` the PATCH stub sets on success; from Automatic, `24h` held and `12h` chosen, both fail → ends Automatic (`{}`), not `24h` | Decision 30, F3 | same |
| `a preferences fetch in flight or started mid-save cannot land the old choice` — (a) a GET held when `24h` is chosen, released answering `{}` → `24h` stays; (b) PATCH held, a GET started and answered `{}` (the old value shows), PATCH succeeds → ends `24h` from the final GET | Decision 30, both orders | same |
| `the second choice is not sent until the first settles` — `requests()` holds one PATCH while the first is held | the scope | same |
| `session.test.ts`: `updateProfile replaces the profile and notifies`; `…ignores another id and a signed-out state` | the setter and its guards | `session.updateProfile is not a function` |
| `a switch in flight over a rename keeps the new name, and one without adopts the fetched` — `meBy`: call 1 `Ada Lovelace` (restore); call 2 held, answering `Ada Lovelace`; `changeWorkspace(AWAY)`, `updateProfile(Ada L)`, release → profile `Ada L`; call 3 `Ada Elsewhere` on a second switch with no rename → `Ada Elsewhere` | Decision 39, both sides | same |
| `signIn remembers a return path and forgets an old one`; `takeReturnPath honours a path once and refuses //evil.example, https://evil.example, /\evil` | Decision 35 | storage reads `null`; `takeReturnPath is not a function` |
| `App.test.tsx`: `a signed-in direct load of /settings shows Settings` | Paths 1 | `No such page.` |
| `the current user's name links to /settings` | Req 8 | no link named `Ada Lovelace` |
| `a signed-out visit to /settings asks for sign-in and remembers it` — `location.assign` stubbed as `session.test.ts:315` does | Paths 2 | storage `null` |
| `the callback returns to the remembered path, or home without one` | Paths 2, both sides | lands on `/` |
| `Back to chat returns to the channel visited before` — start at `/c/:id`, click the name, then the link's `href` | the real parent path | no link |
| `ChatLayout.test.tsx`: `a workspace switch forgets the last channel` — `useChatStore.setState({ lastChannelId: 'c1' })`, rerender with another `activeWorkspaceId`, expect `null` | Decision 34, with `c1` kept by a rerender in the same workspace as the positive | stays `'c1'`: nothing clears it |

**Known ripple (RED — the code-writer may not touch a test).** After Task 8 every signed-in
`ChatLayout` sends `GET /users/me/preferences`; `test/setup.ts:32` errors on an unstubbed request.
Add `auth.preferences({})` beside the Auth stubs in `App.test.tsx` `aReturningUser()`,
`ChatLayout.test.tsx` and `ChatLayout.attachments.test.tsx` `beforeEach`, and
`CreateChannelDialog.test.tsx` *creating a channel from the chat shell* (its dialog-only tests,
which assert `requests()` exactly at line 61, mount no `ChatLayout`). Green at red and after.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/settings.feature`, `steps/test_settings_steps.py`,
`pages/settings_page.py`; `conftest.py` (`ALAN = "alan@collabhub.dev"`, `alan_context`,
`alan`, like `grace_*`); `pages/chat_page.py` (`open_settings()` clicks `current-user`;
`own_name()` waits on `current-user` text).

```gherkin
@bdd
Feature: Settings

  Everyone's name is their own to choose, and it is the same in every
  workspace. A change shows at once in the renamer's own window; everyone else
  sees it the next time their directory is fetched — a reload is enough.

  Background:
    Given Ada is signed in

  Scenario: Grace sees the name Alan gives himself
    Given Ada has created a public channel named "general"
    And Alan has sent "hello from Alan" in "general"
    When Alan changes his name to "Alan Turing"
    Then Alan sees his name as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "hello from Alan" written by "Alan Turing"
```

- Reused verbatim: `Ada is signed in`, `Ada has created a public channel named`, `Grace reloads
  CollabHub`, `Grace opens the "{name}" channel`. New: `Alan has sent "{body}" in "{channel}"`
  (opens the app, the channel, sends and waits), `Alan changes his name to "{name}"`, `Alan sees
  his name as "{name}"`, `Grace sees "{body}" written by "{name}"` (quoted, so it can't bind
  `written by Ada`).
- `SettingsPage.rename_to(name)` fills `settings-display-name`; if `settings-save` is disabled
  the value is already Alan's name (a `KEEP_STACK` rerun) and it returns; otherwise it clicks and
  waits for `settings-saved`.
- **Red:** `uv run pytest tests/bdd --collect-only -q` collects it; `--generate-missing` prints
  nothing. At the code-writer's first e2e run, before Task 8, it fails waiting for
  `settings-display-name`.

## Task 5: Names, the key and the migration (GREEN)

**Files:** `names.py`, `preferences.py` (pure part and `read`/`merge`), `models.py`,
`migrations.py`, `alembic/versions/0002_unique_names_and_preferences.py`

```python
# models.py — every write of a name writes its key (Decision 16)
display_name_key: Mapped[str] = mapped_column(String, nullable=False)

@validates("display_name")
def _keyed(self, _key: str, value: str) -> str:
    self.display_name_key = names.name_key(value)
    return value
# __table_args__ = (Index("ux_users_display_name_key", "display_name_key", unique=True),)  — not partial
```

```python
# 0002 upgrade — in this order, one transaction
op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))
rows = conn.execute(sa.text("SELECT id, display_name FROM users ORDER BY created_at, id")).all()
changed = names.dedupe(rows)                       # the same code as Req 1 (Req 4)
# UPDATE each changed name; then display_name_key = names.name_key(name) for every row
op.alter_column("users", "display_name_key", nullable=False)
op.create_index("ux_users_display_name_key", "users", ["display_name_key"], unique=True)
op.create_table("user_preferences",
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()))
# downgrade drops the table, the index and the column; renamed names are not restored (one-way)
```

- [ ] `names.py` and the pure `preferences.py` to Task 1. Run Task 1: all pass.
- [ ] Model, `UserPreferences`, `upgrade_to`, migration. Run `test_migration_0002.py` and
  `test_schema.py`: pass.
- [ ] Leave uncommitted.

## Task 6: Provisioning and the routes (GREEN)

- [ ] `identities.provision_user`: `base = names.from_idp(display_name, email)`; for each
  `names.candidates(base)`: `async with session.begin_nested(): add + flush`; on the name-index
  `IntegrityError` (Decision 17's test, one helper `_is_name_taken(exc)`) continue; the workspace
  is `f"{user.display_name}'s Workspace"`. Nothing logged with the name.
- [ ] `routers/users.py` `update_me`: `names.normalise_display_name` → 400
  `errors={"displayName": [str(exc)]}`; same stored form → return without writing; else assign,
  `flush()`, name-index violation → `rollback()` and 409 `ProblemException.conflict(MSG,
  errors={"displayName": [MSG]})`. `schemas.UpdateUserRequest.display_name: str | None = None`.
- [ ] `GET`/`PATCH /me/preferences`, declared **before** `/{user_id}`; `find_user` first (404);
  PATCH body `dict[str, Any] = Body(...)`, `parse_patch` → 400 `errors=exc.errors`; `merge`; commit.
- [ ] Run Task 2: all pass. Auth integration whole: green.
- [ ] Leave uncommitted.

## Task 7: The SPA's plumbing (GREEN)

- [ ] `api.ts`, `session.ts` (`updateProfile`, the `adopt` guard, `signIn(provider, returnTo)`, `takeReturnPath`),
  `storage.ts` (`returnPath` beside `pkceVerifier`, same lifetime and comment), `lib/time.ts`,
  `stores/chat.ts`. Run `time.test.ts`, `session.test.ts`: pass.
- [ ] Leave uncommitted.

## Task 8: The page and the clock (GREEN)

- [ ] `usePreferences.ts` (Decisions 30, 42), `useProfile.ts` — the hook-level `onSuccess` of the
  rename calls `session.updateProfile` and `applyRename` (Decisions 31–32).
- [ ] `SettingsPage.tsx`; `App.tsx` route `/settings` under `Protected` with a `SettingsRoute`
  like `SearchRoute`; `Protected` passes `state={{ from: pathname + search }}`; `SignIn` passes
  it to `session.signIn`; `Callback` navigates to `session.takeReturnPath()`.
- [ ] `WorkspaceSwitcher.tsx`: `current-user` a `<Link to="/settings">`. `ChatLayout.tsx`:
  `usePreferences(current.accessToken)` to prime the clock; its workspace cleanup also
  `setLastChannel(null)`. `ChannelView.tsx`: `setLastChannel(channelId)` beside
  `setActiveChannel`.
- [ ] `MessageItem`, `ThreadSummary`, `SearchResult`: `useClock()` → `formatTime` /
  `formatDateTime`; delete the local `timeOfDay` / `when`.
- [ ] Task 3 passes; `npm --prefix src/frontend run typecheck` clean; the existing
  `MessageItem.test.tsx` still passes (no clock = today's output).
- [ ] Leave uncommitted.

## Task 9: The record

- [ ] Register: **D28** 🟢 with Decided 7 and this plan's 25–28; new **D46** 🟢 in *Platform /
  Auth* — global unique names, the leak accepted, the key column (Decisions 14–15).
- [ ] Two ADRs with the `adr-writer` skill: preferences in Auth, per user, validated keys;
  global uniqueness over tenancy, with the key computed in the application.
- [ ] Conventions §5.4: the D46 exception — a display-name 409 may reveal that a name exists in
  another workspace, and names nobody and no workspace.
- [ ] Doc 01: §3 table — the two preferences routes, the 400/409 on `PATCH /users/me`, payloads;
  §4 — `display_name_key`, `ux_users_display_name_key`, `user_preferences`; §5.1 — the suffix
  rule and the IdP-name fallback.
- [ ] Doc 06: §3 `/features/settings`; §4 the return path; §5.2 *Names* — the renamer's own tab
  updates at once, everyone else as before; §9 — D28 decided.
- [ ] Vocabulary: a ruling §35 for `settings.feature` — Alan as the third persona by the issue's
  decision, the four new phrases.
- [ ] Stale text: `MessageItem.tsx:10-16`, `SearchResult.tsx:7-8`, `ThreadSummary.tsx:6-7`
  (D28 "open"/browser locale only); `schemas.py:129-133`; `identities.provision_user` and
  `users.update_me` docstrings; `grep -rn "D28" src docs/design` for any other "open".

## Task 10: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each layer once; the
  whole e2e layer is the journey's first run (`-- -k settings` only to iterate). Counts at or
  above the baseline; record Auth's integration count.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; a waiver names every checker that fires on its line.
- [ ] **First real run** (`docker compose up -d --build`): rename Ada, try `GRACE` as Alan, choose
  24-hour, reload and sign out on `/settings`; fix what the tests missed, with a test, below.
- [ ] Fill in *Found while building*. Leave the worktree dirty.

## Found while building

*Filled in by the code-writer: every deviation from this plan, and every bug the first real run
found, each with the test that now pins it down. Empty until then.*

## Not in this plan

- Live push of a rename; another user's or a workspace's rename; lookalike detection.
- Any preference but `clock`; Auth's OpenAPI types; an avatar editor; the token's `name` claim.

## Self-review

- **Issue coverage:** Req 1 → T1, T2, T6; Req 2 → T2 (409, NFC, capitals, deleted, races), T5–6;
  Req 3 → T1 (`candidates`, `from_idp`), T2 (sign-ins), T6; Req 4 → T1 `dedupe`, T2 migration;
  Req 5 → T3 `useProfile`, `session`, T4; Req 6 → T1, T2 `test_preferences*`; Req 7 → T3 time,
  three components, `usePreferences`; Req 8 → T3 `SettingsPage`, `App`. Where the rules meet 1–7
  → T2 races, sign-in race, T3 `useProfile`/`session`, token, workspace, `MessageItem.clock`,
  merge. Paths 1–8 → `shows only what this visit fetched`, `App` signed-out + callback, unmount,
  remount (no prompt to test), `a new token…`, Decisions 28/40, `useWorkspaceMembers.test.tsx`
  plus the journey, T2 deleted name and 404.
- **Names:** `display_name_key`, `ux_users_display_name_key`, `user_preferences`,
  `['preferences']`, `['profile','me']`, `collabhub.returnPath` — the same everywhere.
- **Known ripple:** `test_schema.py`'s default name (Task 2); `MessageItem.test.tsx` holds (no
  clock = today's options); four `ChatLayout`-mounting files gain a preferences stub (Task 3).
- **Writers of the same state**, each pair tested: session profile — `adopt`, `updateProfile`
  (39); directories and `['profile','me']` — their queries, `applyRename` (32); `['preferences']`
  — its query, `useUpdateClock` (30).

## Review responses

Round 1: 1 fixed — Decisions 39 (`adopt` guard), 32 (write then invalidate), 30 (cancel in
`onMutate`, invalidate in the last `onSettled`), with three in-flight tests in Task 3. 2 fixed —
Decision 42 (`useClock` reads only) and Task 3's *Known ripple* naming the four files. 3 fixed —
Decision 30, test `two failed choices end on what the server holds`. 4 fixed — Decision 41.
5 fixed — Decision 24, `test_the_same_name_with_a_new_avatar_saves_the_avatar`. 6 fixed —
Decision 19, `test_an_idp_name_is_composed_after_dropping`. 7 fixed — Decision 40, **assumed**.
8 fixed — Decision 36, a 60-emoji name in the Save test. 9 fixed — Task 2's sync `at_0001`.
