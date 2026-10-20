# Plan review — gh-3, round 2: approved

All four round-1 findings are fixed. I checked each fix against the installed library source and
`session.ts`. The two major ones now hold in every ordering I traced: decision 17's serial scope,
and decision 35's profile epoch. Each has tests that a wrong build would fail. Nothing new rose to
major. Two small notes are left for the test and code pair.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The clock's settle rule ends on the older choice when answers arrive in reverse (major) | Decision 17 rewritten: `scope: { id: 'preferences' }` sends the PATCHes one at a time in click order, with `inFlight`/`latest`/`confirmed` bookkeeping per `QueryClient`. Only the latest choice's response writes, and the latest choice's failure restores `confirmed`. Four Task 3 tests, one per outcome pair | **resolved** — see below |
| 2. A renewal can put the old name back in the sidebar (major) | Decision 35 rewritten: `profileEpoch` is bumped by `updateProfile`. `adopt()` captures it before `me()` and keeps the current profile if it has changed. Three `session.test.ts` cases | **resolved** — see below |
| 3. Profile prefill on a revisit can come from the cache (minor) | Decision 36, **assumed**: the field waits for this visit's fetch (`isFetchedAfterMount`), with a new test | resolved |
| 4. Rolling-deploy window (minor) | Migration docstring (Task 6) and *What no test covers* | resolved |
| Left-for-later notes (`\u` escapes, deleted rows in doc 01 §4) | Task 1, Task 9 | taken up |

**Finding 1, how I checked it.** I read `@tanstack/query-core` 5.101.4 in the primary checkout.
- `mutation.js:89-115`: `isPaused` is computed from `retryer.canStart()`, then `pending` is
  dispatched and `options.onMutate` awaited, all before `retryer.start()`. So the second click's
  optimistic write happens at the click, even while that mutation is paused.
- `mutationCache.js:60-71`: `canRun` lets only the first pending mutation in a scope run.
- `retryer.js:43,119`: `start` waits when `canStart` is false.
- `mutation.js:194`: `runNext` runs in `finally`, so it runs after an error too, and continues
  the next paused mutation in the scope (`mutationCache.js:72-76`).

I then traced A = 12h, B = 24h, starting from Automatic. The four outcomes come out as the
decision row says:

| A | B | Ends on |
|---|---|---|
| ok | ok | 24h |
| ok | fails | 12h, with the error |
| fails | ok | 24h, no error |
| fails | fails | Automatic, with the error |

The non-latest write is suppressed by `seq !== latest`. `confirmed` is snapshotted only when
`inFlight === 0`. The test "a second choice waits…" fails both a parallel build and one where a
non-latest response writes. "two failed saves" fails a build that restores the per-mutation
snapshot.

**Finding 2, how I checked it.** I read `session.ts:76-94`, `:122-138` and `:199-212`. `renew` and
`changeWorkspace` both go through `adopt`, so one epoch check covers both paths. The epoch is
captured before `me()` is sent:
- If the rename landed after the capture, the current (newer) profile is kept.
- If it landed before, `me()` was sent after the commit and already carries the new name.

Order 2's test fails a sticky "renamed locally" flag. Order 1's test asserts the `renewed` token,
so it proves the renewal still adopted (the guard's positive half). The harness it leans on also
holds:
- `answerSlowly` (`session.test.ts:270-285`) exists.
- A second `restore()` after `beforeEach` acts as a renewal (`renew` with no `spending`).
- That describe block uses no fake timers, so `vi.waitFor` is safe there.

## Findings

None open.

## Left for later stages

- **Decision 36 and a failed profile fetch.** `isFetchedAfterMount` (`queryObserver.js:328`) is
  also true after an **error**. If this visit's GET fails, the build must not seed the field from
  a stale cached name or an `undefined` one. The code-writer should show the error state instead.
  This edge isn't tested; worth a line in *Found while building* if it comes up.
- **Decision 17's "focus refetch mid-save shows the old value for a moment".** This is recorded
  and accepted. The test-writer should not pin the radio's value during that moment.
- Round 1's still-relevant notes stand: `directoryRefresh.ts`'s `load` ignores the abort signal
  (code-reviewer, against decision 16).

## Checked and sound

- The diff since round 1 (`git diff 8caa350 e2f034e`) touches only the plan, plus the runner's
  `run/`. Nothing else in the plan changed beyond the responses.
- Base `2f1cc69` is still `main` in the primary checkout.
- The plan is 600 lines with *Review responses*, about 588 without, so within 250–600.
- The new tests are all RED in Task 3. Their stated reds hold:
  - `module not found` for the new section files;
  - `session.updateProfile is not a function` for the epoch cases, which call it.
- Every round-1 *Checked and sound* item still stands. The changed rows don't touch them.
