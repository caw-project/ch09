# Plan review — gh-3, round 2: approved

All nine round-1 findings are fixed in the plan. Each fix is there and checked against the code or
the installed library, and none of them broke the work beside it. No critical or major finding is
open. Two minor points go to the test pair below.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. `test_schema.a_user` fixed name hides citext | File map row and a Task 5 step: distinct names per user, and the citext test asserts `is_display_name_conflict` is `False`. Both changes are in GREEN | **resolved**. `test_schema.py` has 4 tests, which matches "4 passed". The helper lands in Task 5, the same task as the step |
| 2. Preferences fetch in flight vs optimistic choice | Decision 36: `cancelQueries` in `onMutate`, and the latest mutation's `onSettled` invalidates. The same for `['profile','me']`. Two new hook tests | **resolved**. Checked in the installed `query-core`: `onMutate` is awaited at `mutation.js:102`, before `retryer.start()` at `:115`, and `cancelQueries` defaults to `revert: true` (`queryClient.js:141-142`). The accepted flicker during a pending PATCH is recorded with its reason |
| 3. Merge race not forced | A holds its transaction, B must block (`waiting_on_a_lock`), parametrised with and without a row | **resolved**. A read-modify-write build loses `a` with a row, and gets a PK `IntegrityError` without one. Both are named as the failing builds |
| 4. Module-level import would take down the file | `from auth import preferences` moved inside the merge test's body | **resolved**. The other tests' reds (404, `KeyError: 'detail'`, 401) now run. At red, `user_preferences` doesn't exist, but each test asserts a status before it touches SQL |
| 5. Req 7 "shows the error" and Req 8 "preferences every visit" untested at the page | Two `SettingsPage` tests: a stale `['preferences']` seed against a different server answer, and a 500 that puts `12-hour` back with a `role="alert"` | **resolved**. Both clauses are now pinned as the issue words them |
| 6. Second tab's sidebar settled silently | Decision 37, **assumed**: the sidebar reads the directory entry for `profile.id` and falls back to the session's name. A new `ChatLayout` test | **resolved**. `DirectMessageList.tsx:37` already calls `useWorkspaceMembers` under `ChatLayout` with the same key, so the switcher adds no request and no existing render needs a new stub. `WorkspaceSwitcher` has no test file of its own (grep) |
| 7. Vocabulary ruling 6 | Task 8 amends `:31-32` as well as §1 | resolved |
| 8. `service_database` inside an async test | A sync, function-scoped `at_0001` fixture; the test awaits `upgrade(dsn, "0002")` | resolved. One residual point is under *Left for later stages* |
| 9. `demo_workspace_name=None` | Set in both racing provision tests | resolved |

The sibling-branch check (round 1 *Left for later stages*) is now Task 9's first step.

## Findings

No new findings at critical or major.

## Left for later stages

- **For the test-writer: `a preferences fetch in flight does not undo a choice` needs an active
  observer.** `invalidateQueries` refetches only active queries by default. A later `GET` is
  recorded only if the test renders `usePreferences` beside `useSetClock`, rather than starting the
  held fetch with a bare `queryClient.fetchQuery`. The same applies to the profile test. The GET has
  to go through a recorded `auth.preferences(...)` stub, not the unrecorded default handler.
- **For the test-writer, *unverified*: `asyncio.run` in a function-scoped sync fixture.**
  `service_database` calls `asyncio.run` twice, and `asyncio.run` resets the thread's current event
  loop when it closes. Under `asyncio_mode = "auto"` this has so far run only from session fixtures,
  before any test loop exists. If `at_0001` errors at setup, have the fixture create the database
  through the same `_create`/`upgrade` coroutines inside the async test. That is the second option
  round 1 offered.
- **For `merge`'s builder:** the race test needs `preferences.merge` to leave the commit to its
  caller. The plan implies this ("A commits") but doesn't state it in Task 6. The route commits.
- The plan is 614 lines, a little over the exemplar's 600. Minor.
- Carried from round 1: decision 17 (**assumed**) refuses U+200D ZWJ, so emoji ZWJ sequences are
  refused in names. Decision 14 (**assumed**): `lower()` doesn't fold `ß`/dotless `ı`. Decision 37
  (**assumed**): the sidebar's name comes from the directory. The human should see all three among
  the assumptions.

## Checked and sound

- Base commit: `0ac4c21` is `main` in the primary checkout (`git worktree list`). The branch carries
  only the delivery commits on top of it.
- Decision 36's library claims: `mutation.js:94-128` and `queryClient.js:141-147` in the installed
  `@tanstack/query-core`.
- Decision 37's ripple: the directory query is already mounted by `DirectMessageList` under
  `ChatLayout`, so the switcher adds no request. Its `members` field exists on `Directory`
  (`useWorkspaceMembers.ts:36-40`).
- Integration fixtures named by the new tests exist: `sessions`, `engine`, and `TABLES` in Auth's
  `tests/integration/conftest.py`. `service_database(server, name, upgrade)` matches the
  `partial(upgrade, revision="0001")` call.
- RED still comes before GREEN with the test-reviewer gate. *Found while building* is empty, no task
  commits, and no 🔴 is built on. The Self-review maps every new test to its requirement.
