# Send-back from code-reviewer, round 1 — to the test-writer

**Carries:** finding 1 of `docs/plans/issue-1/reviews/code-reviewer-1.md` (major). No approved test covers
this behaviour, so it comes to the test pair first, as the repo fixes bugs test-first (CLAUDE.md, D32).
The plan's Task 2 has one line to change as well (below). Pass that to the plan-writer if your
reviewer wants it there first; the fix needs no new decision.

## What is wrong

Issue, *Where the rules meet*: "Until the `mark_read` is acknowledged, such a fetch must not bring the
badge back: the local read is re-applied to it." The plan carries this as decision 12 and the hold.

`useMarkRead.ts:83-88`: the throttle effect's cleanup does `for (const release of holds.values())
release()`. That cleanup runs on a socket change, and also **on every unmount**, and `MessageList` now
unmounts on every channel switch (`key={channel.id}`). So:

- Grace reads #random (leading-edge `mark_read`, hold on) and clicks #general before the ack arrives.
  Or a read is held in its window and flushed as the list unmounts. Either way the hold is released in
  the same commit.
- `ChannelView`'s switch effect (`ChannelView.tsx:41-43`) then invalidates the channel list. That `GET`
  races the `mark_read` on the server. If it is read before the marker commits, #random's badge comes
  back, and it stays until the next refetch: a poll (up to 30 s), a focus return or another switch.
  This is the issue's *Paths* row "Switch while a read waits in its window", and the most common way
  anyone leaves a channel they have just read.

The plan wrote it this way: Task 2 says "the effect's cleanup disposes it and **releases its holds**".
It assumed that cleanup meant a socket change. Decision 12 only requires that "a socket change
releases every hold", and that happens without the explicit release. Installed
`socket.io-client/build/esm/socket.js:447-471`: `onclose` → `_clearAcks()` calls every `withError` ack
(which is what `socket.timeout(…).emit` registers, `:301`) with `Error("socket has been
disconnected")`. So closing the old socket already fires each hold's `release`.

## What I ran

A probe in the sketch (`src/features/channels/probe.hold.test.ts`), driving the real `useMarkRead` with
the helpers `useMarkRead.test.ts` uses. It used a `FakeSocket` whose `mark_read` responder returns a
deferred promise, the list and detail seeded with `unreadCount: 3`, and `pollLandsWithOldCount` as
defined in `useMarkRead.test.ts:67-78`.

1. `request(m(2))` (sent, not acked), `unmount()`, then an old-count list fetch lands. The test expects
   `{ lastReadId: m(2), unreadCount: 0 }`. It **fails**: received `{ lastReadId: null, unreadCount: 3 }`.
   Its second half acks and then fetches again, expecting 3 (fetches taken as they come after the ack).
2. `request(m(2))`, ack, `request(m(3))` (held), `unmount()` (the flush sends m3), then an old-count fetch.
   The test expects `{ lastReadId: m(3), unreadCount: 0 }`. It **fails** the same way.

With the release loop deleted from the cleanup (`holds.clear()` kept), both probes pass, and so do
`useMarkRead.test.ts`, `ChannelView.test.tsx` and `readCache.test.ts`: 36/36.

## Why my stage can't fix it

I don't edit code. The code-writer may not write the test. The approved suite holds no test for
"unmount with an un-acked read, then an old fetch", so a code fix now would leave the rule unpinned.

## The smallest fix I'd expect

- **Test (test-writer):** in `useMarkRead.test.ts`, the two probes above as one or two tests. Each needs
  its positive half: after the ack (or 5 s with no responder), the old-count fetch is taken. Optionally
  add a `ChannelView.test.tsx` variant: read #random with a held ack, click #general, answer the switch's
  list `GET` with the old count, and assert #random's badge stays absent until the ack. **Keep "a socket
  change releases holds"**, but note that `FakeSocket` may not emulate `_clearAcks`. If it doesn't,
  don't pin that release through the fake, because the real library does it.
- **Plan (Task 2, first bullet):** "the effect's cleanup disposes it and releases its holds" becomes
  "the effect's cleanup disposes the throttle; each hold is released only by its own ack, error ack or
  timeout — on a socket change the library calls every pending ack with an error, which releases them".
- **Code (code-writer, after the red is approved):** drop the release loop in `useMarkRead.ts`'s cleanup.
  Correct doc 06 §5.2's *Local write and hold* line if it no longer matches.
