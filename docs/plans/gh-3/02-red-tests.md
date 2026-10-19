# Red tests — gh-3, round 1

BDD outside-in for the one journey, TDD below it, as the plan recommends. Python: 2 unit files and 4 integration
files created, `test_schema.py` changed. Vitest: 8 files created, 5 existing files changed, `test/api.ts` extended.
BDD: one feature, bound. **54 new tests fail as planned** (24 Vitest, 30 Python) plus 8 whole files that fail to load
because the module they test does not exist (2 unit, 2 integration, 4 Vitest — every test in each needs that module).
9 new tests pass at red, each named below as *green by design*.

## Baseline

| Files changed | Before | After |
|---|---|---|
| Auth unit (`tests/unit`, whole dir) | 59 passed | 59 passed (+ 2 new files, load failures) |
| `test_users.py` + `test_schema.py` | 17 passed | `test_users` unchanged; `test_schema` 5 old pass, 2 new fail |
| Auth whole (unit + integration) after | — | 187 passed, 30 failed, 4 load errors; every failure is a new test |
| Vitest `session` `App` `ChatLayout` `ChatLayout.attachments` `CreateChannelDialog` `MessageItem` | 6 files, 53 passed | every pre-existing test passes |
| Vitest whole | 503 passed (plan baseline) | 507 passed, 24 failed, 4 files not loading; the 4 extra passes are green by design below |

## Tests

Observed red is the first line of the failure. Plan task in brackets. "Match" is yes unless noted.

| File · test | Layer | Proves | Observed red |
|---|---|---|---|
| `test_names.py` (all, ~50 cases) [1] | unit | the rules, key, suffixes, IdP fallback, dedupe | `ModuleNotFoundError: No module named 'auth.names'` — whole file, as planned |
| `test_preferences.py` (unit, 7) [1] | unit | patch validation | `No module named 'auth.preferences'` — whole file |
| `test_preferences_merge.py` (4) [2] | integration | merge, two-tab race both orders, `- text[]` after `\|\|` | `No module named 'auth.preferences'` — whole file |
| `test_migration_0002.py` (8) [2] | integration | 0002 on seeded data | `ImportError: cannot import name 'upgrade_to' from 'auth.migrations'` — whole file |
| `test_display_names` rename stored trimmed/composed | integration | Req 1 | `assert '  José  ' == 'José'` |
| …refused examples ×5 | integration | Req 1 refusals | `assert 200 == 400` (all five, `" "` included) |
| …101 / padded 100 | integration | boundary after trim | `['String should have at most 100 characters'] == ['A display name is at most 100 characters.']` (plan said the padded 100 is the red; the 101 fails first on the message — same cause, `max_length`) |
| …taken name is 409, names nobody | integration | Req 2, D46 | `assert 200 == 409` |
| …collide only once composed | integration | key on NFC | `assert 200 == 409` |
| …saving the name you have writes nothing | integration | Decision 24 | `(1, …) == (0, …)`: version bumped |
| …deleted account's name stays taken | integration | Req 2 | `assert 200 == 409` |
| …rename racing a held rename ×2 | integration | race, both orders | `the request never waited on the held name` |
| …two renames at once | integration | one wins | `[200, 200] == [200, 409]` |
| …first sign-in suffix | integration | Req 3 | `'sam' == 'sam 3'` |
| …first sign-in racing a held rename ×2 | integration | race, both orders | `the request never waited on the held name` |
| …two first sign-ins | integration | `{Sam, Sam 2}` | `{'Sam'} == {'Sam', 'Sam 2'}` |
| …unusable IdP name | integration | Decision 19 | `'​' == 'zed'` |
| `test_preferences.py` (9 fail) | integration | routes | `404 == 200` / `404 == 401` / `KeyError: 'detail'` (deleted account: missing route has no detail), as planned |
| `test_schema.py` unique-including-deleted | integration | partial index would fail it | `DID NOT RAISE IntegrityError` |
| `test_schema.py` key written on insert and rename | integration | validator, Decision 16 | `AttributeError: type object 'User' has no attribute 'display_name_key'` |
| `time.test.ts` (9) [3] | Vitest | clock overrides locale both ways | `Failed to resolve import "./time"` — whole file |
| `MessageItem.clock` / `ThreadSummary` / `SearchResult` — 24h, and cache-write re-render | Vitest | wiring, no refetch | `Unable to find an element with the text: /15:05/` (2 per file) |
| `SettingsPage.test.tsx` (21) | Vitest | page | `Failed to resolve import "./SettingsPage"` — whole file |
| `useProfile.test.ts` (7) | Vitest | rename writes, unmount, in-flight fetch | `Failed to resolve import "./useProfile"` |
| `usePreferences.test.ts` (11) | Vitest | save, revert, ordering, reads in flight | `Failed to resolve import "./usePreferences"` |
| `session.test.ts` — `updateProfile` ×3 | Vitest | setter, guards, switch in flight | `session.updateProfile is not a function` |
| `session.test.ts` — `takeReturnPath` ×6 | Vitest | honoured once; 4 refusals | `session.takeReturnPath is not a function` |
| `session.test.ts` — `signIn` return path | Vitest | stored, and forgotten | `expected null to be '/settings'` |
| `App.test.tsx` direct load, link, callback-return, Back to chat | Vitest | routes | `Unable to find role="heading" and name "Settings"` / `no link "Ada Lovelace"` |
| `App.test.tsx` signed-out `/search?q=zeppelin`; plain sign-in | Vitest | return path remembered, old one forgotten | `expected null to be '/search?q=zeppelin'` / `expected '/settings' to be null` |
| `App.test.tsx` signed-out `/settings` | Vitest | same | `Unable to find role="button" and name "Sign in"` — `/settings` is `No such page.` today, so it never reaches sign-in; the plan said "storage null". Same missing route |
| `ChatLayout.test.tsx` workspace switch forgets last channel | Vitest | Decision 34 | `expected 'c1' to be null` |

**Green by design at red (9 new tests), each with its positive or a reason:**
`test_changing_only_your_own_capitals_is_allowed`, `test_the_same_name_with_a_new_avatar_saves_the_avatar` (guards an
early return that drops the avatar), `test_a_rename_leaves_the_workspace_name`, `test_the_token_keeps_the_old_name_until_renewed`,
`test_a_return_sign_in_keeps_a_renamed_name` (each has the rename's 200 asserted first); `the callback … goes home when none was remembered`; and the three `12h chosen` tests in
`MessageItem.clock` / `ThreadSummary` / `SearchResult`: the jsdom default locale is `en-US`, which is 12-hour already, so
only the 24-hour test of each pair fails at red (in a 24-hour locale the reverse holds). The pair is the guard.

## Types

`npm --prefix src/frontend run typecheck` — every error is a missing module or export:
`Preferences`, `PreferencesPatch` (not in `lib/auth/api`, so `test/api.ts` and two test files); `./SettingsPage`,
`./usePreferences`, `./useProfile`, `./time`; `session.updateProfile`, `session.takeReturnPath`, `signIn`'s second
argument; `lastChannelId` on the chat store (3 sites). One error was mine (`queryClient` twice in a spread) and is fixed.
**Not yet checked:** with `Preferences` missing, `Refusal`/`updatePreferencesBy` and the hook generics resolve to `any`, so
a type error in my use of them shows only when Task 7 lands. The code-writer's `tsc` run may show some; they are the
test-writer's to fix via a send-back.

## BDD

`uv run pytest tests/bdd --collect-only -q` collects `test_settings_steps.py::test_grace_sees_the_name_alan_gives_himself`
(25 tests in all); `--generate-missing --feature tests/bdd/features` prints nothing, so every step binds.
Expected red at the first e2e run, before Task 8: `Alan changes his name to …` → `open_settings()` clicks `current-user`
(a `<p>` today, so nothing happens) and `rename_to` then fails waiting for `settings-page`. If it were a link already, the
next stop is `settings-display-name`. On a kept stack where Alan already has the name, the scenario still needs
`settings-page` and `settings-display-name` to exist, so a missing page cannot pass.

## Departures from the plan

1. **`ChatPage.has_own_name(name)` added beside `own_name()`.** The plan's `own_name()` waits on `current-user`; the house
   rule is a retrying `expect` for a "Then", so `has_own_name` is the retrying one and `own_name()` is a single read for failure messages.
2. **Tests added beyond the plan:** `test_a_patch_that_removes_everything_still_writes_the_row` (Decision 27),
   `test_the_preferences_table_is_created_empty_and_tied_to_users` (the FK, Global constraints), `test_the_key_is_written_with_the_name_on_insert_and_on_rename`
   (Decision 16), `test_dedupe_gives_an_empty_name_the_word_user`, `test_every_bad_key_is_reported_not_only_the_first`,
   the SettingsPage `Preferences`/`Automatic` default checks and a decomposed-form Save case (Decision 36), `useProfile`/`usePreferences`
   tests for `fresh`, no token, and `useClock` reading only, and the round-2 reviewer's test (finding 1): `a reader that rendered on its own leaves the next refetch able to fetch`.
   A signed-out `/search?q=zeppelin` variant and a "plain sign-in forgets the path" test pin Decision 35's *every protected route*.
3. **`test/api.ts` gained `Refusal` and `auth.updatePreferencesBy`** (a PATCH answered per call, a promise holds it, a `Refusal` fails it) — needed
   to fail one clock save and not the next. Not in the plan's list; `updatePreferences` (single reply) is there too, as planned.
4. **Hook tests mount the real hooks**, not just a seeded cache, as round 2 asked: `useWorkspaceMembers` beside `useUpdateDisplayName`; `usePreferences` beside `useUpdateClock`.
5. **BDD:** the harness `ALAN` constant sits in `tests/bdd/conftest.py` (the plan's file list), not a steps module.
6. `Back to chat` in `App.test.tsx` uses real channel stubs because `ChannelView` must load; it asserts only the link's `href`.

## Picked up from earlier reviews

Plan-reviewer-2, *Left for later stages*: **(1)** the `skipToken` observer — test added (departure 2); the code-writer may switch `useClock` to `enabled: false` with the same `queryFn`.
**(2)** mount the directory and preferences hooks, not just seed the cache — done (departure 4); the final GETs those tests count need an active observer.
**(3)** `docker compose up` first run — not a test matter.

## For the code-writer

- **Wrong builds each in-flight test fails.** *Reverts only if nothing newer* fails an unconditional revert (cache would show `{}` after 24h fails). *Reverts to the last saved choice*
  holds the post-failure GET, so a missing revert (leaning on the invalidate) fails. *Two failed choices* fails "revert only" without the final invalidate (ends `24h`).
  *Read in flight* holds the PATCH open while the old GET answers, so a build with `cancelQueries` missing from `onMutate` fails (the later invalidate would hide it otherwise).
  *Read started mid-save* counts a third GET, so a build that writes the PATCH response and never invalidates fails. *Not sent until the first settles* needs the `scope`.
  *Directory in flight* fails write-without-invalidate (call 2 lands the old name) and invalidate-without-write.
- **Preferences call numbering.** In tests with a held read: call 1 is the mount, and *every* settled save that is the last mutation sends one GET (`isMutating === 1`). Do not add a GET elsewhere (focus, mount) in `useClock`/`useUpdateClock`.
- **The page's markup that tests pin by role/label/text:** headings "Settings", "Profile", "Preferences"; textbox "Display name"; button "Save"; `Saved` as visible text (no other text "Saved"); the field error is the only `role="alert"` while no clock error is showing; radiogroup "Clock" with radios "Automatic", "12-hour", "24-hour"; link "Back to chat". The page shows nothing editable until both GETs of this visit answered. A clock failure shows a `role="alert"` with the Problem's `detail`.
- **Save sends what is typed** as `{ displayName }` — the tests use values without outer spaces, so trimming before sending is allowed.
- **Existing-tests ripple is done**: `auth.preferences({})` is in `App.test.tsx` `aReturningUser`, `ChatLayout.test.tsx`, `ChatLayout.attachments.test.tsx` and the shell test in `CreateChannelDialog.test.tsx`; `aReturningUser` also stubs the directory now.
- **Python:** `merge`/`read`/`PreferencesPatch(set, remove)` per the plan; `display_name_key` must exist on `User`; the race tests need a real unique index (a lock wait). `from_idp`, `candidates`, `dedupe` take and return what the plan gives (`dedupe` rows are `(uuid, name)`, result keyed by uuid).
- **Characters in Python tests are `chr()` constants** because the lint hook rewrites `\u` escapes into raw characters — keep that if a test is edited.
- **Time probe** (deleted): in the Vitest runtime `en-US` `h23` → `15:05`, `en-GB` `h12` → `03:05 pm`, `en-GB` default → `15:05`; `dateStyle: 'medium'` with `hourCycle` is honoured.

## Review responses

Round 2, answering `reviews/test-reviewer-1.md`:

1. **Fixed.** `SettingsPage.test.tsx` gains *a saved rename reaches the session and the cached directory, and only the renamer*: a real `session.restore()`, `['workspace-members', ws]` seeded with Ada and Grace, the page saves "Ada L", then `session.snapshot()` profile and Ada's directory row read "Ada L" and Grace's is untouched. It fails a page-local mutation that writes only `['profile','me']`; like the rest of the file it is red by load failure (`Failed to resolve import "./SettingsPage"`) until the page exists. Typecheck adds only the same missing-module errors.
Round 3, answering `reviews/code-writer-sendback-3.md`:

1. **Fixed.** `SettingsPage.test.tsx` `renderWithClock` no longer spreads the patch: `{ ...stored, ...(body.clock ? { clock: body.clock } : {}) }`. Behaviour unchanged (the test only sends `12h`, `24h` or `null`). `npm --prefix src/frontend run typecheck` is clean; the file passes 24/24 against the built page.

Round 2 notes, continued:

2. Minors (left for later stages / done): `ChatLayout.test.tsx` new test now stubs `auth.members([])` — still red on `lastChannelId` (`expected 'c1' to be null` / vitest first failure), stderr clean. Decision 24 decomposed-form no-op, `{"theme": null}` case, and the `skipToken` / Decision 42 conflict (code-writer records the departure; `enabled: false` is not available to `useClock()`, the test stays) — left for a later stage. The `Automatic` test title's stored half is covered by *shows only what this visit fetched*; left.
