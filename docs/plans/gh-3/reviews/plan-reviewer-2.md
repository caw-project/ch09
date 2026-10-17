# Plan review — gh-3, round 2: approved

All nine round-1 findings are fixed in the plan, and I checked each fix against the installed
source or the repo. No critical or major finding is open. Two minor points about the new tests
go to the test pair under *Left for later stages*.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Race tests' stated red | `test_a_rename_racing_a_first_sign_in` → `AttributeError` on `rename_user`. `wait_until_blocked` is bounded at 5 s with `pytest.fail("B never blocked on the name index")`, and that is the stated red of `test_two_first_sign_ins_with_one_name` (Task 2, lines 277-287) | **resolved.** At red there is no index, and the two provisions use distinct emails, so nothing makes B wait: the poll is the first thing to fail. At green, B's insert waits on A's uncommitted key (`wait_event_type = 'Lock'`), so the helper sees it |
| 2. Cache-write tests can't tell the write from the refetch | *Holding the directory* note. Every call's answer is stated, and the write is asserted while the post-save refetch is held | **resolved.** `scriptDirectory().hold/answer` and `settleDirectory` exist (`test/directory.ts:24,40`), and `renderWithProviders` returns `queryClient` (`test/render.tsx:83`), so the tests can do what they describe. An invalidate-only build shows the old name during the hold and fails |
| 3a. `adopt()` racing a rename | Decision 37 (`profileEdits` read before the fetch), plus two `session.test.ts` tests: the race, through a renewal and through `changeWorkspace`, and the guard's positive | **resolved.** `session.ts:76-94,199-212` match the plan's account. The positive test (an edit made *before* the renewal starts adopts `Ada M`) rules out a frozen profile |
| 3b. Directory not cached yet | `await cancelQueries` before `setQueriesData` (decision 31) | **resolved.** Checked `query.ts:411-418`: the fetch joins when there is no data. Checked `queryClient.ts:276-289`: the default is `revert: true`. With no data, the uncached test fails both a set-then-invalidate build and an invalidate-only build |
| 3c. Two clock saves out of order | `scope: { id: 'user-preferences' }` (decision 34), with a test | **resolved.** Checked `mutation.ts:202-235`: `onMutate` runs before `#retryer.start()`. Checked `mutationCache.ts:160-188`: `canRun` waits for the first pending mutation in the scope, and `runNext` continues the paused one |
| 4. Conventions §3 third exception | Task 11 and decision 36 add it, D46 names it, and the CH009 waiver cites both | **resolved** |
| 5. Return path outlives a failed sign-in | Every `signIn` overwrites or clears it, and every `return false` clears it. Tested, with the positive case | **resolved.** All three `return false` paths in `completeSignIn` (`session.ts:171-197`) are covered by "every `return false`" |
| 6. After 10 lost retries | Re-raise, marked **assumed**, with the reason it can't happen in practice | **resolved** (recorded and defensible) |
| 7. Own-capitals guard has no positive half | Grace's `"ada"` → 409 after Ada becomes `"ADA"` | **resolved.** Grace's `"ada"` gets 200 today, so the test fails at red |
| 8. Legacy names can't be saved unchanged | Decision 15 (**assumed**): the no-op check on `stored_form` runs before validation. New unit and integration tests | **resolved** |
| 9. Small inaccuracies | Distinct names in the email test. README in Task 10. Citations re-checked | **resolved.** `asyncpg.py:791-797` = `raise translated_error from error` (worktree `.venv`). `src/frontend/README.md:61-62` has the "D28 🔴" lines (the plan says 60-62, close enough) |

## Findings

None at critical or major.

## Left for later stages

- **For the test-writer: `a second clock choice waits for the first to reach the server`.**
  "`requests()` holds one preferences PATCH" is a negative assertion. Its anchor, "`12-hour` is
  checked", appears after `onMutate`. In an unscoped build, the second `mutationFn` starts right
  after that, but MSW may not have recorded the request yet. The check therefore has to come
  after the moment the second request could have been recorded, for example after awaiting a
  macrotask inside `act`. Otherwise an unscoped build passes that half. The later ordering
  assertion (the `12h` PATCH is sent only after the release) still catches the same build, so
  this is minor.
- **For the code pair: decision 34 when both clock saves fail.** The second mutation's
  `onMutate` snapshot is the first mutation's optimistic value. If the first fails and then the
  second fails, the second's `onError` puts back a value the server never stored. This is
  visible only after two failures in a row, and the next visit reads from the server anyway.
  Fixing it is optional: snapshot the last *confirmed* value instead.
- Still standing from round 1: these assumed decisions need a human to see them at the end:
  12 (casefold, `ß` = `ss`), 13 (code points), 15 (legacy no-op before validation),
  17/22 (dropping refused characters from IdP names, keeping them in legacy names),
  19 (re-raise after 10), 25, 28 (return path in `sessionStorage`), 29, 30, 34, 37.

## Checked and sound

- Base commit `41bcc04` is still `main` (`git worktree list`). The plan is 571 lines, about 558
  without *Review responses*.
- Every TanStack citation, read in the primary checkout's `node_modules/@tanstack/query-core/src/`:
  `mutation.ts:246` (hook-level `onSuccess`), `query.ts:411-418`, `queryClient.ts:276-289`,
  `mutation.ts:205-235`, `mutationCache.ts:161-176`.
- Decision 37's sketch (Task 9) reads the count before `Promise.all`, as its tests need. It
  changes neither the failure paths of `renew`/`changeWorkspace` nor the 401 path: D37/D38 are
  untouched.
- The new tests keep RED before GREEN. Every new test helper (`auth.meBy`, the `a_user` name
  parameter) is in a RED task.
- Nothing new is built on a 🔴. The record (Task 11) now covers Conventions §3 and §5.4,
  D28, D46, two ADRs, and doc 01 and doc 06 §3/§4/§5.2/§9.
