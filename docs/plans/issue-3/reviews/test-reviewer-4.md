# Test review — issue 3, round 4: approved

Rework pass over the code-reviewer's send-back. `useChannelSocket.threads.test.tsx` now has the two red tests the send-back asked for, one on history and one on the panel's root. Both fail today for the reason the send-back gives, and the other 11 tests in the file still pass.

## Responses checked
| Send-back item | Test as written | Outcome |
|---|---|---|
| History: a summary arriving mid-refetch survives a stale response | `a summary arriving during a history refetch survives it` (lines 271–308). The fetch is held on `historyKey` with a deferred `MessagePage`. The test emits `thread_summary_changed {replyCount: 1}` and asserts it reads 1 at once (precondition), then releases a page with the root at `replyCount: 0`, and asserts 1 and `lastReplyAt` survive. | resolved |
| Optional: same on the thread key | `a summary arriving during a thread refetch survives it on the panel's root` (lines 310–332), using `holdThreadFetch`. Same shape with `replyCount: 3`. | resolved |
| Positive half | The existing `thread_summary_changed sets, never adds` is untouched. | resolved |

## What ran
- `npm --prefix src/frontend test -- src/lib/realtime/useChannelSocket.threads.test.tsx`: 2 failed, 11 passed.
  - History test: `expected replyCount 1, received 0` and `lastReplyAt null`.
  - Panel-root test: `expected replyCount 3, received 0` and `lastReplyAt null`.
  - Both fail at the final assertion, after the precondition passed. The test body ran, so the cause is the stale response overwriting the event.
- No sketch run. The re-apply mechanism is already proven by the sibling `a reply arriving during a thread refetch survives it`. The change adds only an event routed through that same path, so a sketch can't tell me more than reading does.

## Findings
None.

## Left for later stages
- Code-writer: route `applyThreadSummary` through `applyAndReapply` over both the history key and `threadKeys.detail(ws, event.channelId, event.rootId)`, as the send-back says. Each test needs its own key re-applied. A build that re-applies only history fails the panel-root test, and one that re-applies only the thread key fails the history test. Then record it in doc 06 §5.2.

## Checked and sound
- Red for the right reason: the precondition (the event applied at once) passes, and only the post-fetch assertion fails.
- Wrong builds: the unchanged code (no re-apply) is red on both. Each key-only re-apply is caught by exactly one test.
- Clause "sets, never adds": the event carries an absolute count, and the stale page has a different count (0), so the old and new readings don't coincide.
- The fetch is held with a deferred response and released after the event, so the race runs in the order that matters.
- Existing tests: the other 11 in the file pass, and no assertion was changed.
