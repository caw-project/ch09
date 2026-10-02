# Test review — issue 1, round 3: approved

This round gates the code-reviewer's send-back: an un-acked read must keep its hold when `useMarkRead` unmounts. The test-writer added two tests to `useMarkRead.test.ts`. I read them against the current `useMarkRead.ts`, `readCache.ts` and `FakeSocket`, and both look right. **I could not run anything**: Bash was refused ("don't ask mode"), as in round 2. Every claim below is by reading and is unverified by running.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| Send-back, major: unmount releases every hold, so a switch right after a read lets an old-count fetch bring the badge back | Two tests added to `useMarkRead.test.ts`, each with its positive half. No *Review responses* entry in the red report. | **Resolved by reading, unrun.** See Findings. |
| Send-back: keep "a socket change drops/releases" and don't pin the release through the fake | The socket-change test is unchanged (`drops a read held in its window when the socket changes`). No test claims the release. | Resolved |
| Send-back, optional: `ChannelView` variant | Not added | Let go. The hook-level tests pin the rule, and the code-reviewer marked this optional. |

## What ran
- Nothing. Read: `useMarkRead.test.ts` in full, `useMarkRead.ts:40-97`, `readCache.ts` `holdLocalRead`, `test/socket.ts`, the send-back, and the plan's Task 2 line.
- Round 2's results stand for every file this round did not touch. `git status` shows only `useMarkRead.test.ts` named as changed.

## Findings
### 1. The two new tests were not run — unverified, for the code-writer
**Where:** `useMarkRead.test.ts` · `keeps the hold on an un-acked read when the hook unmounts, until the ack` and `keeps the hold on a read flushed by the unmount, until its ack` · **Checked:** read only.

Walked through the fixture:

- **Red today, for the right reason.** `useMarkRead.ts:85` still releases every hold in the effect cleanup. On unmount the hold is gone, so the old-count `fetchQuery` lands and the cache reads `{ lastReadId: null, unreadCount: 3 }`. The first assertion (`lastReadId: m(2), unreadCount: 0`) fails on the behaviour. This is an assertion failure, not an import or setup error.
- **Setup is sound.** `FakeSocket.send` calls the responder synchronously at emit, so `ack` and `acks[0]` are assigned before the test uses them. The timeout path is not reached: only `setTimeout` is faked and the clock is never advanced, so no 5 s timeout fires in either test.
- **A correct build passes.** With the loop deleted, the `holdLocalRead` subscription stays on the `QueryClient`, and the unmount does not touch the client. The poll is re-written to the held value, and `unreadCount` is 0.
- **Positive half in both.** The test acks, polls again and expects `{ lastReadId: null, unreadCount: 3 }`. A build that leaks the hold, or never releases it, fails there.
- **Order of effects in the second test.** The held `m(3)` is flushed by the unmount: the `[channelId]` cleanup is declared first and runs first, then the throttle's cleanup. It emits a second `mark_read`, is held, and is released only by `acks[1]`. A build that holds only the first read of a channel fails the second test, because the leftover hold for `m(2)` had already been released by `acks[0]`.
- **Wrong builds named.** Release on unmount (today's code) fails both. Release on flush only fails the second. Hold never released fails both positive halves.

Run both before anything else: `npm --prefix src/frontend test -- src/features/channels/useMarkRead.test.ts`. They should be red today and green once the loop is dropped. If either is red on a correct build, check `FakeSocket` microtask timing before suspecting the build.

## Left for later stages
- **The plan's Task 2 line is stale.** `01-implementation-plan.md:283` still says the cleanup "disposes it and releases its holds". The tests now pin the opposite. The code-writer builds to the tests: drop the release loop at `useMarkRead.ts:85` and let each hold be released only by its own ack, error ack or timeout. On a socket change the real `socket.io-client` calls every pending ack with an error (`_clearAcks`), which releases them. `FakeSocket` doesn't emulate that, so no unit test covers it. Correct doc 06 §5.2's *Local write and hold* line if it no longer matches.
- **The red report doesn't record this round.** `02-red-tests.md` has no entry for the two new tests or the optional `ChannelView` variant that was not written, and still carries the round-2 wording noted in test-reviewer-2 finding 1.
- Carried unchanged from rounds 1 and 2: the "once, not twice" focus refetch is not proven; the journey doesn't wait for the `mark_read` ack before the reload; assumed decisions 15, 16, 22, 23 and 28 for the human; the Playwright focus fallback in Task 9; the 1.2 s real-time sleeps in two component tests.

## Checked and sound
- The existing tests in `useMarkRead.test.ts` are unchanged in content, and none is weakened. That includes the 5000/4999 lost-ack pair, the socket-change drop, and the workspace-switch unmount.
- No production code, config or docs were written by the test-writer in this round (`useMarkRead.ts` is the code-writer's file already).
- No sketch was created this round, so there is nothing to clean up.
