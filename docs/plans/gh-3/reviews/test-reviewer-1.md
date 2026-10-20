# Test review — gh-3, round 1: changes_requested

The Auth, BDD and most SPA tests are sound: they fail for the reasons given, and the wrong builds I tried fail them. Two SPA
files are not: three tests in `clockSites.test.tsx` cannot pass against any correct build (they assert synchronously on a
TanStack update that is delivered on a timer), and one in `PreferencesSection.test.tsx` passes or fails depending on whether
the radios render before the first fetch. Both were invisible at red because the files fail to load. Four findings: 1 critical, 1 major, 2 minor.

## Expectations

Written from the issue, the plan (decisions 11–36, Tasks 1–4) and today's code
(`routers/users.py`: `PATCH /me` assigns the raw name, no trim, null → 400;
`identities.provision_user` inserts the raw name; no `auth.names`, `auth.preferences`,
`lib/time`, `features/settings`, `session.updateProfile`, `takeReturnTo`) — before opening any test.

| Behaviour | Fails today with | Vacuous version | Clauses to pin | Wrong build |
|---|---|---|---|---|
| Pure rules (`names`, `preferences`) | `ModuleNotFoundError` for the whole file — right, every test needs the module | Refused-char test on one char only; a length bound pinned on one side; NFC-before vs after length; U+2800 not shown accepted; dedup tested with input already in age order | trim = `str.strip()`; both NFC forms; each category alone; 100 ok/101 refused; "oldest by `created_at`" with newest-first input; hidden duplicates after normalisation | `lower()` instead of casefold (Straße); length before NFC; refuse U+2800; keep first in input order |
| Rename over REST (400/409) | assertion failures (200 instead of 409/400) — not a load failure | 409 test with no positive half; 409 body that doesn't check it names nobody; case test only one direction; "deleted name taken" with no deleted row actually soft-deleted | 409 text exact; capitals of own name allowed; NFC collisions both ways; deleted accounts included; global across workspaces | per-workspace uniqueness; pre-check SELECT only (race); `lower()` compare; 409 for self-same name |
| Concurrent rename / first sign-in race | assertion `[200,200]` | gather where one finishes before the other starts; sleep-based ordering | exactly one 200 and one 409, one row | pre-check without index |
| First sign-in suffix | `"ADA"` instead of `"ADA 3"` | only one taken name (so `X 2` and `X 3` coincide) | first *free* suffix, workspace named from result; never overwrites | suffix always 2; overwrite on return |
| Migration | assertion: unchanged (head 0001) | duplicates already normalised; oldest not deleted; one duplicate pair only | trim+NFC first; duplicates only visible after normalising; oldest keeps | rename by id order; dedupe before normalise |
| Preferences routes | 404 no route | GET that creates a row (asserted by COUNT); merge tested with one key; unknown key test without proving stored value unchanged | `{}` with no row, no insert; null removes; all-or-nothing 400; 404 for deleted; concurrency of different keys | read-modify-write merge; reject-partial |
| Fail-open R1 | 404 for preferences half | only one of two writes tested | both PATCHes 200 | adding denylist check |
| SPA time/clock | import not found (time, usePreferences) — whole file | formats checked under one locale where both clocks coincide (9:05); no PM time | 15:07 both ways | `hour12` instead of `hourCycle` |
| Profile form | module not found | Save disabled test one-sided; seeding from cache | disabled while unchanged/blank/>100 and enabled otherwise | seeds from cache; cancels nothing |
| Preferences UI | module not found | revert tested only in one failure order | serial saves; last wins; revert to confirmed | parallel saves |
| session / App | `updateProfile is not a function`, "No such page." | race test releases in one order only | epoch both orders | sticky flag |
| BDD journey | collection passes, steps bind | last Then reads local state | Grace after reload sees new name | – |

Also I will check: existing tests untouched (`test_schema.py` helper change is plan-sanctioned),
red reasons are not typos, and which new tests pass at the gate (plan calls a few green-by-design).

## What ran

- `uv run pytest src/services/auth/tests/unit` — 2 collection errors, `ImportError: cannot import name 'names'` / `'preferences'` from `auth`. Right: every test in each file needs the module.
- `uv run pytest` over the five Auth integration files — **33 failed, 12 passed**, as the report says. First lines match the report's table (`'  José  ' == 'José'`, `200 == 409`-style assertions, `404` for the missing route, `KeyError: 'detail'`, `ImportError … preferences` inside the one test that needs it, `DID NOT RAISE IntegrityError`, `AttributeError: display_name_key`). The 12 passes are the 8 old tests, the 3 plan-named guards and the 100-character test.
- `npm --prefix src/frontend test` — 21 failed, 503 passed; four files fail to load (`time`, `clockSites`, `ProfileSection`, `PreferencesSection`). One earlier run showed an old `App.test.tsx` test failing under load; the file alone and a second full run passed it (flaky timing, not the writer's change).
- `npm --prefix src/frontend run typecheck` — only missing-export/module errors plus the knock-on `TS7031`, as reported.
- `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` — no stub printed; every step binds.
- **Sketch (frontend)**, built to the plan's interfaces: `time.ts`, `usePreferences.ts` (decision 17), `useProfile.ts` (decision 16), `ProfileSection`/`PreferencesSection`, `session.updateProfile`/epoch/`takeReturnTo`/`signIn(returnTo)`, the three formatters.

| Sketch | Files | Result |
|---|---|---|
| Correct | `time.test`, `features/settings`, `session.test` | 58 of 62 green; red: `clockSites` ×3 and `PreferencesSection › refetches on window focus` — see findings 1, 2 |
| Correct, `clockSites` first test made `await vi.waitFor` | `clockSites` | that test goes green; the other two (still sync) stay red — confirms the cause |
| Parallel saves (no mutation `scope`) | `PreferencesSection` | `a second choice waits…` red |
| Non-latest response writes | `PreferencesSection` | `a second choice waits…` red |
| Failure restores the click's snapshot | `PreferencesSection` | `two failed saves…` red |
| Field seeded from the cache | `ProfileSection` | `on a revisit the field waits…` red |
| No cancel of directory fetches on success | `ProfileSection` | `on a revisit…` and `a directory fetch answered before the rename…` red |
| Sticky "renamed locally" flag | `session.test` | `a renewal that read the profile after a rename takes the server's` red |
| No epoch (always the fetched profile) | `session.test` | both "read the profile before a rename" tests red |

Not sketched, by reasoning: `App.test.tsx` (10 tests; each fails on the missing route, link or `takeReturnTo`, and the helpers were read), the Python unit tests (pure, but `names.py` needs the Unicode table; read case by case against the plan's rules) and the Auth integration tests (read; the race tests use a held transaction, not a sleep alone).

## Coverage

| Plan test / expectation | As written | Outcome |
|---|---|---|
| Task 1 `test_names` rows (all 14) | present, plus extras | present |
| Task 1 `test_preferences` rows | present | present |
| Task 2 `test_display_names` (17 rows) | present, plus 100-char | present |
| Task 2 schema, migration (5), preferences (10), R1 | present | present |
| Task 3 `time`, `clockSites`, `ProfileSection` (9), `PreferencesSection`, `session`, `App` (10) | present | present; findings 1–2 on two files |
| Task 4 journey, harness, page object | present; binds | present |
| Departure 1 (`chr()` constants for `\u` escapes) | reason given (tool decodes escapes); each named | accepted |
| Departure 5 (`api.ts` helper grew `failWith`, reply functions) | listed | accepted |
| Expectation: both sides of every clause | rename 100/101, own capitals, NFC both ways, deleted account, global scope, suffix with two taken names, migration with deleted oldest and hidden duplicates | met |

## Findings

### 1. Three clock tests assert synchronously on an update TanStack delivers later — critical
**Where:** `clockSites.test.tsx` — `a message time follows the stored clock`, `a thread summary time follows it`, `a search result time follows it` (`choose()` then an immediate `expect`) · **Checked:** sketch, correct build, ran: all three red after `choose(queryClient, '12h')` (`Received: 15:07`); making the first one `await vi.waitFor(...)` turned it green, the other two stayed red.
`choose` is a synchronous `act(() => queryClient.setQueryData(...))`. React Query tells observers on a `setTimeout(0)` batch, which a sync `act` does not flush, so the component has not re-rendered when the next line runs. No correct build can pass these — the test was a load failure at red, so the body never ran. Fix: make `choose` async and `await` the re-render (`await vi.waitFor(...)` around the assertion, or `await act(async () => …)` followed by a macrotask), in all three tests. Keep both directions and the "not 15:07" half.

### 2. The focus test counts the first GET before it has arrived — major
**Where:** `PreferencesSection.test.tsx › refetches on window focus` · **Checked:** sketch, correct build: `expected [] to have a length of 1 but got +0` at line 76.
`await vi.waitFor(() => expect(checked('Automatic').checked)…)` is satisfied before any answer, because with no data "Automatic" is already what a radio group shows (it did in the sketch; a build that renders the group before the fetch lands is the natural one). The recorded GET comes later. A build that happens to hide the radios until loaded passes; one that doesn't fails — over-pinning. Fix: wait on the request (`await vi.waitFor(() => expect(gets()).toHaveLength(1))`) before asserting, then leave and return, and wait on `gets()` reaching 2 as well as on the radio.

### 3. Report counts one test too many — minor
`PreferencesSection.test.tsx` has 9 tests; the report says 10. Cosmetic.

### 4. `chr()` constants rather than `\u` escapes — minor
Accepted (Departure 1, reason sound). The names carry their category in a comment; nothing to fix.

## Left for later stages

- Plan-reviewer round 2: a failed profile GET with `isFetchedAfterMount` true (stale or `undefined` name) — untested; the code-writer should show an error state, not seed the field.
- Decision 17: the radio during a focus refetch mid-save is correctly not pinned.
- `directoryRefresh.ts`'s `load` ignores the abort signal; in my sketch the cancel in `onSuccess` was enough for `a directory fetch answered before the rename…` to pass, but the code-reviewer should check it against the real tracker.
- `App.test.tsx` was not run against a build: the code-writer is its first real run (it uses 1 s `findBy` timeouts; one old test flaked once under a loaded full run).

## Checked and sound

- Every Auth integration test fails on the behaviour (assertion on 200-vs-409/400, 404 for the missing route), not on a typo or fixture; the four green-by-design guards are named so by the plan.
- Guards have their positive halves: 409 test ends with an accepted free name; own-capitals allowed beside Grace refused; deleted-name test ends with a free name accepted; the 400 test loops five refusals plus 101 characters, with the 100-character test beside it.
- Boundaries both sides: 100/101 at unit, REST and the SPA (UTF-16 units against code points with GRIN); NFC-after-length case; created-at tie broken by id; newest-first input to `deduplicate`.
- Concurrency in both orders (rename behind a sign-in, sign-in behind a rename) held by an uncommitted transaction; the simultaneous rename asserts exactly `[200, 409]` and one row.
- Migration tests build their own database at 0001 with seeded duplicates (oldest deleted, hidden by NFC and case), assert `version` untouched on clean rows.
- No existing assertion removed or weakened: `git diff` of `test_schema.py` changes only `a_user()`'s name (plan-sanctioned) and adds tests; `App.test.tsx`/`session.test.ts` only add; `test/api.ts` keeps `auth.me(profile)` working.
- BDD: scenario parses, every step binds, the last `Then` is Grace's view after a reload; `data-testid`s used only in the page object.
- No production code, config or docs written.

