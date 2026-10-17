# Display names, unique names and a preferences page — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A signed-in user renames themselves on a new `/settings` page; display names are unique
across CollabHub; the same page holds the first per-user preference, a 12/24-hour clock, stored by
Auth (D28).

**Architecture:** One module, `auth/names.py`, owns every name rule: normalise and validate, the
comparison key, the first free suffix, and the duplicate renaming the migration runs. The key is
**computed once, in Python, and stored** in `users.display_name_key` under a plain unique index, so
the database compares exactly what the application computed — Postgres `lower()` never enters it.
The index is the race control: a rename or a first sign-in that loses gets a unique violation, never
a second row. Preferences are a `user_preferences` row merged by one atomic upsert. The SPA gets a
`/settings` route inside the shell; a rename writes the session profile and every cached directory
on success, in the mutation's own callback so it survives an unmount; the clock reaches the three
formatters through one context fed by a TanStack query.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, pytest +
testcontainers · React 19, TanStack Query 5.101, React Router, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/gh-3/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `/home/runner/work/ch09/caw-gh-3`, branch `feature/gh-3`, from `main` at `41bcc04`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | Req 1–8; *Not in this issue* stays out |
| 2 | Who renames whom | Only yourself, through `PATCH /users/me` (id from `sub`) |
| 3 | Name scope | One name per user, unique across all of CollabHub, deleted accounts included — new **D46** |
| 4 | Lookalikes, ZWJ/ZWNJ, U+2800 | Not handled / refused / allowed, as *Decided already* 5 says |
| 5 | Live push of a rename | None; doc 06's "Renames are not covered" holds for everyone but the renamer's tab |
| 6 | Where preferences live | **D28 🟢**: Auth, `user_preferences (user_id, prefs jsonb, version, updated_at)`, per user, server-validated keys; a TanStack query in the SPA (D24) |
| 7 | Fail-open | Both PATCH routes on `require_user`, not Conventions §5.2's sensitive set |
| 8 | Auth's client types | Hand-typed in `lib/auth/api.ts` (`updateMe`, `preferences`, `updatePreferences`) |
| 9 | Logs | No display name in any log call (CH008) |
| 10 | The journey | One scenario with a third persona, Alan — the issue overrides vocabulary ruling 1 ("Ada and Grace, and no one else") |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 11 | How uniqueness is enforced | A stored `display_name_key text NOT NULL` with unique index `ux_users_display_name_key`, set by a `@validates("display_name")` hook on `User` from `names.name_key()` | One computation (the issue's "compare the same way"). A functional index on `lower(display_name)` would put a second, different case rule in the database — exactly the drift the issue warns about |
| 12 | What "ignoring case" means — **assumed** | `name_key(n) = NFC(n.casefold())`: full Unicode case folding, so `"Strauß"` collides with `"STRASSE"` | The issue asks whether `lower()`'s gaps matter; with a stored key they can't arise. `str.lower()` would leave `ß`/`ss` and Greek final sigma distinct. Changing it later: one function and a migration that recomputes the key and re-runs `dedupe` |
| 13 | Length — **assumed** | 1–100 **code points** after trim + NFC (`len()` in Python, `[...s].length` in the SPA) | The issue says "characters". Grapheme counting needs a library neither side has. Cost to change: `normalise_display_name` and the SPA's `nameIsValid` |
| 14 | Validation moves out of the schema | `UpdateUserRequest.display_name: str \| None = None` (no `Field` bounds); `names.normalise_display_name` raises `InvalidNameError` → 400 `errors.displayName` | `max_length=100` counted before trimming, so `"  " + 100 chars` was refused and `"   "` passed. Explicit `null` stays the existing 400 (`users.py:60-65`, `test_users.py:101` — the issue's assumption checked: it is 400 today) |
| 15 | Saving the name you have — **assumed** for legacy names | 200, no write: `version` and `updated_at` unchanged. The no-op check runs **first**, on `names.stored_form(raw)` (trim + NFC, no validation): equal to the stored name → 200 before any validation. So a legacy name the migration kept with a refused character or over 100 (decision 22) can still be saved unchanged | Req 1 "changes nothing" and "saving the name you have succeeds" — the second wins over the character rules because nothing is written. `" ada "` for `"ada"` is the same no-op. The alternative (validate first, 400) contradicts Req 1's last sentence for those users; cost to change: the order of two lines in `update_me` |
| 16 | The 409 | `ProblemException.conflict("That name is already taken.", errors={"displayName": ["That name is already taken."]})` | Req 2's words. Detected by the violated constraint's name, `exc.orig.__cause__.constraint_name == "ux_users_display_name_key"` — SQLAlchemy's asyncpg adapter raises the translated error `from` asyncpg's (`.venv/lib/python3.12/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py:791-797`, checked in the worktree's `.venv`), whose `UniqueViolationError` carries `constraint_name`. The email unique index must not become a 409 |
| 17 | First sign-in's base name — **assumed** | `names.provision_name(raw, email)`: normalise, **drop** every refused character, cut to 100; if empty, the same applied to the email's local part; if still empty, `"user"` | Req 3 says sign-in never refuses over a name, so an IdP name that fails Req 1 must become one that passes. Dropping beats refusing; the fallback chain is `oidc.py:250-252`'s. Cost to change: one function |
| 18 | Suffix and length — **assumed** | `with_suffix(base, n)` = `base[: 100 - len(f" {n}")] + f" {n}"` for n ≥ 2 | Keeps every generated name inside Req 1. `"X 2"` itself is Req 3's |
| 19 | Concurrent first sign-ins | Load the taken keys that equal or start with `key(base) + " "` (deleted rows included), pick `first_free`, insert in a SAVEPOINT; on a violation of `ux_users_display_name_key` add that key to a local `refused` set and retry, at most 10 times. **After the 10th loss — assumed:** the violation is re-raised, and the callback's existing error path fails that one sign-in | The loser blocks on the index until the winner commits, then retries and sees it (READ COMMITTED). `refused` covers a cut-down candidate the prefix query can't see, so no candidate is tried twice and every loss is to a row another sign-in committed. Ten losses in a row need eleven first sign-ins with one base name, each committing inside the others' window — unreachable with Dex's users, so Req 3's "never refuses" holds in practice. The alternative, an unbounded loop, turns any key bug into a hung callback; cost to change: one constant |
| 20 | Migration shape | `0002_unique_display_names`: add the column nullable → load every row ordered `(created_at, id)` → `names.dedupe(rows)` → `UPDATE` each row's name and key → `SET NOT NULL` → create the index. Downgrade drops the index and column; names stay rewritten | Req 4, "with the same code as Req 1": the migration imports `auth.names`. A Python pass beats SQL because the rules are Python's |
| 21 | Which duplicates are renamed | `dedupe` first reserves the key of every **kept** name (the oldest of each key), then suffixes the rest in age order, skipping every reserved key | Otherwise `"X", "X", "X 2"` renames the real `"X 2"`. Req 4 renames duplicates only |
| 22 | A stored name that is empty after trimming — **assumed** | The migration gives it the email local part, else `"user"`, then the suffix rule | NOT NULL and a unique key need *a* name; the issue's Req 4 assumes none exist. Characters Req 1 refuses are **left** in stored names (Req 4 says trim + NFC only) |
| 23 | Preferences wire shape | `GET`/`PATCH /api/v1/users/me/preferences` → `200 {"clock": "24h"}` — the stored keys, flat | Req 6's "returns the stored keys, or `{}`" |
| 24 | The merge | One statement, `INSERT … ON CONFLICT (user_id) DO UPDATE SET prefs = (user_preferences.prefs \|\| :set) - :remove, version = user_preferences.version + 1, updated_at = now()` | Different keys from two tabs both land, the same key is last-write-wins; a read-modify-write in Python loses one. The merge exists only in SQL — no Python copy |
| 25 | `PATCH {}` — **assumed** | 200 with the current keys, no row written | Nothing to change; mirrors decision 15 |
| 26 | Unknown key and bad value | All errors at once, `errors.<key>`: unknown → `"Unknown preference."`; bad → `"Must be \"12h\", \"24h\" or null."`; nothing applied, valid keys in the same body included | Req 6 "nothing changes" |
| 27 | `/settings` placement | Inside `Protected`, so inside `ChatLayout`: the sidebar's `current-user` is on screen when the rename lands | Req 5's "at once" is visible there. A bare page would need its own shell |
| 28 | Sign-in returns to the route — **assumed**; see *Corrections* | `Protected` redirects with `state.from`; `SignIn` passes it to `session.signIn('dex', from)`, stored in `sessionStorage` (`collabhub.returnPath`); `Callback` navigates to `session.takeReturnPath() ?? '/'`. Only a path starting `/` and not `//` is kept. **Every `signIn` overwrites it** (clears it when `returnTo` is absent), and every failed `completeSignIn` clears it, so a failed sign-in from `/settings` never sends a later plain one there | The *Paths* row needs it; it applies to every protected route, because one guard serves all. It extends doc 06 §4's "only the PKCE verifier" in `sessionStorage` by one non-secret path, recorded there (Task 11). Cost to undo: three call sites |
| 29 | "Back to chat" — **assumed** | `/c/{lastChannelId}` from a new `lastChannelId` in the chat store, set whenever a channel opens, never cleared by leaving it, cleared on a workspace change; `/` when empty (a direct load) | `activeChannelId` is cleared on `ChannelView` unmount (`ChannelView.tsx:38`). Client state, so Zustand (D24) |
| 30 | Client-side Save gating — **assumed** | Disabled when `value.trim().normalize('NFC')` equals the server's name, is empty, or is over 100 code points; the character rules are the server's 400 | Req 8 "disabled while unchanged or invalid". A second copy of the Unicode tables in TS would drift |
| 31 | What a rename writes in the SPA | In `useMutation`'s own `onSuccess`, in this order: `session.updateProfile(profile)`; the profile query; `await queryClient.cancelQueries({ queryKey: ['workspace-members'] })`; `setQueriesData` on every `['workspace-members', *]` list; then `invalidateQueries({ queryKey: ['workspace-members'] })` | The hook-level callback runs with no observer (`query-core/src/mutation.ts:246`); per-call `mutate(…, { onSuccess })` runs only while subscribed (`mutationObserver.ts:164`). **The cancel comes first** because `invalidateQueries` cancels an in-flight fetch only when the query already has data — with none (a direct load of `/settings`, the sidebar's first directory fetch still out) it *joins* it (`query.ts:411-418`), and the old name would land. `cancelQueries` cancels either kind (`queryClient.ts:276-289`, `revert: true`). The invalidate then refetches after the commit. All four citations checked in the primary checkout's `src/frontend/node_modules/@tanstack/query-core/src/` (5.101.4, the lock's version; `main` = this branch's base) |
| 32 | The clock in the SPA | `preferenceKeys.mine(userId) = ['user-preferences', userId]`, read once by `ClockProvider` in `ChatLayout`; `useClock()` returns `null` outside it | Per user, so no workspace in the key: a switch keeps it (D24's workspace rule is for workspace data). `null` outside a provider keeps every existing formatter test as it is |
| 33 | 12/24 hour | `hourCycle: 'h12'` / `'h23'`, never `hour12` | `hour12: false` can render midnight as `24:05` in some ICU locales; `hourCycle` is allowed beside `timeStyle`. Pinned by the midnight test, not assumed |
| 34 | Optimistic clock — **assumed** | `onMutate` sets the cache; `onError` puts the snapshot back **only if** the cache still holds this mutation's value; `onSuccess` writes the server's answer only on the same condition. The mutation has `scope: { id: 'user-preferences' }`, so a second choice's PATCH waits for the first to settle and the server stores the choices in the order made | Req 7's revert, without a late failure undoing a newer choice. Without the scope two PATCHes can reach Auth in the other order, leaving the tab on 12-hour and the server on 24-hour. A scoped mutation runs `onMutate` at once and only its `mutationFn` waits (`mutation.ts:205-235`, `canRun` from `mutationCache.ts:161-176`), so the optimistic render is unchanged |
| 35 | The settings queries | `useProfile` and `usePreferences` on the page with `refetchOnMount: 'always'`; the form renders only once `isFetchedAfterMount` | Req 8 "from the server on every visit", not the session's or the cache's copy |
| 36 | The register | D28 → 🟢; new D46 🟢; two ADRs; Conventions §3 gains the deleted-names read as its third soft-delete exception, recorded under D46 | The issue's *Record in this slice*; §3 says "a third exception should be a decision with a record, not a local call" |
| 37 | A renewal or switch racing a rename — **assumed** | `session.ts` counts profile edits (`profileEdits`). `adopt()` reads the count before fetching `me`; when it sets the session, if the count moved and the signed-in profile is the same user's, it keeps the session's current profile instead of the fetched one | `adopt()` takes `me` from before `set` (`session.ts:79-92`): a renewal or a switch whose `me` was answered before the PATCH committed but lands after `updateProfile` would put the old name back in the sidebar while the directory shows the new one — *Where the rules meet* 3. A renewal that *starts* after the edit adopts what it fetches, so the next one picks up a rename made elsewhere. The alternative, re-fetching `me` after every adopt, costs a request per renewal; cost to change: one function |

Nothing here builds on a 🔴 entry: D28 is 🔴 today, and the issue decides it (*Decided already* 7) —
the human's call, recorded by Task 11. The nearest still-open ones are **D37/D38** (a 401, and a renewal
lost to a network error): Task 9 touches `session.ts` and sign-in's return path, and changes neither
what a failed renewal nor a 401 does. **D18** (notifications) and **D13** (avatars) are named by the
issue as out; `avatarAsset` is unchanged.

## Corrections to the issue

1. **"The SPA's sign-in returns to the route it started from" is false.** `Protected` redirects to
   `/sign-in` with nothing remembered (`App.tsx:83`) and `Callback` always lands on `/`
   (`App.tsx:63`); only a *reload* with a live cookie stays put, through `restore()`. The *Paths* row
   "`/settings` while signed out → back on `/settings`" needs it built: decision 28, Task 9.
2. **`users.display_name` alone cannot be the unique thing.** Req 2's case-insensitive comparison is
   carried by a second column (decision 11); doc 01 §4 records it (Task 11).

## Test approach — recommendation to the test pair

**BDD outside-in, with the one journey the issue names.** A rename is a new capability a user sees,
and only two browsers prove another person's view picks it up from the server. Everything else goes
down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Alan renames himself on Settings; Grace, after a reload, sees the new name on his message | **BDD** | `tests/bdd/features/settings.feature` |
| Trim, NFC, every refused/accepted example, length, the key, suffixes, the base name, `dedupe` | unit | `auth/tests/unit/test_names.py` |
| The preference patch rules | unit | `auth/tests/unit/test_preferences.py` |
| Rename over REST: 400, 409, case, NFC collisions, deleted names, the no-op | integration | `auth/tests/integration/test_users.py` |
| The concurrent rename, first sign-in suffixing (one and two at once) | integration | `auth/tests/integration/test_display_names.py` |
| The migration's normalising and renaming, and the index it leaves | integration | `auth/tests/integration/test_migration_0002.py` |
| Preferences routes, the merge race, 404 for a deleted account | integration | `auth/tests/integration/test_preferences.py` |
| Fail-open of both PATCHes | integration | `auth/tests/integration/test_r1_unreachable.py` |
| The formatters, 12/24/automatic | Vitest | `lib/time.test.ts` |
| The page, its paths, the writes on success, the clock and its revert | Vitest | `features/settings/SettingsPage.test.tsx` |
| The clock in all three formatters, re-rendered from the cache with no refetch | Vitest | `features/settings/ClockProvider.test.tsx` |
| `updateProfile`, the return path | Vitest | `lib/auth/session.test.ts`, `App.test.tsx` |
| `lastChannelId` | Vitest | `stores/chat.test.ts` |

**What no test covers:** a second tab or device of the renamer — no code is added for it; it relies
on the directory's existing refetches, proven by `useWorkspaceMembers.test.tsx`. The token's `name`
claim staying old until refresh — left as the issue says. Locales other than the one Vitest and
Playwright run in (decision 33's assumption is checked in one locale only). The first-sign-in suffix
on the preview (the issue's *Acceptance* says so). Two first sign-ins with the **same email** at
once: `provision_user`'s loop re-raises every violation but the name index's, so that behaves as today.

**Baseline**, from `docs/test-report.md` (written at `4422c67`; unit recorded at `3daf13a`): Auth unit
59 passed; Vitest 503 passed; the integration figure there is `tools/delivery`'s alone (26), so the
test-writer records Auth's integration count before adding to it; end-to-end not run. Expected counts
are "N or more".

## Global constraints

- `PATCH /users/me` and both preferences routes: `require_user`, the row from `principal.user_id`
  only (CH001). A deleted account is **404 `"This account no longer exists."`**, as `users.py:34`.
- The D46 409 names nobody: no id, email, name or workspace in the body beyond the fixed sentence.
- The taken-keys query and the migration read deleted rows **on purpose** — waive CH009 on that line
  with the reason ("names stay taken after deletion — D46, Conventions §3's third exception"), and a
  `nosemgrep` only if semgrep fires. Task 11 records the exception in §3, so the waiver cites a
  decision, not a local call.
- No new environment variable. No chart change: `/api/v1/users` is in the Ingress allow-list
  (`charts/collabhub/templates/ingress.yaml:50`, checked). Messaging and the Worker are untouched.
- Sibling branch: `origin/feature/gh-3-run1` is an earlier, unmerged run of this same issue and edits
  the same files — the two cannot both merge; that is the human's to choose. `origin/feature/gh-4`
  touches only `docs/plans/gh-4/`.

## File map

Paths shortened: `auth/` = `src/services/auth/`, SPA paths from `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `auth/tests/unit/test_names.py` · `test_preferences.py` | create | the rules | 1 |
| `auth/tests/integration/test_users.py` | modify | rename over REST | 2 |
| `auth/tests/integration/test_display_names.py` | create | rename race, sign-in suffixing | 2 |
| `auth/tests/integration/test_migration_0002.py` | create | the migration | 2 |
| `auth/tests/integration/test_preferences.py` | create | preferences routes and merge | 2 |
| `auth/tests/integration/test_r1_unreachable.py` | modify | fail-open of both PATCHes | 2 |
| `auth/tests/integration/test_schema.py` | modify | `a_user` gives each user its own name; the email test asserts *its* constraint — an existing test the index weakens | 2 |
| `auth/tests/integration/conftest.py` | modify | `TABLES` gains `user_preferences`, first | 2 |
| `tests/bdd/features/settings.feature` · `steps/test_settings_steps.py` | create | the journey | 3 |
| `tests/bdd/conftest.py` · `pages/chat_page.py` | modify | `alan_context`/`alan`; settings methods | 3 |
| `lib/time.test.ts` · `features/settings/SettingsPage.test.tsx` · `ClockProvider.test.tsx` | create | the SPA's red | 4 |
| `lib/auth/session.test.ts` · `App.test.tsx` · `stores/chat.test.ts` | modify | `updateProfile`, return path, `lastChannelId`; `aReturningUser` stubs preferences | 4 |
| `features/channels/ChatLayout.test.tsx` · `ChatLayout.attachments.test.tsx` · `CreateChannelDialog.test.tsx` | modify | stub `GET /users/me/preferences` — the shell now fetches it | 4 |
| `test/api.ts` | modify | `auth.preferences`, `auth.patchPreferences`, `auth.patchMe` stubs | 4 |
| `auth/auth/names.py` | create | every name rule | 5 |
| `auth/auth/preferences.py` | create | `KNOWN`, `parse_patch`, `read`, `apply_patch` | 5 |
| `auth/auth/models.py` | modify | `User.display_name_key` + validator; `UserPreferences` | 6 |
| `auth/auth/alembic/versions/0002_unique_display_names.py` · `0003_user_preferences.py` | create | the migrations | 6 |
| `auth/auth/identities.py` | modify | `NameTakenError`, `rename_user`, `provision_user` suffixing | 7 |
| `auth/auth/schemas.py` · `routers/users.py` | modify | request without bounds; the rename rules; two preferences routes | 7 |
| `lib/auth/api.ts` · `session.ts` · `storage.ts` | modify | client calls; `updateProfile`; return path | 8–9 |
| `lib/time.ts` | create | the formatters | 8 |
| `features/settings/{SettingsPage.tsx,useProfile.ts,usePreferences.ts,ClockProvider.tsx}` | create | the page, its queries, the clock | 8 |
| `App.tsx` · `features/channels/{WorkspaceSwitcher,ChatLayout,ChannelView,MessageItem}.tsx` · `features/threads/ThreadSummary.tsx` · `features/search/SearchResult.tsx` · `stores/chat.ts` | modify | route, link, provider, `lastChannelId`, formatters | 8–9 |
| `docs/design/01-auth-service.md` · `06-frontend-spa.md` · `00-platform-conventions.md` (§3, §5.4) · `07-open-decisions-register.md` · two ADRs | modify · create | the record | 11 |
| `src/frontend/README.md` | modify | the stale "D28 🔴" | 10 |

Deliberately unchanged: `tests/bdd/conftest.py`'s truncation (Auth's tables are never truncated, and
the journey needs nothing reset); `auth/oidc.py` (its fallback chain stays the raw input to
`provision_name`); `link_identity` (still never touches an existing user's name);
`sessions.py:51-57` (the `name` claim stays as the issue leaves it). The sweep found nothing else
inserting into `users`: `identities.provision_user` is the only `User(` outside tests.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing unit, integration, BDD and Vitest tests, each for the reason given — **test-reviewer gate** |
| GREEN — Auth | 5–7 | code-writer | Tasks 1–2 pass |
| GREEN — SPA | 8–9 | code-writer | Task 4 passes, `tsc` clean |
| Finish | 10–12 | code-writer | docstrings, the record, verification (the journey's first run) |

One RED phase is enough: Auth's types are hand-typed, so the SPA's stubs type against the
interfaces Task 4 adds to `test/api.ts` from this plan's wire shapes, not a generated file.

---

## Task 1: The rules (RED)

**Files:** `src/services/auth/tests/unit/test_names.py`, `test_preferences.py` (create)

**Interfaces** — `auth.names`:
- `MAX_LENGTH = 100`; `class InvalidNameError(ValueError)` with a user-facing message
- `stored_form(raw: str) -> str` — `strip()`, then NFC; no validation (the migration's step, and the no-op check of decision 15)
- `normalise_display_name(raw: str) -> str` — `stored_form`, then the length and character rules; raises `InvalidNameError`
- `name_key(name: str) -> str` — `unicodedata.normalize("NFC", name.casefold())`
- `with_suffix(base: str, n: int) -> str`; `first_free(base: str, taken: AbstractSet[str]) -> str` — `taken` holds **keys**
- `provision_name(raw: str, email: str) -> str` (decision 17)
- `dedupe(rows: Sequence[tuple[UUID, str, str]]) -> dict[UUID, str]` — rows `(id, display_name, email)` already in `(created_at, id)` order; returns the stored name for **every** row (trimmed + NFC, decision 22, decision 21)

The refused set, as `names.py` holds it — general category in `{Cc, Cf, Cs, Co, Cn, Zl, Zp}`, or one
of the `Default_Ignorable_Code_Point` ranges of `DerivedCoreProperties.txt` (Python has no accessor):

```python
_DEFAULT_IGNORABLE = (  # DerivedCoreProperties.txt, Default_Ignorable_Code_Point
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)
```

`auth.preferences`: `KNOWN: Mapping[str, frozenset[str]] = {"clock": frozenset({"12h", "24h"})}`;
`@dataclass(frozen=True) class PreferencesPatch: set: dict[str, str]; remove: frozenset[str]`;
`class InvalidPreferencesError(ValueError)` with `.errors: dict[str, list[str]]`;
`parse_patch(body: Mapping[str, object]) -> PreferencesPatch`.

| Test | Proves | Expected red |
|---|---|---|
| `test_refused_examples` — parametrized over Req 1's five: `"Grace​"`, `"Graceㅤ"`, `"Gr͏ace"`, `"Grace\x07"`, `" "` | each is refused | collection error `ModuleNotFoundError: No module named 'auth.names'` — every test in the file needs it |
| `test_accepted_examples` — `"José"` precomposed and `"José"` both → `"José"`; `"Zoë"`, `"李小龍"`, `"O'Brien"`, `"Ada  Lovelace"` (inner spaces kept), `" ada "` → `"ada"`, `"⠀"` | accepted, stored form | same |
| `test_each_refused_category_alone` — one inner char each: Cc `\x1f`, Cf `⁦`, Cs `\ud800`, Co ``, Cn `͸`, Zl ` `, Zp ` ` — **inside** the name (`str.strip()` would remove a trailing ` `) | every category, each on its own | same |
| `test_default_ignorables_outside_cf` — `ᅟ`, `️`, `\U000e0100`, `឴` inside a name | the range table, not only Cf | same |
| `test_length_after_trim_and_nfc` — 100 accepted; 101 refused; 100 plus surrounding spaces accepted; 99 letters + `é` (101 code points before NFC, 100 after) accepted; `""` refused | both sides of 1 and 100, counted after normalising | same |
| `test_stored_form_trims_and_composes_without_validating` — `" José "` → `"José"`; `" Ada​ "` → `"Ada​"` (kept, not refused) | decision 15's no-op input; the migration's step | same |
| `test_key_ignores_case_and_form` — `"José"`/`"José"`/`"JOSÉ"` one key; `"Strauß"`/`"STRASSE"` one key; `"Ada"` vs `"Adb"` differ | decision 12 (fails a `lower()` build on `ß`) | same |
| `test_first_free` — none taken → `"X"`; `{"x"}` → `"X 2"`; `{"x","x 2"}` → `"X 3"`; `{"x 2"}` → `"X"`; a 100-char base taken → 98 chars + `" 2"` | Req 3, decision 18 | same |
| `test_provision_name` — `"Gr​ace"` → `"Grace"`; `"​"` with `ada@x` → `"ada"`; both empty → `"user"`; 150 letters → 100 | decision 17 | same |
| `test_dedupe_keeps_the_oldest_and_suffixes_in_order` — `[Sam, sam, "SAM "]` → `Sam`, `sam 2`, `SAM 3` | Req 4's order and the iteration | same |
| `test_dedupe_never_takes_a_kept_name` — `[X, X, "X 2"]` → `X`, `X 3`, `X 2` | decision 21 | same |
| `test_dedupe_finds_duplicates_only_normalising_reveals` — `["José", " José"]` → `José`, `José 2` | Req 4 | same |
| `test_dedupe_names_an_empty_name` — `"   "` with `bob@x` → `"bob"` | decision 22 | same |
| `test_parse_patch` (in `test_preferences.py`) — `{"clock":"24h"}` sets; `{"clock":None}` removes; `{}` empty; `{"theme":"dark"}` → `errors["theme"]`; `"13h"`, `12`, `True` → `errors["clock"]`; `{"clock":"13h","theme":1}` → both keys at once | Req 6, decision 26 | `ModuleNotFoundError: No module named 'auth.preferences'` |

Each test gets the house one-line docstring saying what breaks if the rule goes. Leave uncommitted.

## Task 2: The routes, the SQL, the race and the migration (RED)

**Wire contract** (Tasks 4 and 7 depend on it):

```
PATCH /api/v1/users/me {displayName}       → 200 UserResponse | 400 errors.displayName | 409 errors.displayName
GET   /api/v1/users/me/preferences         → 200 {"clock"?: "12h"|"24h"}        | 404 deleted account
PATCH /api/v1/users/me/preferences {clock?: "12h"|"24h"|null} → 200 same shape | 400 errors.<key> | 404
409 body: {type, title, status: 409, detail: "That name is already taken.", errors: {displayName: ["That name is already taken."]}}
```

**Store interfaces** (`auth.identities`): `class NameTakenError(Exception)`;
`async rename_user(session, user: User, name: str) -> bool` — `name` already normalised; returns
`False` and writes nothing when it equals `user.display_name`; flushes inside a SAVEPOINT and raises
`NameTakenError` on `ux_users_display_name_key`; bumps `version` and `updated_at` otherwise.
`provision_user` keeps its signature. **`auth.preferences`:** `async read(session, user_id) -> dict[str, str]`;
`async apply_patch(session, user_id, patch: PreferencesPatch) -> dict[str, str]` (decision 24).

`test_users.py` (modify), through Dex as its other tests do:

| Test | Expected red |
|---|---|
| `test_a_name_is_stored_trimmed_and_in_nfc` — `"  José  "` → 200 `"José"`, and `GET /users/me` agrees | assertion: today stores the raw string |
| `test_an_invalid_name_is_refused` — parametrized over Req 1's five refused examples: 400, `errors.displayName` present, name unchanged | `"Grace​"`, `ㅤ`, `͏`, `\x07` pass today (200) — assertion; `" "` passes too (no trim) |
| `test_saving_the_name_you_have_changes_nothing` — `" ada "`: 200, and `users.version` (read with `sessions`) unchanged | assertion: version bumps today |
| `test_a_taken_name_is_409_naming_nobody` — Grace exists as `"grace"`; Ada sends `"GRACE"`: 409, `detail` and `errors.displayName` as above, body contains neither Grace's id, email nor any workspace name; Ada still `"ada"`. Same test: Ada sends `"Grace Hopper"` → 200 | 200 where 409 is expected |
| `test_names_colliding_only_after_nfc_are_taken` — Grace renames to `"José"`; Ada sends `"josé"` → 409 | 200 |
| `test_changing_only_your_own_capitals_is_allowed` — Ada `"ada"` → `"ADA"`: 200 `"ADA"`; **then** Grace sends `"ada"` → 409 (the key followed the rename and still holds the name) | assertion: Grace's `"ada"` is 200 today. The first half is the guard (the index never refuses the caller's own row); the second its positive — a build that refused own-capitals, or left the old key behind, fails one half |
| `test_a_legacy_name_can_be_saved_unchanged` — Ada's name set through the ORM to `"Ada​"` (as the migration keeps such names, decision 22); PATCH `" Ada​ "` → 200 and `users.version` unchanged; PATCH `"Ada​x"` → 400 `errors.displayName` | assertion: today the first PATCH bumps `version`. Decision 15's order |
| `test_a_deleted_accounts_name_stays_taken` — Grace signed in, then `deleted_at` set (as `test_deleted_accounts.py:29`); Ada sends `"grace"` → 409 | 200 |
| existing `test_an_empty_display_name_is_refused`, `test_a_null_display_name_is_refused` | unchanged, still pass — 400 both before and after |

`test_display_names.py` (create) — store level, two sessions from `sessions`, so the interleaving is
forced. The wait for "B is blocked" is a module helper, `wait_until_blocked(sessions)`: it polls
`pg_stat_activity` every 50 ms for a backend in this database with `wait_event_type = 'Lock'`, and
after **5 seconds** calls `pytest.fail("B never blocked on the name index")` — never a sleep, never
unbounded. Wherever no lock exists yet, that message is the red:

| Test | Proves | Expected red |
|---|---|---|
| `test_two_renames_to_one_name_one_wins` — users Grace/Alan seeded; A: `rename_user(grace,"Sam")` flushed, not committed; B: `rename_user(alan,"Sam")` in a task, seen blocked; A commits; B raises `NameTakenError`; `count(*) WHERE display_name_key='sam'` is 1 | the index, not a pre-check, is the control (a SELECT-then-UPDATE build lets B through) | `AttributeError: module 'auth.identities' has no attribute 'rename_user'` (A's first step) |
| `test_a_rename_racing_a_first_sign_in` — A: `rename_user(grace,"X")` uncommitted; B: `provision_user(email=new, display_name="X")` blocked; A commits; B's user is `"X 2"`, its workspace `"X 2's Workspace"`, B committed without error | *Where the rules meet* 2 | `AttributeError: … no attribute 'rename_user'` — A's first step, before anything else runs; every path of the test needs it |
| `test_two_first_sign_ins_with_one_name` — the same with two `provision_user` calls; afterwards the two names are `"Sam"` and `"Sam 2"` | Req 3, two at once | `Failed: B never blocked on the name index` after 5 s — with no index B's insert never waits, so the poll, not the `"Sam"`-twice assertion, is what fails first |
| `test_a_taken_idp_name_gets_the_first_free_suffix` — through Dex: Grace renames to `"alan"`; Alan signs in for the first time; his `displayName` is `"alan 2"` and his own workspace is `"alan 2's Workspace"` | Req 3 through the real callback | assertion |
| `test_a_deleted_accounts_name_is_skipped_at_sign_in` — a deleted user holds `"alan"`; Alan's first sign-in → `"alan 2"` | deleted rows count | assertion |

`test_migration_0002.py` (create) — its own database, `auth_migration`, from a module fixture calling
`testkit.databases.service_database(postgres_server, "auth_migration", <upgrade to "0001">)`; each test
first runs `command.downgrade(cfg, "base")` then `command.upgrade(cfg, "0001")` through
`auth.migrations.alembic_config` and `run_sync` (as `migrations.py:33-46`), inserts rows with explicit
`created_at`, then upgrades to `"0002"`:

| Test | Expected red |
|---|---|
| `test_names_are_trimmed_and_normalised` — `" José "` → `"José"` | `alembic.util.exc.CommandError: Can't locate revision identified by '0002'` |
| `test_duplicates_are_renamed_except_the_oldest` — `"Sam"` (newest id, **oldest** `created_at`), `"sam"`, a deleted `"SAM"`: the oldest by `created_at` keeps `"Sam"`, others suffixed | same |
| `test_the_index_exists_after_the_upgrade` — inserting a second `"sam"` raises `IntegrityError` naming `ux_users_display_name_key`; a distinct name inserts | same |

`test_preferences.py` (create):

| Test | Expected red |
|---|---|
| `test_no_row_reads_as_empty_and_creates_nothing` — `{}`, `count(*) FROM user_preferences` = 0 | 404 (no route) |
| `test_a_patch_is_stored_and_read_back` · `test_null_removes_a_key` · `test_the_last_write_on_one_key_wins` | 404 |
| `test_an_unknown_key_is_400_and_nothing_changes` — after `clock: "12h"`, `{"clock":"24h","theme":"dark"}` → 400 `errors.theme`; GET still `"12h"` | 404 |
| `test_a_bad_value_is_400` — `"13h"` → `errors.clock` | 404 |
| `test_a_deleted_account_is_404` — GET and PATCH, **asserting `detail == "This account no longer exists."`** | assertion on `detail`: today's 404 is the router's generic one, so the test can't pass vacuously |
| `test_preferences_follow_the_user_across_workspaces` — set under one token, switch workspace (`/auth/switch-workspace`), read the same | 404 |
| `test_two_writers_on_different_keys_both_land` — store level, `apply_patch` in two sessions with `PreferencesPatch(set={"clock":"24h"})` and `PreferencesPatch(set={"probe":"1"})` (the store takes a parsed patch; the route alone validates); A uncommitted, B blocked (polled as above), A commits, B commits → both keys. **Import `auth.preferences` inside the test**, so its `ModuleNotFoundError` fails this test alone | `ModuleNotFoundError` in this test only |
| `test_preferences_need_a_token` — GET and PATCH with no bearer → 401 | 404: no route matches, so `require_user` never runs |

`test_r1_unreachable.py` (modify): `test_a_rename_and_a_preference_fail_open` — under `r1_down`,
`PATCH /users/me` → 200 and `PATCH …/preferences` → 200. Red: the preferences half, 404.

`test_schema.py` (modify): `a_user(email="ada@example.com", name="Ada Lovelace")` takes the name as
a parameter; `test_email_uniqueness_ignores_case` passes **distinct names** (`"Ada One"`, `"Ada Two"`)
— defaulting the name from the email would not do, since `ada@…`/`ADA@…` casefold to one key — and
asserts the error names `users_email_key`. Red: none needed — both pass before and after; the change
keeps the email test from passing on the name index once it exists.
Add `test_a_display_name_differing_only_in_case_is_refused` — red: no `IntegrityError` raised.
`conftest.py`: `TABLES` gains `"user_preferences"` first. Leave uncommitted.

## Task 3: The journey (RED)

**Files:** `tests/bdd/features/settings.feature`, `tests/bdd/steps/test_settings_steps.py` (create,
`scenarios("../features/settings.feature")`, `pytestmark = pytest.mark.bdd`), `tests/bdd/conftest.py`
(`ALAN = "alan@collabhub.dev"`, session-scoped `alan_context`, function-scoped `alan`, exactly as
`ada`/`grace`), `tests/bdd/pages/chat_page.py`.

```gherkin
@bdd
Feature: Settings

  Everyone has one name across CollabHub, and it is theirs to change. Somebody
  who renames themselves sees the new name at once; everyone else sees it the
  next time their copy of the workspace's people is fetched — reloading is enough.

  Background:
    Given Ada is signed in

  # Alan's name is never put back: renaming him to the name he already has is a
  # no-op, so a rerun against a kept stack still passes.
  Scenario: Grace sees the name Alan gives himself on his message
    Given Ada has created a public channel named "general"
    And Alan has sent "the machine is thinking" in "general"
    When Alan changes his display name to "Alan Turing"
    Then Alan's sidebar shows him as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the machine is thinking" written by "Alan Turing"
```

New phrases: `Given Alan has sent "{body}" in "{channel}"` (as `ada_has_sent`), `When Alan changes
his display name to "{name}"`, `Then Alan's sidebar shows him as "{name}"`, `Then Grace sees "{body}"
written by "{name}"` — quoted because the name is a value, not a persona; it lives in this module, so
it can't collide with `test_message_steps.py`'s `written by Ada`. Reused verbatim: `Given Ada is signed
in`, `Given Ada has created a public channel named "{name}"`, `When Grace reloads CollabHub`, `When
Grace opens the "{name}" channel`.

`ChatPage` gains (all `data-testid`, retrying `expect`): `open_settings()` — clicks `current-user`,
waits for `settings-display-name` to be visible; `change_display_name(name)` — fills it; if
`settings-save` is enabled, clicks it and waits for `settings-saved`; if disabled the field already
holds `name` (the rerun case) and nothing is sent; `shows_current_user(name) -> bool` —
`expect(current-user).to_have_text(name)`. `has_author(text, name)` already exists (`chat_page.py:256`).

Expected red: `uv run pytest tests/bdd --collect-only -q` collects the scenario; it can't run before
the code-writer. At the code-writer's run, before the GREEN SPA, it fails at `open_settings`:
`current-user` is a `<p>`, so no `settings-display-name` ever appears. Leave uncommitted.

## Task 4: The SPA's red (RED)

**Interfaces** Task 8 implements:
- `lib/auth/api.ts`: `type Clock = '12h' | '24h'`; `interface Preferences { clock?: Clock }`;
  `type PreferencesPatch = { clock?: Clock | null }`; `updateMe(accessToken, body: { displayName: string }): Promise<Profile>`;
  `preferences(accessToken): Promise<Preferences>`; `updatePreferences(accessToken, patch): Promise<Preferences>`
- `lib/auth/session.ts`: `updateProfile(profile: Profile): void` (replaces the profile only while signed in as `profile.id`, and counts the edit for `adopt()`, decision 37); `signIn(provider = 'dex', returnTo?: string)` (writes the path, or clears it when absent); `takeReturnPath(): string | null` (read once, then cleared; `null` unless it starts `/` and not `//`); a failed `completeSignIn` clears the path (decision 28)
- `lib/time.ts`: `timeOfDay(iso: string, clock: Clock | null): string` — `{ hour: '2-digit', minute: '2-digit' }` plus `hourCycle`; `dateAndTime(iso, clock)` — `{ dateStyle: 'medium', timeStyle: 'short' }` plus `hourCycle`. `null` adds nothing, so output equals today's
- `features/settings/usePreferences.ts`: `preferenceKeys.mine(userId)`, `usePreferences(accessToken, userId)`, `useSetClock(accessToken, userId)`; `useProfile.ts`: `profileKeys.mine(userId) = ['user-profile', userId]`, `useProfile`, `useUpdateDisplayName`; `ClockProvider.tsx`: `ClockProvider({ accessToken, userId, children })`, `useClock(): Clock | null`; `SettingsPage({ accessToken, userId })`
- `stores/chat.ts`: `lastChannelId: string | null` (set by `setActiveChannel(id)` for non-null, kept on `null`), `resetLastChannel()`

**Markup** the tests query (roles for Vitest, test ids for the page object): heading `Settings`;
section headings `Profile` and `Preferences`; `<input aria-label="Display name" data-testid="settings-display-name">`;
`<button data-testid="settings-save">Save</button>`; `<p role="status" data-testid="settings-saved">Saved</p>`;
the field's error `<p role="alert" data-testid="settings-display-name-error">`; a `<fieldset>`
with legend `Clock` and radios labelled `Automatic`, `12-hour`, `24-hour`; the clock's error through
`ProblemBanner`; `<Link data-testid="settings-back">Back to chat</Link>`. `current-user` becomes
`<Link to="/settings" data-testid="current-user">{displayName}</Link>`.

`test/api.ts` gains `auth.preferences(prefs: Preferences)`, `auth.patchPreferences(reply)` and
`auth.patchMe(reply)`, each `reply` a value or `(body) => value | Promise<value>` (a promise is how a
test holds the request), and `auth.meBy(reply: (call: number) => Profile | Promise<Profile>)`, numbered
from 1 like `membersBy` (`test/api.ts:323`) — all recorded like the others.

**Holding the directory.** Every directory test below uses `scriptDirectory` (`test/directory.ts`):
the sidebar's `DirectMessageList` mounts `useWorkspaceMembers` on `/settings` too, so call 1 is the
shell's first fetch, and decision 31's invalidate makes the next one. Each test **says what every
call answers** and pins the cache write **while the post-save refetch is still held**, so an
invalidate-only build (the "next refetch" everyone else gets) fails: during the hold its cache still
holds the old name. Released calls answer the new name, as the server would after the commit.

| Test | Proves | Expected red |
|---|---|---|
| `lib/time.test.ts`: `automatic is the browser's format` (equals `toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})` for a local 13:05); `24h shows 13:05`; `12h shows no 13`; `24h shows midnight as 00:05, not 24:05`; `dateAndTime` 12h/24h pair | the three choices; decision 33. Dates built as local time (`new Date(2026, 9, 17, 13, 5)`) so the TZ doesn't matter | `Failed to resolve import "./time"` — every test needs it |
| `ClockProvider.test.tsx`: `each formatter follows the clock` — `MessageItem`, `ThreadSummary`, `SearchResult` under the provider with `{clock:'24h'}` show `13:05`; with `{}` the automatic text | Req 7's three places | `Failed to resolve import "./ClockProvider"` |
| `ClockProvider.test.tsx`: `a changed clock re-renders cached messages and fetches nothing` — after first render, `setQueryData(preferenceKeys.mine(id), {clock:'24h'})`; the time changes; `requests()` holds no request after the change | *Where the rules meet*, the clock and cached lists | same |
| `SettingsPage.test.tsx` — every test renders `<App />` at a route, fresh module per test as `App.test.tsx:55-59` does, so the real router, guard and shell are the parent | | the file imports only `App` and existing helpers, and writes cache keys as literals (`['workspace-members', WORKSPACE_ID]`), so it loads; each test fails at its first query (`findByRole('textbox', {name: 'Display name'})` times out: `/settings` is *No such page*) |
| `the form shows the server's name, not the session's` — `me` answers `Ada Lovelace` on the first call (sign-in) and `Ada L` after; the field holds `Ada L`; the `24-hour` radio is checked from `GET preferences` | Req 8, decision 35 | as above |
| `it is reached from the sidebar's name` — clicking the `Ada Lovelace` link lands on `/settings` | Req 8 | link not found |
| `Save is off while unchanged or invalid` — unchanged, `"   "`, 101 letters: disabled; 100 letters and `"Ada L"`: enabled | decision 30, both sides of 100 | as above |
| `a save updates the sidebar, the directory and says Saved` — call 1 answers Ada as `Ada Lovelace` and Grace, and is settled (`settleDirectory`); call 2 is held. Save: PATCH body is `{displayName:"Ada L"}`; `Saved` shown; **with call 2 still held** the `current-user` link reads `Ada L`, the `['workspace-members', WORKSPACE_ID]` entry for Ada reads `Ada L` and Grace's is untouched; then call 2 is released with `Ada L` and the entry still reads it | Req 5 "at once", *Where the rules meet* 3; decision 31 | as above |
| `a 409 is shown on the field and nothing changes` · `a 400 is shown on the field` — the alert carries `errors.displayName[0]`; sidebar unchanged | Req 8 errors | as above |
| `a save that lands after leaving still updates the session and directory` — PATCH held; click `Back to chat`; release; the sidebar reads the new name and the cache holds it | *Paths*: unmount mid-save, decision 31 | as above |
| `an unsaved edit is dropped on leaving` — type, leave, come back: the field holds the server's name; `window.confirm` (spied) never called | *Paths* | as above |
| `Back to chat returns to the last channel, or home on a direct load` — after opening `/c/<id>` then Settings → `/c/<id>`; direct load of `/settings` → `/` | decision 29 | as above |
| `a workspace switch on Settings changes nothing` — type a draft, switch workspace through the sidebar; the draft and the clock remain, and no further `GET me` or `GET preferences` after the switch's own `me` | *Paths* | as above |
| `a refetch in flight with the old name does not undo the rename` — call 1 answers the old name and settles; call 2 is held and started with `queryClient.refetchQueries({ queryKey: ['workspace-members', WORKSPACE_ID] })` (the query has data); call 3 is held; save; with call 3 held the entry reads `Ada L`; release call 2 with the **old** name: still `Ada L`; release call 3 with `Ada L` | decision 31, the cached case (`invalidateQueries`' cancel) | as above |
| `a first directory fetch still out does not undo the rename` — direct load of `/settings`; call 1 is held (no data yet); save; release call 1 with the **old** name; call 2 answers `Ada L`; after `settleDirectory` the entry reads `Ada L` | decision 31, the uncached case: an invalidate-only or set-then-invalidate build joins call 1 (`query.ts:411-418`) and ends on the old name; only the `cancelQueries` first passes | as above |
| `a directory fetch that lands before the save is overwritten by it` — call 1 settles with the old name, then save, call 2 held: the entry reads `Ada L` | the other order of the race | as above |
| `choosing a clock saves at once` — `24-hour` → PATCH `{clock:'24h'}`; `Automatic` → `{clock:null}` | Req 7 | as above |
| `a failed save puts the previous clock back and says why` — previous `12-hour`; choose `24-hour`, PATCH 500 Problem: `12-hour` checked again, an alert shown | Req 7, *Timing* | as above |
| `a second clock choice waits for the first to reach the server` — first PATCH (`24h`) held; choose `12-hour`: `12-hour` is checked at once (the positive anchor), and `requests()` holds one preferences PATCH; release the first; then a second PATCH with `{clock:'12h'}` is sent, and `12-hour` stays | decision 34's `scope`: an unscoped build sends both at once and fails the count | as above |
| `a late failure does not undo a newer choice` — `24-hour` held; choose `12-hour`; release the first as a 500: `12-hour` stays checked, the `12h` PATCH is then sent and succeeds, and `12-hour` is still checked after it | decision 34 | as above |
| `App.test.tsx`: `a signed-out visitor to /settings is back there after signing in` — guard → `Sign in` clicked (`location.assign` stubbed as `session.test.ts:314-315`) → re-render at `/auth/callback?code=…` with the verifier stored and exchange/me/workspaces stubbed → lands on `/settings` | *Paths*, decision 28 | lands on `/` — assertion |
| `App.test.tsx`: `a direct load of /settings renders the page` | *Paths* | *No such page* |
| `session.test.ts`: `updateProfile replaces the signed-in profile` · `…ignores another user's` · `…does nothing signed out`; `takeReturnPath returns once`; `refuses //host and absolute URLs` | Task 9's rules | `session.updateProfile is not a function` / `takeReturnPath is not a function` — the module exists, so each fails alone |
| `session.test.ts`: `a renewal whose me predates a rename keeps the new name` — signed in as `Ada Lovelace`; renewal fires (fake `setTimeout`, as `session.test.ts:213`), its `me` (`auth.meBy` call 2) held; `updateProfile({…, displayName:'Ada L'})`; release `me` with `Ada Lovelace`: the profile reads `Ada L`, and the new token is adopted. Same through `changeWorkspace` | decision 37, the race in this order; the *Paths* row "workspace switch while on `/settings`" | `updateProfile is not a function` |
| `session.test.ts`: `a renewal that starts after a rename adopts what it fetches` — `updateProfile(Ada L)`, then a renewal whose `me` answers `Ada M` (a rename in another tab): profile reads `Ada M` | the guard's positive: the count is read at the start of `adopt`, so it never freezes the profile | `updateProfile is not a function` |
| `session.test.ts`: `a failed sign-in forgets the return path` — `signIn('dex','/settings')`, then `completeSignIn(?error=access_denied)`: `takeReturnPath()` is `null`; `signIn('dex','/settings')` then `signIn('dex')`: `null`; and the positive, `signIn('dex','/settings')` alone: `'/settings'` | decision 28 | `takeReturnPath is not a function` |
| `stores/chat.test.ts`: `lastChannelId survives leaving a channel` · `resetLastChannel clears it` | decision 29 | assertion `undefined` / `is not a function` |

`App.test.tsx`'s `aReturningUser`, and the arrangements in `ChatLayout.test.tsx`,
`ChatLayout.attachments.test.tsx` and `CreateChannelDialog.test.tsx`, gain `auth.preferences({})`:
the shell will fetch it and an unstubbed request fails the test (`setup.ts:32`). They pass before
and after. Run with `npm --prefix src/frontend test -- <paths>`; `tsc` is red until Task 8 for the
same reasons. Leave uncommitted.

## Task 5: The rules (GREEN)

- [ ] `auth/names.py` to Task 1's interface. `_refused(ch)`: `unicodedata.category(ch) in _REFUSED or any(lo <= ord(ch) <= hi for lo, hi in _DEFAULT_IGNORABLE)`. Messages: `"A display name is required."`, `"A display name can be at most 100 characters."`, `"A display name cannot contain invisible or control characters."`.
- [ ] `auth/preferences.py`: `parse_patch`, then `read` and `apply_patch` (decision 24 — a `postgresql.insert(...).on_conflict_do_update(...)` whose `prefs` is `UserPreferences.prefs.op("||")(cast(set, JSONB)).op("-")(cast(remove, ARRAY(Text)))`; bound parameters only, CH006).
- [ ] Task 1 passes. Leave uncommitted.

## Task 6: The tables (GREEN)

```python
# 0002_unique_display_names.py — the key is computed by auth.names, never by SQL.
op.add_column("users", sa.Column("display_name_key", sa.String(), nullable=True))
rows = bind.execute(sa.text(
    "SELECT id, display_name, email FROM users ORDER BY created_at, id")).all()  # deleted rows too (D46)
for user_id, name in names.dedupe(rows).items():
    bind.execute(sa.text("UPDATE users SET display_name = :n, display_name_key = :k WHERE id = :id"),
                 {"n": name, "k": names.name_key(name), "id": user_id})
op.alter_column("users", "display_name_key", nullable=False)
op.create_index("ux_users_display_name_key", "users", ["display_name_key"], unique=True)

# 0003_user_preferences.py
op.create_table(
    "user_preferences",
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("prefs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
)
```

- [ ] `models.py`: `User.display_name_key` + `@validates("display_name")` setting it from `names.name_key`; `UserPreferences`. The docstring says why the key is stored.
- [ ] Task 2's migration and schema tests pass. Leave uncommitted.

## Task 7: The rename, sign-in and the routes (GREEN)

- [ ] `identities.py`: `NameTakenError`, `rename_user`, `_is_name_conflict(exc)` (decision 16), `_taken_keys(session, base)` (decision 19 — `User.display_name_key == k` or `.startswith(k + " ", autoescape=True)`, no `deleted_at` filter, waived), and `provision_user`'s loop. The own workspace is named from the stored name.
- [ ] `schemas.py`: `UpdateUserRequest.display_name: str | None = None`.
- [ ] `routers/users.py`: `update_me` — null → existing 400; `names.stored_form(raw) == user.display_name` → no write (decision 15, before validation); else `normalise_display_name` (→ 400 `errors.displayName`), `rename_user` (→ 409), then the avatar branch as now; `updated_at`/`version` move into `rename_user` and the avatar branch so a no-op writes nothing. `GET`/`PATCH /me/preferences`, declared **before** `/{user_id}`; body `dict[str, Any]`; 404 as `/me`. No name in any log.
- [ ] Tasks 1–2 pass. Auth integration: the recorded count plus Task 2's. Leave uncommitted.

## Task 8: The SPA (GREEN)

- [ ] `lib/auth/api.ts` calls (PATCH with `JSON.stringify`); `lib/time.ts`.
- [ ] `usePreferences` (query, `refetchOnMount` default) and `useSetClock` (decision 34, with `scope: { id: 'user-preferences' }`); `useProfile` and `useUpdateDisplayName` (decision 31; all writes in the hook-level `onSuccess`, `cancelQueries` awaited before `setQueriesData`). `setQueriesData<WorkspaceMember[]>({ queryKey: ['workspace-members'] }, …)` maps only the member whose `user.id` is the profile's, and returns `undefined` for an entry with no data.
- [ ] `ClockProvider` around `ChatLayout`'s tree; `MessageItem`, `ThreadSummary`, `SearchResult` call `useClock()` and `lib/time` — their local `timeOfDay`/`when` go.
- [ ] `SettingsPage` (decisions 30, 35; the markup in Task 4); the `/settings` route in `App.tsx` as `SettingsRoute`, like `SearchRoute`; `WorkspaceSwitcher`'s link; `stores/chat.ts`'s `lastChannelId`, and `ChatLayout`'s existing workspace cleanup (`ChatLayout.tsx:51-57`) calls `resetLastChannel()`.
- [ ] Task 4 passes except the return path; `npm --prefix src/frontend run typecheck` clean. Leave uncommitted.

## Task 9: Sign-in returns to the route (GREEN)

- [ ] `storage.ts`: `returnPath` beside `pkceVerifier`, key `collabhub.returnPath`, with the same comment discipline.
- [ ] `session.ts`: `signIn(provider, returnTo)` writes it, or clears it when `returnTo` is absent; every `return false` in `completeSignIn` clears it; `takeReturnPath()`; `updateProfile` and `profileEdits`, read at the top of `adopt()` (decision 37):

```ts
async function adopt(pair: api.TokenPair): Promise<void> {
  const edits = profileEdits // before the fetch: an edit after this point wins over its `me`
  const [fetched, workspaceList] = await Promise.all([api.me(pair.accessToken), api.workspaces(pair.accessToken)])
  const kept = profileEdits !== edits && state.status === 'signedIn' && state.session.profile.id === fetched.id
  const profile = kept ? state.session.profile : fetched
  // …set() as today, with `profile`
```
- [ ] `App.tsx`: `Protected` → `<Navigate to="/sign-in" replace state={{ from: pathname + search }} />`; `SignIn` passes `useLocation().state?.from`; `Callback` → `navigate(signedIn ? (session.takeReturnPath() ?? '/') : '/sign-in')`.
- [ ] All of Task 4 passes. Leave uncommitted.

## Task 10: Docstrings

- [ ] `MessageItem.tsx:10-15` and `SearchResult.tsx:7-8` say "register D28 🔴 / no preference": rewrite to the clock. `ThreadSummary.tsx:6-7` likewise. `users.py`'s module and `update_me` docstrings gain the normalising and D46. `identities.provision_user`'s docstring gains the suffix. `steps/conftest.py:24-31`'s `ADA_NAME` comment stays true (Ada is never renamed by the suite).
- [ ] `src/frontend/README.md:60-62` says "D28 🔴" and "if D28 ever lands": D28 is 🟢 now, and settles where preferences live; there is still no theme preference (D26 light-only). Rewrite those two lines to say so.
- [ ] Sweep: `grep -rn "D28\|Renames are not covered\|preferences" docs/design src/frontend src/services/auth --exclude-dir=node_modules` and fix every line this slice makes false.

## Task 11: The record

- [ ] Register: D28 → 🟢 *Decided (2026-10-17)* with *Decided already* 7 and *built against it*; new D46 in *Platform / Auth* — global unique names, the leak it accepts, the stored key (decision 11), and **the soft-delete exception it makes** (the name key and the taken-keys read include deleted rows). Both in the "Settled" list at the top.
- [ ] Conventions §3 *Soft delete*: the "Two documented exceptions" become three — **`users` in Auth (D46): a display name stays taken after its account is deleted, so the taken-keys read in `identities.provision_user` and the migration's dedupe read do not filter `deleted_at`, and the unique index covers deleted rows.** Every other `users` read still filters.
- [ ] ADRs with the `adr-writer` skill: `261017-user-preferences-in-auth.md` (D28), `261017-display-names-unique-across-collabhub.md` (D46, with decision 12's case folding).
- [ ] Doc 01: §3 the two preferences routes, the 409 and the normalising on `PATCH /users/me`; §4 `display_name_key` with its index, `user_preferences`; §5.1 the first-sign-in suffix rule (decisions 17–19).
- [ ] Doc 06: §3 `/features/settings` and the `/settings` route; §5.2 *Names*: the renamer's own tab updates at once (decision 31); §4 the return path (decision 28 — `sessionStorage` now holds the verifier and one non-secret path) and the profile kept over an older `adopt` (decision 37); §9's D28 paragraph rewritten.
- [ ] Conventions §5.4: the D46 exception — a display-name 409 may reveal that a name exists in another workspace, and names nobody and no workspace.

## Task 12: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e`: each layer once —
  `integration` because Auth's SQL changes, `e2e` because a journey is added and the sign-in guard
  every journey passes through changes. Counts at or above the baseline; `-- -k settings` only to
  iterate on a failure.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; every waiver names each checker that fires on its line.
- [ ] **First real run**, `docker compose up -d --build`: rename Ada and watch her sidebar and her own
  message; try Grace's name in capitals; choose 24-hour and look at a message after noon; sign out on
  `/settings` and sign back in. Fix what it finds with a test and record it below.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Filled in by the code-writer, round 1. No bug was found by a run; the departures:

1. **`useClock` and its context are in `features/settings/useClock.ts`, not `ClockProvider.tsx`.**
   The lint rule `react-refresh/only-export-components` rejects a component file that also
   exports a hook, and a waiver is not warranted when a file split fixes it. `ClockProvider`
   is still exported from `ClockProvider.tsx` as the tests import it. No test pins the
   location of `useClock`.
2. **`directoryKeys.all = ['workspace-members']`** added to `useWorkspaceMembers.ts`, the
   prefix a rename writes across. Same key as the tests' literal.
3. **`usePreferences` uses TanStack's defaults** (stale at once, so the page's mount refetches);
   only `useProfile` sets `refetchOnMount: 'always'`. Equivalent for decision 35; pinned by
   `shows the server's name and clock`.
4. **The form is not rendered at all until the profile has been fetched after mount** (a
   "Loading…" line instead), rather than rendering it disabled: the tests' `user.clear` refuses
   a disabled field. Matches decision 35's wording. Pinned by the same test.
5. **An unchanged avatar is no longer a write.** `update_me`'s avatar branch bumps
   `version`/`updated_at` only when the avatar value changes (plan: "a no-op writes nothing").
   No test pins it.
6. **Plan-review 2's optional item (two clock saves failing in a row restore a value the server
   never stored) is not fixed.** The next visit reads from the server. No test.
7. **A flake**: `App.test.tsx › sends a signed-out visitor who opens a channel link to sign in`
   failed once in a whole-suite run (`location()` still `/c/…`), and passed alone and in two
   further whole runs. It does not touch the new code path; the location spy's effect had not
   yet run when the button was found.

## Not in this plan

- A grapheme-aware length; lookalike detection; the ZWJ/ZWNJ names Decided 5 accepts refusing.
- Refreshing the token's `name` claim on a rename.
- Any preference but `clock`; any change to `avatarAsset`.

## Self-review

- **Issue coverage:** Req 1 → Tasks 1, 2 (`test_users`), 5, 7; Req 2 → 1 (key), 2 (409, NFC, case,
  deleted, race), 6, 7; Req 3 → 1 (`first_free`, `provision_name`), 2 (`test_display_names`), 7;
  Req 4 → 1 (`dedupe`), 2 (migration), 6; Req 5 → 4 (save, unmount, races), 8; Req 6 → 1, 2, 5–7;
  Req 7 → 4 (`time`, `ClockProvider`, revert), 8; Req 8 → 3, 4, 8, 9. *Where the rules meet*: 1 →
  `test_two_renames_to_one_name_one_wins`; 2 → `test_a_rename_racing_a_first_sign_in`; 3 → `a save
  updates the sidebar…`, the three directory-race tests and the two `adopt` race tests; 4 and 5 → *Deliberately unchanged*; 6 → `a changed clock
  re-renders…`; 7 → `test_two_writers_on_different_keys_both_land`, `test_the_last_write_on_one_key_wins`.
  *Paths*: each row → the `SettingsPage.test.tsx` / `App.test.tsx` test of the same words; deleted
  account → `test_a_deleted_accounts_name_stays_taken`, `test_a_deleted_account_is_404`; second tab
  and Grace's view → *What no test covers* and the journey.
- **Names:** `display_name_key`, `ux_users_display_name_key`, `user_preferences`,
  `['user-preferences', userId]`, `['user-profile', userId]` everywhere.
- **Known ripple:** `test_schema.py`, `conftest.py`, and four SPA test files' stubs — all RED (Tasks 2, 4).

## Review responses

Round 1, `reviews/plan-reviewer-1.md`:

1. **Fixed.** `test_a_rename_racing_a_first_sign_in`'s red is now the `AttributeError` on `rename_user`. `wait_until_blocked` polls for at most 5 s and fails with `"B never blocked on the name index"`, which is now `test_two_first_sign_ins_with_one_name`'s stated red (Task 2).
2. **Fixed.** Task 4 has a *Holding the directory* note: every call's answer is stated, and the write is asserted while the post-save refetch is held, so a build that only invalidates fails. The save test and the three race tests name the call numbers they hold.
3. **Fixed, three rules, each tested.** (a) Session profile: new decision 37 (`profileEdits` read at the top of `adopt`), with two `session.test.ts` tests — the race in this order, through a renewal and through `changeWorkspace`, and the guard's positive. (b) Directory not cached yet: decision 31 now awaits `cancelQueries` before `setQueriesData`. I checked `query.ts:411-418` in the installed source: the invalidate joins a fetch with no data, so you were right. Tested by `a first directory fetch still out…`. (c) Two clock saves: decision 34 adds `scope: { id: 'user-preferences' }` (checked in `mutation.ts:205-235`: `onMutate` still runs at once). Tested by `a second clock choice waits…`.
4. **Fixed.** Task 11 adds the third exception to Conventions §3, and the D46 entry names it. The CH009 waiver reason cites both (decision 36, Global constraints).
5. **Fixed.** Decision 28: every `signIn` overwrites or clears the path, and every failed `completeSignIn` clears it. Tested by `a failed sign-in forgets the return path`, with its positive.
6. **Fixed.** Decision 19 says what happens after the 10th loss: the violation is re-raised and that one sign-in fails. It is marked **assumed**, with the reason it is unreachable in practice and the alternative.
7. **Fixed.** Grace sends `"ada"` → 409 after Ada becomes `"ADA"`, so the test now fails at red.
8. **Fixed.** Decision 15 (**assumed**): the no-op check runs first, on `stored_form`, so a legacy name can be saved unchanged. Covered by the new `stored_form` interface and unit test, and by `test_a_legacy_name_can_be_saved_unchanged`.
9. **Fixed.** `a_user` takes the name, and the email test passes distinct names. The README's "D28 🔴" is now a Task 10 item. The citations in decisions 16, 31 and 34 are checked against the worktree's `.venv` (SQLAlchemy) and the primary checkout's `node_modules` (TanStack 5.101.4, the lock's version, on `main`, which is this branch's base). The asyncpg range is corrected to `791-797`.
