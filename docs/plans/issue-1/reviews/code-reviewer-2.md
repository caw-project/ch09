# Code review — issue 1, round 2: approved

Finding 1 from round 1 is fixed. `useMarkRead`'s cleanup no longer releases holds, so a channel switch
keeps an un-acked read's hold until its ack, error ack or timeout. Doc 06 §5.2 and the plan's Task 2 now
say the same, and the test pair's two new tests catch the old code. Everything the plan names is green,
and no finding is open.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 (major): the throttle cleanup releases every hold on unmount, so the switch refetch can bring the badge back | Release loop removed from the cleanup (`useMarkRead.ts:83-92`), with a comment saying why; `holds.clear()` kept. Doc 06 §5.2 *Local write and hold* and plan Task 2 (line 283) corrected. The round is recorded in *Found while building* (line 572). | **Resolved.** The new tests pass on the real code and fail on the old one (mutant below). |

The send-back's other points:
- The plan line was rewritten in the words the send-back proposed.
- Doc 06 line 181–182 says "Leaving a channel does not release it; a socket change does, because the
  socket library answers each pending ack with an error". That matches the code, and it matches
  socket.io-client's `_clearAcks` on close (checked in round 1).

## What ran
- `npm --prefix src/frontend test`: 27 files, **243 passed**. `run typecheck`: clean. `run lint`: clean.
  `run build`: built (367.92 kB JS).
- `python3 .claude/hooks/checks/conventions.py` over `useMarkRead.ts` and `useMarkRead.test.ts`: no findings.
- Evidence for `scripts/test.sh`:
  - `docs/test-report.md` is at `14d0a0486d40-dirty`, which is HEAD. Lint ✅. Unit ✅ 565 (frontend 243).
    End-to-end ✅ 20. Integration ⚪ not run: the plan's verification doesn't name it.
  - `build/test-results/e2e.xml`: `tests="20" failures="0" errors="0"`. Its timestamp is 14:45:36, after
    the `useMarkRead.ts` edit (14:44:23). `test_graces_unread_count_clears_once_she_has_read_the_channel`
    is present and has no failure.
- The test file's mtime is 14:42:58. That is before test-reviewer-3's approval (14:44:01), so the
  code-writer didn't touch it.
- **Mutant** in `useMarkRead.ts`: put back `for (const release of holds.values()) release()` in the
  throttle cleanup. Ran `useMarkRead.test.ts`: **caught**, 2 failed of 14. The failures were `keeps the
  hold on an un-acked read when the hook unmounts, until the ack` and `keeps the hold on a read flushed by
  the unmount, until its ack`.
- No other mutants: nothing else changed in the code.
- Ran `sketch.sh clean`.

## Findings
None.

## Unpinned
- **A socket change releasing holds** now depends only on socket.io-client calling each pending
  `timeout()` ack with an error when the socket closes. `FakeSocket` doesn't emulate that, so no unit test
  holds it. The 5 s timeout is pinned (the 4999/5000 pair), and it bounds the case where it fails. One
  case gets only the timeout: a workspace change that keeps the same socket object. Its hold stays up to
  5 s, but it covers only the old workspace's cache keys, so nothing the user now sees is affected.
- **A→B→A within one ack.** The old mount's hold on A and the new mount's hold can both be live. Each
  re-applies a forward-only write, so the newer marker wins, and each ends with its own ack. By reading
  only.
- Carried from round 1: `refetchOnWindowFocus: false` with `cancelRefetch: false` (that mutant
  survived), the bold-name half of the shared `unread` condition, and StrictMode.

## Left for the human
- The plan's **first real run** by hand (two browsers): walk the issue's *Acceptance* list. Check that
  a tab return makes one list request, and that switching away right after reading a channel leaves no
  badge on it. That second check is the path this round fixed.
- Assumed decisions to read: 15, 16, 22, 23, 28.
- The journey doesn't wait for the `mark_read` ack before it reloads (plan, *What no test covers* (c)).
- `02-red-tests.md` doesn't record the test-writer's round 3 (test-reviewer-3, *Left for later
  stages*). It is the test pair's report, so nothing for the code pair to do.
- The semgrep finding in `testkit/report.py:96` was there before this branch, which doesn't touch it.

## Checked and sound
- `useMarkRead.ts` cleanup: dispose, then `holds.clear()` (the map dies with the effect; the
  subscriptions stay until each `release`), then the `throttle.current === live` guard. Unchanged otherwise.
- Holds are not leaked forever: each `emit` is under `socket.timeout(5000)`, so every hold ends.
- Doc 06 §5.2, plan Task 2 and *Found while building* agree with the code.
- The green report's round-2 *What ran* (243 Vitest, lint, unit, e2e) matches what I ran and the
  evidence.
