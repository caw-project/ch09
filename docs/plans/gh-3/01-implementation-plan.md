# Display names, unique names and a preferences page — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A signed-in user renames themselves on a new `/settings` page; display names are unique
across CollabHub, case-insensitively; the same page sets the first per-user preference, a 12/24-hour
clock, stored by Auth (D28).

**Architecture:** One unique expression index on `lower(display_name)` is the only arbiter of
uniqueness — the rename route turns its violation into a 409, first sign-in walks `X`, `X 2`, `X 3`…
inside savepoints until an insert holds, and migration `0002` renames existing duplicates before
creating it. A pure `auth.names` module owns trimming, validation and the suffix rule. A
`user_preferences` row per user is merged by one `INSERT … ON CONFLICT … SET prefs = (prefs || new) -
removed`, so concurrent writers of different keys both land. The SPA gets a Settings feature: a
mutation that writes the session profile and every cached workspace directory on success, a
`['preferences']` query the three time formatters read through one hook, and a return-to-path for
sign-in.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, Postgres 18, pytest +
testcontainers + real Dex · React 19, React Router, TanStack Query 5.101, Vitest + MSW · pytest-bdd +
Playwright.

**Issue:** `docs/plans/gh-3/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `/home/runner/work/ch09/caw-gh-3`, branch `feature/gh-3`, from `main` at `0ac4c21`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | Req 1–8; *Not in this issue* stays out |
| 2 | Who renames whom | Only yourself; the row comes from the token's `sub` (already so, `routers/users.py:45-55`) |
| 3 | Uniqueness | Global, trimmed, case-insensitive, deleted accounts included — new **D46**, accepting that a 409 reveals a name exists somewhere; it names nobody and no workspace |
| 4 | Lookalikes | TR39 confusables are a known gap; only case and invisible characters are handled |
| 5 | Live rename | No broadcast; others see it on their next directory refetch |
| 6 | Preferences | **D28 🟢**: Auth's `user_preferences` (`user_id`, `prefs jsonb`, `version`, `updated_at`), per user, server-validated keys; SPA holds them in TanStack Query |
| 7 | The one preference | `clock`: `"12h"`, `"24h"` or absent (Automatic) |
| 8 | R1 down | Both PATCH routes stay on `require_user` and fail open |
| 9 | Client types | Hand-typed in `lib/auth/api.ts`: `updateMe`, `preferences`, `updatePreferences` |
| 10 | Logs | No display name in any log call (CH008) |
| 11 | Existing duplicates | Migration renames all but the oldest (`created_at`) by Req 3's rule — one-way |
| 12 | The journey's third person | Alan, with an `alan` context beside `ada` and `grace`; his name is not restored |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 13 | How uniqueness is enforced | `CREATE UNIQUE INDEX uq_users_display_name ON users (lower(display_name))`. Trimming is guaranteed by every writer (route, provisioning, migration all go through `auth.names`), not by the index expression | `btrim()` in the index trims only spaces while Python's `str.strip()` trims all Unicode whitespace; two trims that disagree are worse than one. A pre-check `SELECT` alone can't close the race — only the index can |
| 14 | `lower()` vs full case folding — **assumed** | `lower()`. Under `postgres:18`'s default `en_US.utf8` collation it maps accented capitals (`É`→`é`), which Task 2 proves on the real image; it does not fold `ß`/`SS`, final sigma or dotless `ı`, accepted beside the confusables gap (decision 4) | The issue asks whether it matters. Changing later is one migration recreating the index on another expression, after renaming any pair the new rule makes collide |
| 15 | Telling our conflict from another | `identities.is_display_name_conflict(exc)`: `getattr(exc.orig.__cause__, "constraint_name", None) == "uq_users_display_name"`. SQLAlchemy's asyncpg adaptor raises its translated error `from` asyncpg's (`sqlalchemy/dialects/postgresql/asyncpg.py:781-797`, installed), and asyncpg's `UniqueViolationError` carries `constraint_name` | An email-uniqueness violation in the same insert must still be an error, not a name retry |
| 16 | First sign-in under a race | For each candidate: skip it if `lower()`-equal to any row's (deleted included); else insert inside `session.begin_nested()`, and on a name conflict move to the next. No cap — the table is finite | The pre-check keeps the common case to one insert; the savepoint makes a lost race a retry rather than a failed sign-in (Req 3, *Where the rules meet* row 2) |
| 17 | Characters refused — **assumed** | After trimming, any code point whose `unicodedata.category` is `Cc`, `Cf`, `Cs`, `Co`, `Cn`, `Zl` or `Zp` | The issue says "control … invisible format characters". `Cf` holds the zero-width and bidi marks; `Zl`/`Zp` are invisible line breaks. Narrowing to `Cc`+`Cf` later is one set literal and two tests |
| 18 | Length unit — **assumed** | Code points (`len()`), 1–100 after trimming | What Pydantic's old `max_length` counted. Graphemes would need a new dependency |
| 19 | The IdP's name — **assumed** | `names.provisional_name(raw)`: trim, drop refused characters, cut to 100, `"user"` if nothing is left; then the suffix rule. Also used by the migration for stored names that would now fail validation | Sign-in must never refuse over a name (Req 3), so a bad IdP name is cleaned, not rejected |
| 20 | Saving the name you have — **assumed** | 200 with the profile, and **no write**: `version` and `updated_at` unchanged | "Succeeds and changes nothing" (Req 1). Bumping `version` would be a change |
| 21 | The migration's rule — **assumed** | `0002` imports `auth.names` rather than a frozen copy | One suffix rule in one place; the alternative is two rules that drift. Cost: a later edit to `names` changes what `0002` would do on a fresh database with duplicates — there are none after it has run once |
| 22 | Which names a suffix may take — **assumed** | The migration reserves every stored name first, so a suffix never takes a name an account already holds, and no non-duplicate is renamed | The issue doesn't say; renaming someone who had no duplicate would be a surprise |
| 23 | A deleted oldest duplicate — **assumed** | It keeps the name; the live newer account is suffixed | Req 4 says "the oldest account" and Req 2 counts deleted accounts. The alternative is one `ORDER BY deleted_at IS NOT NULL, created_at` |
| 24 | Preferences wire shape | `GET`/`PATCH /api/v1/users/me/preferences` → `200 { "clock"?: "12h" \| "24h" }`, known keys only, absent when unset. PATCH with `{}` writes nothing | Req 6. A bare object, not an envelope: it is one user's settings, not a list |
| 25 | Return to `/settings` after sign-in — **assumed** | Built, for every protected route: the guard passes `from`, Sign in stores it in `sessionStorage` (`collabhub.returnTo`), the callback navigates there | The issue's assumption is false (*Corrections* 1) and its *Paths* row needs it. Undoing it is three small edits; the alternative was to record the row as not holding |
| 26 | Where `/settings` renders — **assumed** | Inside the chat shell (`Protected` → `ChatLayout`), sidebar visible | Reached from the sidebar's name, so the shell stays; and the shell owns the socket, which a round trip to Settings shouldn't drop |
| 27 | "Back to chat" — **assumed** | `location.state.from` when it starts with `/c/`, else `/`. The sidebar link passes it; history state survives a reload | `activeChannelId` is cleared when `ChannelView` unmounts (`ChannelView.tsx:38`), so the store can't say |
| 28 | Client-side validity — **assumed** | Save is disabled when the trimmed value equals the current name or its length is outside 1–100; the character rule is the server's, shown on the field | One rule mirrored, not two |
| 29 | The renamer's own view | The mutation's **hook-level** `onSuccess` calls `session.updateProfile`, `setQueriesData` on every `['workspace-members', *]` entry, then invalidates them. Hook-level callbacks run without observers (`@tanstack/query-core/build/modern/mutation.js:123`); `mutate()`-level ones only with listeners (`mutationObserver.js:77`) | Req 5 and the unmount *Path*. The invalidate closes the race with a directory fetch in flight (decision 30) |
| 30 | Other writers of the same state | `session.adopt()` also writes `profile`: it keeps the current profile when `updateProfile` ran while its `me` was in flight (an epoch counter). A directory fetch in flight with the old name is cancelled and replaced by the invalidate (`cancelRefetch` defaults true) | Both orders are tested (Task 3) |
| 31 | How the clock reaches the formatters | `ChatLayout` and the Settings page run `usePreferences`; `MessageItem`, `ThreadSummary` and `SearchResult` call `useClock()`, which subscribes to the query cache with `useSyncExternalStore` — no second `useQuery` | A skip-token observer could set the query's options for a later `refetchQueries`; a cache subscription can't fetch at all |
| 32 | Clock saves in a row | `useSetClock` mutations share `scope: { id: 'preferences' }`, so their requests run in order (`mutationCache.js:60-75`) while each `onMutate` still applies at once (`mutation.js:94-105`). Only the latest mutation's result is applied; if it fails, the value from before the burst comes back | The server then sees choices in the order made; out-of-order responses can't leave the screen on an older choice |
| 33 | 12/24 hours — **assumed** | `hourCycle: 'h12'` / `'h23'`; Automatic passes neither | `hour12: false` gives `24:05` past midnight in some ICU builds (`h24`) |
| 34 | Sign-out and the preferences cache — **assumed** | Not cleared; nothing clears the cache on sign-out today. A second user in the same tab sees the first's clock until `ChatLayout`'s mount fetch lands | Clearing the cache on sign-out is its own change across every key |
| 35 | Register | D28 🟢 and new D46 🟢, in the slice | Issue *Record in this slice* |
| 36 | A read in flight against an optimistic or confirmed write | `useSetClock`'s `onMutate` first `await queryClient.cancelQueries({ queryKey: ['preferences'] })`, then writes the choice; the **latest** mutation's `onSettled` invalidates `['preferences']`. `useUpdateDisplayName` does the same for `['profile','me']`: cancel in `onMutate`, `setQueryData` then invalidate on success. `onMutate` is awaited before the scoped request may start (`mutation.js:94-115`: `onMutate` at :102, `retryer.start()` — where `canRun` waits on the scope — at :115) | A focus or mount refetch started before the choice would otherwise land with the old value and flip the screen back (or leave it wrong if it lands after the PATCH). The cancel closes the read already in flight; the settle invalidate replaces one started while the PATCH was pending with a read of what the server committed. A refetch landing *during* a pending PATCH can still show the old value until the PATCH settles — accepted, a flicker that ends on the right value. The alternative, a long `staleTime` alone, only narrows the window |
| 37 | The sidebar's own name — **assumed** | `WorkspaceSwitcher` names the user from the active workspace's directory entry for `profile.id` (`useWorkspaceMembers(...).members`, not `nameFor`, so no tracker follow-up), falling back to `session.profile.displayName` while the directory has no entry | The issue's *Paths* row says a second tab sees the new name "on its next refetch", and its rule that the sidebar and one's own authors never disagree; `session.profile` alone changes only at a renewal or a reload (`session.ts:76-94`), so a second tab would show two names for up to a renewal. Reading the directory makes both change on the same fetch. The alternative — accept the gap until renewal or reload — is undone by reverting one component and one test |

Nothing here builds on a 🔴 entry. The nearest are **D18** (notification channels — a preference
the issue rules out) and **D38** (whether a failed renewal signs out): the return-to-path (decision
25) runs only after a successful exchange and leaves renewal untouched. **D16** is not touched: a
deleted account's name stays taken, and no tombstone is purged.

## Corrections to the issue

1. **"The SPA's sign-in returns to the route it started from" is false.** `Protected` sends a
   signed-out visitor to `/sign-in` with nothing remembered (`App.tsx:83`), and both the sign-in page
   and the callback go to `/` (`App.tsx:26`, `:63`). The *Paths* row "`/settings` while signed out"
   is built here (decision 25); doc 06 §4 is updated because `sessionStorage` then holds a second key.
2. **The scenario vocabulary says "Ada and Grace, and no one else"** (`00-scenario-vocabulary.md`
   §1, 🔴 for a third person). The issue's *Tests* decides Alan; Task 8 records the exception in §1.
3. Checked and kept as the issue says: an explicit `displayName: null` is a **400** (`users.py:61-65`,
   `test_users.py:101-109`); `provision_user` is the only place outside tests that builds a `User`
   (`identities.py:101`) and `link_identity` its only caller (`identities.py:168`).

## Test approach — recommendation to the test pair

**BDD outside-in, one journey.** A Settings page is a new capability a user sees, and only a real
browser proves a rename made by one user reaches another's screen through Auth. Everything under it
goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Alan renames himself on Settings; Grace, after a reload, sees the new name on his message | **BDD** | `tests/bdd/features/display_names.feature` |
| Trim, length, refused characters, cleaning an IdP name, the suffix sequence | unit | `auth/tests/unit/test_display_name_rules.py` |
| The preferences patch: known keys, values, `null` as removal | unit | `auth/tests/unit/test_preference_rules.py` |
| Rename: 400s, 409 (case, deleted, accented), own capitals, no-op, both races | integration | `auth/tests/integration/test_display_names.py` |
| First sign-in suffixing, its race, its workspace name, never overwriting | integration | `auth/tests/integration/test_first_sign_in_names.py` |
| Migration `0002` on duplicate data | integration | `auth/tests/integration/test_name_migration.py` |
| Preferences routes, merge atomicity, 404, per-user across a workspace switch | integration | `auth/tests/integration/test_preferences_api.py` |
| Both PATCH routes with R1 down | integration | `auth/tests/integration/test_r1_unreachable.py` |
| The three formatters' rule | Vitest | `lib/time.test.ts` |
| Return path; `updateProfile` and its race with renewal | Vitest | `lib/auth/storage.test.ts`, `lib/auth/session.test.ts` |
| The form, the clock control, Back to chat | Vitest | `features/settings/SettingsPage.test.tsx` |
| Own-view update, unmount, directory race; clock optimism and bursts | Vitest | `features/settings/useProfile.test.tsx`, `usePreferences.test.tsx` |
| Each formatter follows the clock; `/settings` routes; the sidebar link | Vitest | `MessageItem.test.tsx`, `ThreadSummary.test.tsx`, `SearchResult.test.tsx`, `App.test.tsx`, `ChatLayout.test.tsx` |

**What no test covers:** that an edit left unsaved is dropped without a warning — it is component
state, and nothing is written to keep it; Postgres folding `ß` (decision 14, a gap by choice); the
two-tab "last write wins" on one key beyond the sequential test, because one statement per write
gives it by construction; the `name` claim staying stale until refresh, which the issue leaves.

**Baseline**, from `docs/test-report.md` at `3daf13a` (dirty): Auth unit 59 passed, frontend
(Vitest) 503 passed. Auth integration and end-to-end have no recorded run there — that report's
integration layer ran `tools/delivery` only — so their baseline is this branch's first full run.
Expected counts are "N or more".

## Global constraints

- Auth has no workspace in these routes: everything keys on the token's `sub`; there is no id in any
  body (CH001). The 409's `detail` and `errors` are the fixed string `"That name is already taken."`
  and nothing else — no user, email or workspace.
- `require_user` on all three routes, never `require_user_sensitive` (decision 8).
- The name check reads **deleted rows on purpose**; that `select()` carries a CH009 waiver comment
  saying so (`# conventions: ok — a deleted account's name stays taken (D46).`).
- No display name in a log call (CH008), including the migration.
- `user_preferences.user_id` has a real foreign key to `users.id` — both are Auth's.
- No new environment variable. No chart change: `/api/v1/users` is already in the Ingress allow-list
  (`charts/collabhub/templates/ingress.yaml:50`, checked), and `/settings` falls through to the
  SPA's `location /` as `/search` does (`docker/frontend/nginx.conf:12`).
- TanStack Query owns profile and preferences; nothing goes in Zustand (D24).

## File map

| File | Change | Responsibility | Task |
|---|---|---|---|
| `auth/tests/unit/test_display_name_rules.py` · `test_preference_rules.py` | create | the rules | 1 |
| `auth/tests/integration/test_display_names.py` · `test_first_sign_in_names.py` · `test_name_migration.py` · `test_preferences_api.py` | create | routes, SQL, races, migration | 2 |
| `auth/tests/integration/test_r1_unreachable.py` | modify | two fail-open tests | 2 |
| `frontend/src/test/api.ts` | modify | Auth stubs for the new calls; a default, unrecorded `GET …/me/preferences → {}` | 3 |
| `lib/time.test.ts` · `lib/auth/storage.test.ts` · `features/settings/*.test.tsx` · `ThreadSummary.test.tsx` · `SearchResult.test.tsx` | create | the SPA's red | 3 |
| `lib/auth/session.test.ts` · `App.test.tsx` · `ChatLayout.test.tsx` · `MessageItem.test.tsx` | modify | the SPA's red | 3 |
| `tests/bdd/features/display_names.feature` · `steps/test_display_name_steps.py` | create | the journey | 4 |
| `tests/bdd/conftest.py` · `pages/chat_page.py` | modify | `alan_context`/`alan`; `rename_self`, `own_name` | 4 |
| `auth/auth/names.py` | create | `validate_display_name`, `provisional_name`, `candidates`, `InvalidDisplayNameError` | 5 |
| `auth/auth/alembic/versions/0002_unique_display_names_and_preferences.py` | create | clean, dedupe, index, table | 5 |
| `auth/auth/models.py` · `migrations.py` | modify | `UserPreferences`, the index on `User`; `upgrade(dsn, revision)` | 5 |
| `auth/auth/identities.py` | modify | suffixing `provision_user`, `is_display_name_conflict`, `display_name_taken` | 5 |
| `auth/tests/integration/conftest.py` | modify | `TABLES` gains `"user_preferences"` first — **GREEN, not RED**: at red the table doesn't exist and truncating it would error every Auth integration test | 5 |
| `auth/tests/integration/test_schema.py` | modify | `a_user` names each user from its email, so `test_email_uniqueness_ignores_case` hits `citext`, not the name index, and asserts `is_display_name_conflict(exc.value)` is `False` — **GREEN**, with the index | 5 |
| `auth/auth/preferences.py` | create | `PreferencesPatch`, `split`, `read`, `merge` | 6 |
| `auth/auth/routers/users.py` · `routers/preferences.py` · `schemas.py` · `main.py` | modify · create · modify · modify | rename rules; two routes; models; registration | 6 |
| `lib/auth/api.ts` · `storage.ts` · `session.ts` | modify | the calls; `returnPath`; `updateProfile`, `signIn(…, returnTo)` | 7 |
| `lib/time.ts` · `features/settings/{SettingsPage.tsx,useProfile.ts,usePreferences.ts}` | create | formatters; the feature | 7 |
| `App.tsx` · `features/channels/WorkspaceSwitcher.tsx` · `ChatLayout.tsx` · `MessageItem.tsx` · `ThreadSummary.tsx` · `SearchResult.tsx` | modify | route and return; the link; fetch; formatters | 7 |
| `docs/design/01-auth-service.md` · `06-frontend-spa.md` · `07-open-decisions-register.md` · two ADRs · `CLAUDE.md` · `README.md` · `src/frontend/README.md` · `src/frontend/src/index.css` · `00-scenario-vocabulary.md` | modify · create | the record | 8 |

Deliberately unchanged: `tests/bdd/conftest.py`'s truncation — it never touches Auth, so Alan's name
and everyone's preferences survive between scenarios, which the journey relies on; `oidc.py` — the
name fallback chain stays, cleaning happens in `provision_user`; `sessions.py` — the `name` claim
reads `user.display_name` and needs nothing; the generated OpenAPI files — Auth has none. Existing
SPA tests that render `ChatLayout` (`ChatLayout*.test.tsx`, `App.test.tsx`) need no new stub because
of the default handler in `test/api.ts`, which records nothing so request-order assertions hold.

Paths are relative to `src/services/` and `src/frontend/src/` where shortened.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing unit, integration, Vitest and BDD tests, each for the reason given — **test-reviewer gate** |
| GREEN — Auth | 5–6 | code-writer | Tasks 1–2 pass |
| GREEN — SPA | 7 | code-writer | Task 3 passes, `tsc` clean |
| Finish | 8–9 | code-writer | the record, then verification (the journey's first run) |

One red phase: Auth has no generated types, so the SPA's stubs type against the interfaces Task 3
adds to `test/api.ts` from Task 7's contract below, and `tsc` is red for the same reason as the tests.

---

## Task 1: The rules (RED)

**Files:** `auth/tests/unit/test_display_name_rules.py`, `auth/tests/unit/test_preference_rules.py`

**Interfaces** — `auth.names`:
- `MAX_LENGTH = 100`; `class InvalidDisplayNameError(ValueError)` with `.message: str`
- `validate_display_name(raw: str) -> str` — trimmed name, or raises with one of: `"A display name
  is required."`, `"A display name is at most 100 characters."`, `"A display name cannot contain
  control or invisible characters."`
- `provisional_name(raw: str) -> str` — decision 19; never raises, never empty
- `candidates(base: str) -> Iterator[str]` — `base`, then `f"{stem} {n}"` for `n = 2, 3, …`, where
  `stem` is `base` cut (and right-stripped) so each candidate is ≤ 100

`auth.preferences`:
- `class PreferencesPatch(CamelRequest)` with `model_config` adding `extra="forbid"`;
  `clock: Literal["12h", "24h"] | None = None`
- `split(patch: PreferencesPatch) -> tuple[dict[str, str], list[str]]` — keys to set, keys to remove
  (`null`), from `model_fields_set` only

| Test | Proves | Expected red |
|---|---|---|
| `test_a_name_is_trimmed` | `"  Ada L  "` → `"Ada L"`, inner spaces kept | `ModuleNotFoundError: No module named 'auth.names'` (whole file) |
| `test_a_blank_name_is_required` | `""` and `"   "` both raise the *required* message | same |
| `test_length_is_counted_after_trimming` | 100 chars + 2 spaces passes; 101 chars raises the *length* message | same |
| `test_invisible_and_control_characters_are_refused` | `"Ada​"` (Cf), `"Ada\x07"` (Cc), `"Ada "` (Zl) raise; `"Émile"` and `"Ada 🚀"` pass | same |
| `test_an_idp_name_is_cleaned_not_refused` | `" Sam​ "` → `"Sam"`; 120 chars → 100; `"​"` → `"user"` | same |
| `test_suffixes_start_at_two` | first three of `candidates("Sam")` are `Sam`, `Sam 2`, `Sam 3` | same |
| `test_a_suffix_never_makes_a_name_too_long` | for a 100-char base, candidate 2 and candidate 10 are each ≤ 100 and end `" 2"` / `" 10"` | same |
| `test_a_patch_sets_a_known_key` | `{"clock": "24h"}` → `({"clock": "24h"}, [])` | `ModuleNotFoundError: … 'auth.preferences'` |
| `test_null_removes_a_key_and_absence_leaves_it` | `{"clock": None}` → `({}, ["clock"])`; `{}` → `({}, [])` | same |
| `test_an_unknown_key_is_refused_by_name` | `{"theme": "dark"}` raises `ValidationError` whose `loc` is `("theme",)` | same |
| `test_a_bad_value_is_refused_by_key` | `{"clock": "13h"}` raises with `loc` `("clock",)` | same |

House docstrings, one line each on what breaks without the rule (`auth/tests/unit/test_tokens.py`
style). No database, no session.

## Task 2: The routes, the SQL, the races and the migration (RED)

**Files:** the four new integration files, and `test_r1_unreachable.py`.

**Interfaces** — the wire contract Tasks 3 and 6 share:

```
PATCH /api/v1/users/me          { displayName?, avatarAsset? }   → 200 UserResponse (unchanged shape)
  invalid name  → 400  errors.displayName: [<names message>]
  taken name    → 409  detail "That name is already taken.", errors.displayName: ["That name is already taken."]
GET   /api/v1/users/me/preferences                               → 200 { clock?: "12h" | "24h" }
PATCH /api/v1/users/me/preferences  { clock?: "12h"|"24h"|null } → 200 the merged object
  unknown key / bad value → 400 errors.<key>; deleted account → 404 detail "This account no longer exists."
```

`auth.migrations.upgrade(dsn: str, revision: str = "head") -> None` (async); `upgrade_to_head(dsn)`
stays and calls it. Revision `"0002"`, `down_revision = "0001"`.

Helpers each file defines for itself (no cross-file `tests` imports, TID251): `sign_in`/`bearer` as
`test_users.py:24-29`; `delete_account` as `test_deleted_accounts.py:29-34`; `waiting_on_a_lock(sessions)`
— polls `SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND datname =
current_database()` every 50 ms for up to 5 s and returns whether it saw one; a racing test that
needs the block asserts it is `True` before releasing.

`test_display_names.py` — through the app with real Dex (`ADA`, `GRACE`, `ALAN` sign in as `ada`,
`grace`, `alan`):

| Test | Proves | Expected red |
|---|---|---|
| `test_a_name_is_stored_trimmed` | PATCH `"  Ada L  "` → 200 `"Ada L"`, and `GET /users/me` says so | `assert '  Ada L  ' == 'Ada L'` |
| `test_a_blank_name_is_400_and_nothing_changes` | `"   "` → 400 with `errors["displayName"]`; name still `"ada"` | `assert 200 == 400` |
| `test_length_is_counted_after_trimming` | 100 chars padded with spaces → 200; 101 chars → 400 | `assert 400 == 200` (Pydantic counts the padding) |
| `test_an_invisible_character_is_400` | `"Ada​"` → 400 `errors["displayName"]` | `assert 200 == 400` |
| `test_a_taken_name_is_409_and_names_nobody` | Ada → `"grace"`: 409, `detail` and `errors` exactly as the contract; the body contains no `@`, no user id and no `"Workspace"`; Ada still `"ada"` | `assert 200 == 409` |
| `test_your_own_capitals_are_free_and_nobody_elses_are` | Ada → `"ADA"` 200; then Grace → `"ada"` 409 | second half: `assert 200 == 409` |
| `test_case_folding_covers_accented_capitals` | Grace → `"Émile"` 200; Alan → `"émile"` 409 | `assert 200 == 409` |
| `test_saving_the_name_you_have_changes_nothing` | PATCH `"ada"` → 200; `users.version` and `updated_at` (read with `sessions`) unchanged; then PATCH `"ada b"` bumps `version` | `version` 0 → 1 on the no-op |
| `test_a_deleted_accounts_name_stays_taken` | Grace signs in, is deleted; Ada → `"grace"` 409; Ada → `"grace hopper"` 200 | `assert 200 == 409` |
| `test_two_renames_to_one_name_at_once` | Grace and Alan PATCH `"Sam"` under `asyncio.gather`: statuses sort to `[200, 409]`; exactly one row has `lower(display_name) = 'sam'` | `[200, 200]` |
| `test_a_rename_waits_on_a_sign_up_holding_the_name` | a second session runs `provision_user(email="sam@example.com", display_name="Sam", demo_workspace_name=None)` and holds its transaction open; Ada's PATCH `"Sam"` blocks (`waiting_on_a_lock` is `True`); the session commits; the PATCH is 409 | `waiting_on_a_lock` is `False` — the PATCH returned 200 without blocking |
| `test_a_sign_up_after_a_rename_takes_a_suffix` | Ada → `"Sam"`; then `provision_user(…, display_name="Sam")` → `"Sam 2"` | `assert 'Sam' == 'Sam 2'` |

`test_first_sign_in_names.py` — mostly `identities.provision_user` on `sessions`, rows inserted with
`User(id=uuid7(), …)`:

| Test | Proves | Expected red |
|---|---|---|
| `test_the_first_free_suffix_is_taken` | with `Sam`, `Sam 2`, `Sam 4` stored, a new `Sam` becomes `Sam 3` — not `Sam 4`/`Sam 5`, which a count would give | `assert 'Sam' == 'Sam 3'` |
| `test_suffixing_ignores_case` | with `sam` stored, `SAM` becomes `SAM 2` | `'SAM' == 'SAM 2'` |
| `test_a_deleted_accounts_name_is_skipped` | a deleted `Sam` stored; a new `Sam` becomes `Sam 2` | `'Sam' == 'Sam 2'` |
| `test_the_own_workspace_is_named_from_the_result` | the new user's owned workspace is `"Sam 3's Workspace"` | `"Sam's Workspace"` |
| `test_an_idp_name_is_cleaned` | `" Sam​ "` provisions as `Sam` | stored raw |
| `test_two_first_sign_ins_with_one_name` | `demo_workspace_name=None` on both, so the only lock is the name's (`ensure_demo_workspace`'s advisory lock would block at red too); two sessions provision `Sam` (distinct emails); the first holds its transaction, the second blocks (`waiting_on_a_lock`), the first commits, the second commits: names are `{"Sam", "Sam 2"}` | the second never blocks: `False` |
| `test_a_first_sign_in_through_dex_takes_a_suffix` | Grace signs in and renames to `"ada"`; Ada's first sign-in: `/users/me` is `"ada 2"` and `/workspaces` lists `"ada 2's Workspace"` | `'ada' == 'ada 2'` |
| `test_sign_in_never_overwrites_a_name` | Ada signs in, renames to `"Ada L"`, signs in again: still `"Ada L"` | **passes at red** — the guard for Task 5's rewrite of `provision_user`; paired in-file with the suffix tests above |

`test_name_migration.py` — a **sync**, function-scoped fixture `at_0001` returns
`service_database(postgres_server, f"auth_mig_{uuid4().hex[:8]}", partial(upgrade, revision="0001"))`
(sync because it calls `asyncio.run`, `testkit/databases.py:46-48`); the async test inserts rows in SQL,
then `await upgrade(dsn, "0002")`. `upgrade` is imported at module level: all four need it:

| Test | Proves | Expected red |
|---|---|---|
| `test_duplicates_are_renamed_and_the_oldest_keeps_its_name` | rows by `created_at`: `Sam`, `sam`, `" SAM "`, `Sam 2`, `Bob` → `Sam`, `sam 3`, `SAM 4`, `Sam 2`, `Bob` (decision 22: `Sam 2` is reserved, and `sam 3` is taken when `SAM` is reached) | `ImportError: cannot import name 'upgrade' from 'auth.migrations'` (whole file) |
| `test_a_deleted_oldest_keeps_its_name` | deleted `Ann` (older) and live `ann` → live becomes `ann 2` | same |
| `test_stored_names_are_cleaned` | `"Zed​"` → `Zed`; `"   "` → `user` | same |
| `test_afterwards_a_duplicate_cannot_be_inserted` | inserting `BOB` raises `IntegrityError`; inserting `Bobby` does not | same |

`test_preferences_api.py`:

| Test | Proves | Expected red |
|---|---|---|
| `test_no_preferences_read_as_an_empty_object_and_create_no_row` | GET → 200 `{}`; `SELECT count(*) FROM user_preferences` is 0 | `assert 404 == 200` |
| `test_a_patch_is_read_back` | PATCH `{"clock": "24h"}` → 200 `{"clock": "24h"}`; GET the same | `404` |
| `test_null_removes_a_key` | set `24h`, PATCH `{"clock": null}` → `{}`; GET `{}` | `404` |
| `test_an_unknown_key_is_400_and_nothing_changes` | set `24h`; PATCH `{"theme": "dark"}` → 400 with `errors["theme"]`; GET still `24h` | `404` |
| `test_a_bad_value_is_400_and_nothing_changes` | set `24h`; PATCH `{"clock": "13h"}` → 400 `errors["clock"]`; GET still `24h` | `404` |
| `test_merges_of_different_keys_both_land[with_row]` · `[without_row]` | Ada signed in (so her `users` row exists); `with_row` first stores `{"c": "0"}`. Session A runs `preferences.merge(…, {"a": "1"}, [])` and **holds its transaction open**; session B's `merge(…, {"b": "2"}, [])` runs as a task and must block (`waiting_on_a_lock` is `True`); A commits; B finishes and commits. Stored: `{"a": "1", "b": "2"}` plus `"c": "0"` with the row. Then, `with_row` only, a third merge `{"a": "3"}` → `a` is `"3"` (one key: last write wins). A read-modify-write build loses `a` (with a row) or raises a primary-key `IntegrityError` (without) | `ModuleNotFoundError: No module named 'auth.preferences'` — from `from auth import preferences` **inside the test body**, so only these two fail at load and the file's other tests reach their own reds |
| `test_preferences_are_per_user_not_per_workspace` | Ada sets `24h`, switches workspace (`/auth/switch-workspace` with `session_cookie`), GET → `24h`; Grace's GET → `{}` | `404` |
| `test_a_deleted_account_gets_404_on_both` | GET and PATCH → 404 with `detail == "This account no longer exists."` — the detail is what a missing route lacks | `KeyError: 'detail'` |
| `test_preferences_need_a_token` | GET and PATCH without a token → 401 | `assert 404 == 401` |

`test_r1_unreachable.py` (add, with its `reachable`/`r1_down` fixtures):
`test_a_rename_fails_open` (PATCH `/users/me` → 200 under `r1_down`) — **passes at red**, the guard
that Task 6 keeps `require_user`; `test_a_preferences_patch_fails_open` → red `assert 404 == 200`.

## Task 3: The SPA's red (RED)

**Files:** as the file map. Install first (`npm --prefix src/frontend ci`). The SPA contract, which
Task 7 builds:

```ts
// lib/auth/api.ts
export type Clock = '12h' | '24h'
export interface Preferences { clock?: Clock }
export function updateMe(accessToken: string, body: { displayName: string }): Promise<Profile>   // PATCH /api/v1/users/me
export function preferences(accessToken: string): Promise<Preferences>                         // GET  /api/v1/users/me/preferences
export function updatePreferences(accessToken: string, patch: { clock: Clock | null }): Promise<Preferences>
// lib/auth/storage.ts — key 'collabhub.returnTo'
export const returnPath: { write(path: string | null | undefined): void; take(): string | null }
//   write(null|undefined) clears; take() reads and clears; both drop anything that does not start
//   with '/', starts with '//' or '/\', or is '/sign-in' or begins '/auth/callback'
// lib/auth/session.ts
export function updateProfile(profile: api.Profile): void   // replaces session.profile when signed in as profile.id; else nothing
export async function signIn(provider = 'dex', returnTo?: string): Promise<void>  // returnPath.write(returnTo) before leaving
// lib/time.ts
export function timeOfDay(iso: string, clock?: Clock, locale?: string): string     // { hour: '2-digit', minute: '2-digit' }
export function dateAndTime(iso: string, clock?: Clock, locale?: string): string   // { dateStyle: 'medium', timeStyle: 'short' }
// features/settings/usePreferences.ts
export const preferenceKeys: { mine: () => readonly ['preferences'] }
export function usePreferences(accessToken: string, options?: { refetchOnMount?: 'always' }): UseQueryResult<Preferences>
export function useClock(): Clock | undefined
export function useSetClock(accessToken: string): UseMutationResult<Preferences, Error, Clock | null>
// features/settings/useProfile.ts
export const profileKeys: { me: () => readonly ['profile', 'me'] }
export function useProfile(accessToken: string): UseQueryResult<Profile>          // refetchOnMount: 'always'
export function useUpdateDisplayName(accessToken: string): UseMutationResult<Profile, Error, string>
// features/settings/SettingsPage.tsx
export function SettingsPage(props: { accessToken: string }): JSX.Element
```

**Markup the tests query** (no `data-testid` in Vitest): heading `Settings`; a `region`/section
headed `Profile` with a textbox labelled `Display name`, button `Save`, status text `Saved`
(`role="status"`), the field error as text; a group named `Clock` (`<fieldset>`/`<legend>`) of radios
`Automatic`, `12-hour`, `24-hour`, and its error as `role="alert"`; a link `Back to chat`. The sidebar
name is a link whose name is the display name. The BDD `data-testid`s (Task 4) sit on the same
elements: `current-user` (the link), `display-name-input`, `display-name-save`, `display-name-saved`.

**`test/api.ts`:** `auth.updateMe(reply | (body) => Profile | Promise<Profile>)`,
`auth.preferences(prefs)`, `auth.updatePreferences(reply | fn)` — recorded like the rest, a function
reply able to hold the response; and `setupServer(...)` gains one default handler,
`GET ${AUTH_URL}/api/v1/users/me/preferences → {}`, **not recorded**. `server.resetHandlers()`
keeps initial handlers, so it survives every test.

**Tests seed the cache with literal keys** — `['preferences']`, `['workspace-members', ws]` — never
an imported `preferenceKeys`, so `MessageItem.test.tsx`'s existing tests still load at red.
Times: build each message's ISO from `new Date(2026, 9, 16, 13, 5).toISOString()`, so local time is
13:05 in any time zone.

| File · test | Proves | Expected red |
|---|---|---|
| `time.test.ts` · `timeOfDay follows the clock in every locale` | for `en-US`, `en-GB`, `de-DE`: `24h` contains `13:05` and no `AM`/`PM`; `12h` does not contain `13` and contains `1:05` (`en-US` matches `/01:05\sPM/`) | `Failed to resolve import "./time"` |
| `time.test.ts` · `automatic is the browser's own format` | `timeOfDay(iso)` equals `new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })`; same for `dateAndTime` with `toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })` | same |
| `time.test.ts` · `dateAndTime follows the clock` | `24h` contains `13:05`; `12h` doesn't contain `13` | same |
| `storage.test.ts` · `a return path is taken once` | write `/settings`; `take()` → `/settings`, then `null` | `TypeError: Cannot read properties of undefined (reading 'write')` |
| `storage.test.ts` · `only a path on this origin is kept` | `//evil.test`, `https://evil.test`, `/\evil`, `/sign-in`, `/auth/callback?code=x` → `take()` `null`; `/c/abc?message=m` kept | same |
| `session.test.ts` · `updateProfile replaces the signed-in profile` | after `restore()`, `updateProfile({...profile, displayName: 'Ada L'})` → `snapshot().session.profile.displayName === 'Ada L'`; a profile with another `id` changes nothing | `session.updateProfile is not a function` |
| `session.test.ts` · `a renewal that fetched the old profile does not undo a rename` | hold the renewal's `GET /users/me` (old name); `updateProfile` new name; release → new name | same |
| `session.test.ts` · `a rename after a renewal stands` | the other order → new name | same |
| `session.test.ts` · `signIn keeps the path to return to` | `signIn('dex', '/settings')` with `location` stubbed (`:312-321` pattern) → `sessionStorage['collabhub.returnTo'] === '/settings'`; `signIn('dex')` clears it | `null` |
| `App.test.tsx` · `renders /settings on a direct load` | a returning user at `/settings` sees heading `Settings` | finds `No such page.` |
| `App.test.tsx` · `a signed-out visitor on /settings signs in and comes back` | first visit at `/settings` → `/sign-in`; clicking Sign in stores `/settings`; then a fresh App at `/auth/callback?code=c` with the verifier and stubs → `location().pathname === '/settings'` | stored `null`; then `'/'` |
| `App.test.tsx` · `a callback with nothing stored lands on /` | guard beside it | **passes at red** |
| `ChatLayout.test.tsx` · `the signed-in name links to Settings` | clicking the link named `Ada Lovelace` → `/settings` with `state.from` the current path | no link with that name |
| `ChatLayout.test.tsx` · `the sidebar names the user as the directory does` | session profile `Ada Lovelace`; the directory stub lists the user's own id as `Ada L` → the `current-user` link reads `Ada L`, and a message by her in the open channel reads `Ada L` too; with a directory that lacks her id → `Ada Lovelace` (decision 37) | first half finds `Ada Lovelace` |
| `SettingsPage.test.tsx` · `prefills the name the server has, not the session's` | cached `['profile','me']` says `Old`; the server says `Ada L`; the textbox shows `Ada L` and never `Old`; one `GET /users/me` recorded | module not found |
| `SettingsPage.test.tsx` · `Save is offered only for a changed, valid name` | disabled at the server's name, and at that name plus trailing spaces; enabled for `ADA L` (capitals only); disabled for `   ` and for 101 characters; enabled at 100 | same |
| `SettingsPage.test.tsx` · `a taken name is shown on the field` | 409 problem → `That name is already taken.` visible, the typed value kept, no `Saved` | same |
| `SettingsPage.test.tsx` · `a refused name is shown on the field` | 400 with `errors.displayName: ['A display name cannot contain control or invisible characters.']` → shown | same |
| `SettingsPage.test.tsx` · `a save says Saved and makes the new name the baseline` | PATCH body `{ displayName: 'Ada L' }` (trimmed); `Saved` shown; Save disabled; typing again hides `Saved` | same |
| `SettingsPage.test.tsx` · `the clock shows what the server holds` | prefs `{ clock: '24h' }` → `24-hour` checked; `{}` → `Automatic` | same |
| `SettingsPage.test.tsx` · `choosing a clock saves it at once` | `12-hour` → PATCH `{ clock: '12h' }`; `Automatic` → `{ clock: null }` | same |
| `SettingsPage.test.tsx` · `the clock is read from the server on every visit` | cache seeded `['preferences']` with `{ clock: '12h' }`; the server answers `{ clock: '24h' }` → `24-hour` ends checked, `12-hour` never is while the radios are enabled, and one `GET …/me/preferences` is recorded | same |
| `SettingsPage.test.tsx` · `a failed clock save puts the choice back and says so` | server `{ clock: '12h' }`; choose `24-hour`, PATCH answers 500 → `12-hour` checked again and a `role="alert"` with text is shown; then a successful choice hides the alert | same |
| `SettingsPage.test.tsx` · `Back to chat returns to the channel it came from` | with `state.from: '/c/abc'` → href `/c/abc`; with none, or `from: '/search'` → `/` | same |
| `SettingsPage.test.tsx` · `a workspace switch leaves the page as it is` | type an unsaved edit, rerender with a new `accessToken`: the edit stays, no new `GET /users/me` | same |
| `useProfile.test.tsx` · `a rename updates the session and every cached directory` | signed in via `restore()`; `['workspace-members', A]` and `[…, B]` both hold the user and Grace; after success the user is renamed in both, Grace untouched, `snapshot()` has the new name | module not found |
| `useProfile.test.tsx` · `a rename lands after its component unmounts` | hold the PATCH, unmount, release → session and directory updated | same |
| `useProfile.test.tsx` · `a directory fetch in flight with the old name does not win` | hold a directory refetch answering the old name; rename succeeds; release the held fetch → the cache ends with the new name (the invalidate's fetch answers it) | same |
| `useProfile.test.tsx` · `a profile fetch in flight with the old name does not win` | `['profile','me']` holds `Ada Lovelace`; a refetch is held answering it; rename to `Ada L` succeeds; release the held fetch → `['profile','me']` ends `Ada L` (cancelled, then the success's invalidate answers the new name) | same |
| `usePreferences.test.tsx` · `a choice applies before the server answers` | hold the PATCH: the `['preferences']` cache already holds `24h` | module not found |
| `usePreferences.test.tsx` · `a failed save puts the previous choice back` | from `12h`, choose `24h`, PATCH 500 → cache `12h`, error exposed | same |
| `usePreferences.test.tsx` · `two choices in a row end on the second` | `24h` then `12h`, the first held; the second request is sent only after the first settles (scope); final cache `12h` | same |
| `usePreferences.test.tsx` · `a failure behind a later choice is ignored; both failing restore the start` | first fails, second succeeds → `12h`; both fail → the starting value | same |
| `usePreferences.test.tsx` · `a preferences fetch in flight does not undo a choice` | cache `12h`; a refetch is started and held, answering `12h`; choose `24h` → cache `24h`; release the held GET → still `24h`; after the PATCH settles, a further `GET` is recorded (the invalidate) and the cache ends on what it answers, `24h` (decision 36) | module not found |
| `usePreferences.test.tsx` · `useClock follows the cache without fetching` | `setQueryData(['preferences'], { clock: '24h' })` → `'24h'`; then `{}` → `undefined`; no request recorded | same |
| `MessageItem.test.tsx` · `the time follows the clock, re-rendering a cached message` | cache `24h` → `13:05`; `setQueryData` `12h` → no `13`, and no request recorded | shows the locale default, not `13:05` (in a 24-hour default locale the second half fails instead) |
| `ThreadSummary.test.tsx` · `the last reply time follows the clock` | `24h` → `13:05`, then `12h` → no `13` | as above |
| `SearchResult.test.tsx` · `the result time follows the clock` | same, through `dateAndTime` | as above |

Each formatter test starts at `24h` and moves to `12h`, so at red one half fails in any default locale.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/display_names.feature`, `steps/test_display_name_steps.py`,
`conftest.py`, `pages/chat_page.py`

```gherkin
@bdd
Feature: Display names
  Alan changes the name everyone sees him by, on his Settings page.

  Background:
    Given Alan is signed in

  Scenario: Grace sees the name Alan gives himself, after a reload
    Given Alan has created a public channel named "general"
    And Alan has sent "the bombe is running" in "general"
    When Alan renames himself to "Alan Turing" on Settings
    Then Alan sees his own name as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the bombe is running" written by "Alan Turing"
```

- Reused verbatim: `When Grace reloads CollabHub`, `When Grace opens the "{name}" channel`. New
  phrases, all in the steps module: `Given Alan is signed in`, `Given Alan has created a public
  channel named "{name}"`, `Given Alan has sent "{body}" in "{channel}"`, `When Alan renames himself
  to "{name}" on Settings`, `Then Alan sees his own name as "{name}"`, `Then Grace sees "{body}"
  written by "{name}"` — this last one with `parsers.re` and `[^"]*` groups (as `steps/conftest.py:143`),
  and distinct from `written by Ada` (`test_message_steps.py:39`), which takes no quoted name.
- `conftest.py`: `ALAN = "alan@collabhub.dev"`, a session-scoped `alan_context` from
  `_signed_in_context` (so he joins `CollabHub Demo` like the others), and an `alan` fixture as `ada`.
- `ChatPage`: `own_name()` reads `current-user`; `has_own_name(name)` retries with `expect`;
  `rename_self(name)` clicks `current-user`, waits for `display-name-input`, fills it, and **if
  `display-name-save` is disabled — the name is already his, a `KEEP_STACK` rerun — returns**; else
  clicks it and waits for `display-name-saved`. A step never holds a selector.
- The last `Then` is Grace's window after a reload: what Auth holds, not Alan's cache.
- Expected red: `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` lists only
  this feature's new steps until the step module exists; once it does, the journey (run in Task 9)
  would fail at `rename_self` waiting for `display-name-input` — there is no `/settings`.

## Task 5: Names, the migration and first sign-in (GREEN)

**Files:** `names.py`, `0002_…py`, `models.py`, `migrations.py`, `identities.py`, integration `conftest.py`

```python
# 0002 — order matters: clean, dedupe, then the index that forbids what was just fixed.
rows = bind.execute(sa.text(
    "SELECT id, display_name FROM users ORDER BY created_at, id")).all()
# 1. each name -> names.provisional_name(name)          (trim, drop refused chars, ≤100, "user")
# 2. reserved = {lower(n) for every cleaned name}; assigned = set()
#    oldest first: keep if lower(n) not in assigned, else first candidate whose lower() is in
#    neither reserved nor assigned; add to assigned. UPDATE only rows whose name changed.
op.create_index("uq_users_display_name", "users", [sa.text("lower(display_name)")], unique=True)
op.create_table(
    "user_preferences",
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
)
# downgrade: drop the table and the index. Renamed names are not restored (Req 4: one-way).
```

- [ ] `names.py` to Task 1's interface. Task 1's name tests: 7 passed.
- [ ] `User.__table_args__` gets `Index("uq_users_display_name", text("lower(display_name)"),
  unique=True)`; `UserPreferences` model (JSONB `prefs`). `migrations.upgrade(dsn, revision)`.
- [ ] `identities.display_name_taken(session, name) -> bool` (no `deleted_at` filter, with the CH009
  waiver), `is_display_name_conflict(exc) -> bool` (decision 15), and `provision_user` walking
  `names.candidates(names.provisional_name(display_name))` per decision 16; the own workspace is
  named from `user.display_name`. Logs nothing about the name.
- [ ] Integration `conftest.py`: `TABLES = ("user_preferences", "refresh_tokens", …)`.
- [ ] `test_schema.py` as the file map says — distinct names per user, and the citext test asserts
  the violation is not the name index's. Run it: 4 passed.
- [ ] `uv run pytest src/services/auth/tests/integration/test_first_sign_in_names.py
  …/test_name_migration.py`: all pass. Leave uncommitted.

## Task 6: The routes (GREEN)

- [ ] `schemas.UpdateUserRequest.display_name: str | None = None` — **no** `Field` length limits;
  `names.validate_display_name` decides, after trimming. `PreferencesResponse(CamelModel)` with
  `clock: Literal["12h", "24h"] | None = None`.
- [ ] `update_me`: `null` stays the existing 400 (`users.py:61-65`). `InvalidDisplayNameError` →
  `ProblemException.validation_error(e.message, errors={"displayName": [e.message]})`. Unchanged
  name and nothing else sent → return without writing (decision 20). Otherwise set, `flush()` in a
  `try`; on `IntegrityError` that `is_display_name_conflict`, `rollback()` and raise
  `ProblemException.conflict("That name is already taken.", errors={"displayName": ["That name is
  already taken."]})`; any other `IntegrityError` re-raises.
- [ ] `preferences.read(session, user_id) -> dict` (no row → `{}`, no insert) and
  `preferences.merge(session, user_id, set_, remove) -> dict`: one `postgresql.insert(...)
  .on_conflict_do_update(index_elements=["user_id"], set_={"prefs": (prefs || excluded.prefs) -
  CAST(:remove AS text[]), "version": version + 1, "updated_at": now()}).returning(prefs)`, built
  with SQLAlchemy operators (`.op("||")`, `.op("-")`), never interpolated (CH006). The insert's own
  `prefs` is `set_`.
- [ ] `routers/preferences.py`, `APIRouter(prefix="/api/v1/users")`: `GET /me/preferences` and
  `PATCH /me/preferences` (`body: PreferencesPatch`), both `require_user`, both 404 `"This account no
  longer exists."` via `identities.find_user`; PATCH with nothing to set or remove writes nothing;
  responses through `PreferencesResponse` with `response_model_exclude_none=True`. Register in
  `main.py` beside `user_routes`.
- [ ] `uv run pytest src/services/auth/tests`: Tasks 1–2 pass; Auth unit 70 or more. Leave uncommitted.

## Task 7: The SPA (GREEN)

- [ ] `api.ts`, `storage.ts` (`returnPath`, and its header comment: a second short-lived key),
  `session.ts` (`updateProfile`, with a module `profileWrites` counter that `adopt()` reads before
  and after its fetch and keeps the current profile when it moved — decision 30; `signIn` takes
  `returnTo`).
- [ ] `App.tsx`: `Protected` passes `state={{ from: pathname + search }}` to `/sign-in`; `SignIn`
  passes it to `session.signIn`; `Callback` navigates to `returnPath.take() ?? '/'` on success, and on
  failure to `/sign-in` with `state.from` set from what it took, so a retry still returns; a
  `/settings` route rendering `SettingsPage` under `Protected`.
- [ ] `WorkspaceSwitcher.tsx`: `current-user` becomes a `Link` to `/settings` with `state.from`, its
  text the directory's name for `profile.id`, else the session's (decision 37).
  `ChatLayout.tsx`: `usePreferences(current.accessToken)`.
- [ ] `time.ts`; `MessageItem`, `ThreadSummary`, `SearchResult` call `useClock()` and `time.ts` — and
  drop their "D28 🔴 / no stored preference" comments.
- [ ] `usePreferences.ts` (decisions 31, 32 and 36; `useClock` via `useSyncExternalStore` over
  `queryClient.getQueryCache().subscribe`), `useProfile.ts` (decisions 29 and 36; also
  `setQueryData(profileKeys.me(), profile)` then invalidate it), `SettingsPage.tsx` (the form mounts once `useProfile`
  has fetched since mount; the clock radios are disabled until preferences have).
- [ ] `npm --prefix src/frontend test` and `run typecheck`: Task 3 passes; Vitest 530 or more. Leave uncommitted.

## Task 8: The record

- [ ] Register: D28 → 🟢 (the issue's *Decided already* 7, built 2026-10-16, and the clock); new D46
  🟢 in *Platform / Auth* — global, case-insensitive, deleted accounts included, the existence leak
  accepted, `lower()`'s folding gap (decision 14); both in *Resolve First*'s settled list.
- [ ] Two ADRs with the `adr-writer` skill: D28 (preferences in Auth, per user, validated keys, atomic
  merge) and D46 (global uniqueness over tenancy, the index as sole arbiter).
- [ ] Doc 01: §3 the two preferences routes and the 400/409 on `PATCH /users/me`; §4
  `user_preferences` and `uq_users_display_name`; §5.1 the first-sign-in suffix rule.
- [ ] Doc 06: §3 `/features/settings`; §4 point 4 — `sessionStorage` also holds the return path;
  §5.2 *Names* (`:316`) — the renamer's own tab updates at once, everyone else as before; §9's D28
  paragraph (`:479`).
- [ ] `CLAUDE.md`: the D28 paragraph under *Open decisions* (preferences now exist; light-only is D26's
  choice, not a missing store); the tenancy bullets gain the D46 exception, worded as decided.
- [ ] `README.md:45-46`, `src/frontend/README.md:60-62`, `src/frontend/src/index.css:10`: the
  "no user-preferences feature" reasons. `00-scenario-vocabulary.md`: §1 (`:36`, `:52`) and
  ruling 6's summary (`:31-32`, "forbids … a third") both gain the exception — Alan, from issue gh-3,
  for the display-name journey only. Sweep: `grep -rn "D28\|preference" docs/design src/services/auth
  src/frontend/src` for anything still saying there is none. Leave uncommitted.

## Task 9: Verification

- [ ] `git branch --no-merged main`: name any sibling branch touching Auth's `users`, `session.ts` or
  the formatters in *Found while building*.
- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each once; the whole e2e
  layer is the journey's first run, `-- -k display` only to iterate on a failure. Counts at or above
  the baseline; Auth integration is new to the report.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; the CH009 waiver names every checker that fires on its line.
- [ ] **First real run** on the Compose stack (`docker compose up -d --build`): rename Ada in one
  browser and watch her sidebar and own messages change; try Grace's name in capitals; choose
  24-hour and see a cached channel's times change; reload `/settings` signed out and sign in.
- [ ] If `main` moved, merge it and rerun the above. Fill in *Found while building*. Leave dirty.

## Found while building

- **`tests/integration/conftest.py` `TABLES` and `test_schema.py` `a_user` were not changed.** The plan
  made both GREEN, but the code-writer may not write any test file. Neither is needed: `testkit.truncate`
  runs `TRUNCATE … CASCADE`, which clears `user_preferences`, and the citext test passes because it only
  asserts an `IntegrityError`. The sharper assertion (that the email index, not the name index, refused
  it) is not made — a follow-up for the test pair. No test pins it.
- **`directoryKeys.all()`** (`['workspace-members']`) added to `useWorkspaceMembers.ts` for the rename's
  `setQueriesData`/`invalidateQueries`. Pinned by `useProfile.test.tsx`.
- **Settings radios also unlock on a failed preferences read** (`isFetchedAfterMount || isError`), so one
  bad request cannot lock the section. No test.
- **`PATCH /users/me` with `{}`** now writes nothing (it used to bump `version`); a consequence of decision 20.
- No bug was found by the first e2e run; the journey passed on its first run.
- Sibling branches: `git branch --no-merged main` lists none.

## Not in this plan

- Pushing a rename to other users live; renaming anyone else or a workspace.
- Clearing the query cache on sign-out (decision 34).
- Any preference but `clock`; generating Auth's OpenAPI types.

## Self-review

- **Issue coverage:** Req 1 → Tasks 1, 2 (`test_display_names`), 3 (form), 6; Req 2 → 2, 5, 6;
  Req 3 → 1, 2 (`test_first_sign_in_names`), 5; Req 4 → 2 (`test_name_migration`), 5; Req 5 → 3
  (`useProfile`, `session`), 4, 7; Req 6 → 1, 2 (`test_preferences_api`), 6; Req 7 → 3 (`time`,
  formatters, `usePreferences`), 7; Req 8 → 3 (`SettingsPage`, `App`, `ChatLayout`), 4, 7.
  *Where the rules meet:* concurrency → `test_two_renames_to_one_name_at_once`; rename vs sign-up →
  `test_a_rename_waits_on_a_sign_up_holding_the_name`, `test_a_sign_up_after_a_rename_takes_a_suffix`,
  `test_two_first_sign_ins_with_one_name`; own view → `a rename updates the session and every cached
  directory`; token → left (issue); workspace name → `test_a_first_sign_in_through_dex_takes_a_suffix`
  shows the workspace follows only the first name, rename leaves it (no code touches it); clock and
  cache → `MessageItem` re-render test; two tabs → `test_merges_of_different_keys_both_land`.
  *Paths:* direct load → `renders /settings on a direct load`; signed out → `a signed-out visitor
  on /settings…`; unmount → `a rename lands after its component unmounts`; unsaved edit → no test,
  said above; workspace switch → `a workspace switch leaves the page as it is`; second tab → `the sidebar names
  the user as the directory does` (decision 37) with the existing directory refetch tests; Grace →
  the journey's reload; deleted account → 404 and taken-name tests. Req 7's "shows the error" →
  `a failed clock save puts the choice back and says so`; Req 8's "preferences on every visit" →
  `the clock is read from the server on every visit`.
- **Other writers of the same state:** `['preferences']` and `['profile','me']` (decision 36),
  `session.profile` (30), the directory (29) — each with its in-flight test.
- **Names:** `uq_users_display_name` in the model, the migration and `is_display_name_conflict`;
  `['preferences']` in tests and `preferenceKeys.mine()`; `collabhub.returnTo` in storage and tests.
- **Known ripple:** `test/api.ts`'s default handler keeps existing `ChatLayout` renders quiet; the
  integration conftest's `TABLES` and `test_schema.py`'s `a_user` change in GREEN, not RED.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. Fixed — `test_schema.py` in the file map and Task 5 (distinct names; citext test checks the constraint).
2. Fixed — decision 36 (cancel in `onMutate`, invalidate on settle, both keys); two new hook tests.
3. Fixed — A holds its transaction, B must block; parametrised with and without a row.
4. Fixed — the `auth.preferences` import is deferred into that test; the migration file's stays, all need it.
5. Fixed — two `SettingsPage` tests: the server read on every visit, and the failed save's alert.
6. Fixed — decision 37, **assumed**: the sidebar reads the directory; `ChatLayout` test added.
7. Fixed — Task 8 amends ruling 6's summary (`:31-32`) as well as §1.
8. Fixed — `at_0001` is a sync function-scoped fixture; the test awaits `upgrade(dsn, "0002")`.
9. Fixed — `demo_workspace_name=None` in both racing provision tests. Also taken up: Task 9's branch check.
