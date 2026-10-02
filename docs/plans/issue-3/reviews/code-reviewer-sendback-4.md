# Send-back from the code-reviewer — issue 3

To the test-writer. One behaviour that no approved test covers is wrong in the code. This repo
fixes a bug test-first (CLAUDE.md, D32), so the red test comes first, then the code-writer fixes
it. **The plan doesn't have to change.** Task 6 already routes every message and reaction event
through the re-apply rule in `useChannelSocket.ts`. `thread_summary_changed` is the one event
that misses it.

This carries finding 1 of `reviews/code-reviewer-1.md`. The code-writer should read that review
for the other findings (2 and 3 are its own, in the docs and the test report).

## The fault

`src/frontend/src/lib/realtime/useChannelSocket.ts`:

```ts
live.on('thread_summary_changed', (event: ThreadSummaryEvent) =>
  applyThreadSummary(queryClient, workspaceId, event),
)
```

The file's own header gives the rule: *"An event that lands during a history fetch is applied
again when the fetch does."* A fetch that resolves replaces the cached pages with what it read,
and it read the root before the reply committed.

Message events and reaction events are re-applied through `applyAndReapply`. The summary is not.
So a `thread_summary_changed` that arrives while history is refetching is written into the cache
and then overwritten by the stale response. Two common things trigger that refetch: the join-ack
refetch on every channel open, and every reconnect. Grace's root then shows the old count, or no
summary at all, until something refetches again. That breaks R8 ("A root's new `replyCount` and
`lastReplyAt` reach everyone in the channel"). The reply itself survives, because its
`message_received` *is* re-applied, so Grace sees the reply in the thread but no "1 reply" on the
root.

## What ran

A probe in the sketch copy, `src/lib/realtime/probe.summary.test.tsx`, run against the real,
unmutated code:

1. Seed history with the root at `replyCount: 0`.
2. Hold a history fetch, using the same pattern as `holdThreadFetch` in
   `useChannelSocket.threads.test.tsx`, but on `messageKeys.list`.
3. Connect, then emit `thread_summary_changed {replyCount: 1}`. It reads 1.
4. Release the held fetch with the root at `replyCount: 0`, as the server read it before the
   reply.

```
FAIL  probe: summary during a history refetch > a summary arriving mid-refetch survives a response read before the reply
AssertionError: expected +0 to be 1
```

The control in the same file passes: with no fetch in flight, the same event sets 1 and it stays.

## The smallest fix I'd expect

- **Test (test-writer):** add this to `useChannelSocket.threads.test.tsx`: *a summary arriving
  during a history refetch survives it*. Build it the way the probe above does. It should go red
  on today's code with `expected +0 to be 1`.
  - **Optionally**, add the same test on the thread key with the panel's root. The panel shows no
    summary today, so history is the case users see.
  - Its positive half is the existing `thread_summary_changed sets, never adds`.
- **Code (code-writer, afterwards):** run `applyThreadSummary` through `applyAndReapply` over the
  history key and `threadKeys.detail(ws, event.channelId, event.rootId)`, as `onReaction` does for
  a root. Then record it in doc 06 §5.2's routing bullet.
