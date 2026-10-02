# Red tests — issue 1, round 1

BDD outside-in, as the plan recommends: one journey (`read_state.feature`) that collects and binds
but can't run here, and the rules below it in Vitest. **38 Vitest tests fail in files that load, and 5
files (the pure rules, cache, sender, attention) fail to load** — every test in those five needs the
missing module (`readState`, `readThrottle`, `readCache`, `useMarkRead`, `usePageAttention`). Nothing
passes that shouldn't; one test passes by design (below).

## Baseline
Run before any change (`npm --prefix src/frontend ci` first):

| File | Before | After |
|---|---|---|
| `MessageList.test.tsx` | 6 passed | 6 passed (`tsc` red only: the two new required props) |
| `ChannelList.test.tsx` | 3 passed | 3 existing pass; 10 new: 9 fail, 1 green by design |
| `useChannelSocket.test.tsx` | 12 passed | 12 existing pass; 4 new fail |
| `uv run pytest tests/bdd --collect-only -q` | 19 collected | 20 collected |

Whole Vitest run now: 146 passed, 38 failed, 5 files not loading.

## Tests
"Match" is against the plan's expected red. Observed lines are the first line of the failure.

| File · test | Layer | Task | Observed red | Match |
|---|---|---|---|---|
| `readState.test.ts` (18 tests) | Vitest | 1 | `Failed to resolve import "./readState"` | ✔ |
| `readThrottle.test.ts` (9) | Vitest | 1 | `Failed to resolve import "./readThrottle"` | ✔ |
| `readCache.test.ts` (15) | Vitest | 2 | `Failed to resolve import "./readCache"` | ✔ |
| `useMarkRead.test.ts` (12) | Vitest | 2 | `Failed to resolve import "./useMarkRead"` | ✔ |
| `usePageAttention.test.ts` (4) | Vitest | 2 | `Failed to resolve import "./usePageAttention"` | ✔ |
| `MessageList.reading` · 9 of 10 (marks read…, hidden, blurred, scrolled back, 79/80, again on arrival, newest confirmed, settled, reconnect) | Vitest | 3 | `AssertionError: expected [] to deeply equal [ Array(1) ]` (no `mark_read` emitted) | ✔ |
| `MessageList.reading` · reports the channel as being read | Vitest | 3 | `expected undefined to be 'channel-general'` | ✔ |
| `MessageList.divider` · all 7 | Vitest | 3 | `Unable to find role="separator" and name "New messages"` (the null-marker test fails in its second half) | ✔ |
| `ChannelView` · refetches on every switch | Vitest | 3 | `expected 1 to be 2` (list `GET`s) | ✔ |
| `ChannelView` · cached channel read once measured · mid-history not read · held read sent on switch · switch-then-workspace · badge hidden while read | Vitest | 3 | `expected [] to deeply equal [ … ]` at the first `mark_read` wait — the test's positive half | ✔ |
| `ChannelView` · returning to a cached channel (×2 orders) | Vitest | 3 | `Unable to find role="separator"`; its earlier "no divider while held, no `mark_read`" halves pass today | ✔ |
| `ChannelList` · pill and bold name · no pill · 99/99+ · singular · hides the badge being read | Vitest | 3 | `Unable to find a label with the text of: 3 unread messages` (and `99`, `1`, `2` variants) | ✔ |
| `ChannelList` · refetches every 30 s | Vitest | 3 | `expected 1 to be 2` | ✔ |
| `ChannelList` · pauses while hidden … polls again | Vitest | 3 | `expected 2 to be 3` — the first two counts pass today, as the plan says | ✔ |
| `ChannelList` · refetch on focus with the tab visible | Vitest | 3 | `expected 1 to be 2` | ✔ |
| `ChannelList` · keeps the list when a refetch fails | Vitest | 3 | `Unable to find an accessible element with the role "link" and name "general"` — the list is replaced by the error | **differs**: the plan names "`alert` role found"; same cause, an earlier assertion in the same test |
| `ChannelList` · shows the error when the list never loaded | Vitest | 3 | **passes** — *green by design*, as the plan says | ✔ |
| `useChannelSocket` · refetches the list on every connect | Vitest | 3 | `expected false to be true` (`isInvalidated`) | ✔ |
| `useChannelSocket` · applies own receipt · ignores another user's | Vitest | 3 | `expected { id: 'channel-1', … } to match object` (`lastReadId` unchanged) | ✔ |
| `useChannelSocket` · older receipt refetches | Vitest | 3 | `expected false to be true` | ✔ |
| `read_state.feature` | BDD | 4 | cannot run here — see below | — |

Wrong builds the added halves catch (every "to pin" half names one):
- *mid-history not read* — a build that initialises `atBottom` true, or assumes the bottom after a
  remount, emits for #random before the scroll. *79/80* — `≤` instead of `<`.
- *blur/hidden/scrolled-back flips* — a rule that ignores that input emits before the flip.
- *no divider while either is held (both orders)* — capturing on the first render, or after only one
  of the two refetches, puts the divider above the wrong message or none.
- *badge hidden while read, shown on hide* — a build that always shows, or never shows, the count.
- *throttle `flush` then request* — a flush that leaves the window open (or its timer running).
- *held read: positive half before the drop* (`useMarkRead`, `ChannelView`) — a build that only drops
  never sends; a build that only flushes sends after a workspace switch.
- *receipt for another user, then own* — a build that applies every receipt; one that applies none.

## Types
`npm --prefix src/frontend run typecheck` — only expected errors:
- `TS2307` Cannot find module `./readState`, `./readThrottle`, `./readCache`, `./useMarkRead`,
  `./usePageAttention` (5, one per test file).
- `TS2322` the two new required `MessageList` props `lastReadId`, `channelFetching` (in
  `MessageList.test.tsx`, `.reading`, `.divider`).
- `TS2339` / `TS2353` `readingChannelId` not on `ChatState` (`MessageList.reading`, `ChannelList.test`).

## BDD
- `uv run pytest tests/bdd --collect-only -q`: **20 tests collected** (19 + the new scenario).
- `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features`: prints no stubs — every
  step binds (including the moved `Grace is looking at` and the new `Grace reloads CollabHub`).
- Expected red at e2e (Task 9): the scenario runs through `Grace opens the "design" channel` and
  stops at `Then Grace sees 1 unread message in "random"` — `has_unread_badge` fails because the
  sidebar renders no `channel-unread-badge`. `Then Grace sees no unread messages in "random"` would
  pass vacuously on a build with no badge at all, which is why the earlier step must be red first.

## Departures from the plan
- **Real timers in the component tests**, not fake. TanStack's notifications are scheduled with
  `setTimeout(…, 0)`, so a faked `setTimeout` stalls rendering, and `userEvent` waits on timers too
  (clicks are `fireEvent.click`). The 1 s window is crossed by real waiting in two tests
  (`MessageList.reading` "again on arrival", `ChannelView` workspace test, ~1.2 s each); the exact
  1000/999 boundary is proven in `readThrottle.test.ts` and the 5000/4999 in `useMarkRead.test.ts`,
  both fake-timer. The poll tests fake only `setInterval`/`clearInterval`.
- **Merged:** the plan's "marks read when the page becomes visible again" / "when scrolled to the
  bottom" are the positive halves of the hidden / scrolled-back tests, same assertion — not separate.
- **Added:** `useMarkRead` · `follows the socket's disconnect` and `holds the write against an old
  fetch until the ack, and takes fetches as they come after it` (the ack path, which the lost-ack test
  doesn't reach); `readCache` · `leaves absent entries alone` inside the other-channels test;
  `ChannelView` returning-to-cached runs in both orders (detail first, history first).
- `ChannelView` **workspace test** holds the new workspace's detail response with a gate, so
  `ChannelView` is pending and `MessageList` unmounts (plan-review round 2's note).
- `ChannelView` **cached-return test** keeps the page hidden until the click, so no read is possible
  before capture except through the bug; the first `mark_read` is asserted only after both land.
- `readCache` hold tests use `fetchQuery` with a held `queryFn` (started before the hold, answered
  after) rather than MSW, so the fetch's `success` is non-manual exactly as in the app.
- `ChannelView.test.tsx` and `useMarkRead.test.ts` mock `snapshot` as the plan specifies.
- `test/layout.ts`'s `layoutEveryElement` registers its own undo with `onTestFinished`; `test/page.ts`
  tracks the last attention it set so only a changed input fires its event.

## Picked up from earlier reviews
- plan-reviewer-2, *Left for later stages*, for the test-writer: the `ChannelView` workspace-switch
  test stubs the new workspace's requests — it holds the detail with a gate and leaves the view on
  `Loading…`, asserted before waiting out the window. Done.
- The *Playwright focus* and the "ack before reload" notes concern the code stage; nothing to test here.

## For the code-writer
- `MessageList` gets its socket from `useSocket()` (tests provide it through `renderWithProviders({ socket })`);
  its props are only the two new ones. A read goes out as `socket.timeout(…).emit('mark_read', { channelId, messageId }, ack)`.
- Tests read `readingChannelId` from `useChatStore.getState()`, and set it with `useChatStore.setState`.
- `useMarkRead.send` calls `snapshot()` imported from `lib/auth/session` (the tests mock that export).
- The divider's position is tested as "N messages above the separator"; `role="separator"` named
  `New messages` sits between articles in the scroller. A tombstone must still render as an `<article>`.
- `ChannelView` tests assume the remount per channel (`key`), the list refetch on every switch (also at
  first mount — they take a baseline after settling), and the unmount flush ordering the plan gives.
- Components under test make no `data-testid` assumptions; the pill is found by its `aria-label`, the
  bold name by `font-semibold` on the name's `<span>` inside the link.
- `setPageAttention` and `layoutEveryElement` (new, `src/test/`) are the only new shared helpers, plus
  `messageIdAt` in `factories.ts`; `setup.ts` resets the page after each test.
