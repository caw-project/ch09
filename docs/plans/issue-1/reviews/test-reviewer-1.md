# Test review — issue 1, round 1: changes_requested

38 of the 38 new failing Vitest tests fail as the plan and report say (plus 5 files that fail to load, by
design), and a correct sketch turns every new test green except one pair: `ChannelView.test.tsx`
"captures today's marker only after both refetches" (×2) cannot pass against a correct build, because
the test itself lets the page become visible while #random is open, so a correct build reads #random
and the test then asserts nothing was sent. One critical finding; one minor. The rest of the suite
caught every wrong build I tried.

## Expectations

Written from the issue, the plan, plan-reviewer-1/2 and the current `MessageList`, `ChannelList`,
`ChannelView`, `useChannelSocket`, `useChannels`, before any test file was opened.

**State today:** none of `readState`, `readThrottle`, `readCache`, `useMarkRead`, `usePageAttention`
exist; `MessageList` has no `lastReadId`/`channelFetching` props, no `atBottom`, no divider; the
sidebar has no badge, no poll; `useChannelSocket` has no `read_receipt_updated` handler and no
list refetch on connect; `ChannelView` renders `MessageList` without `key`.

| Behaviour | Fails today with | Vacuous version | Wrong build to catch |
|---|---|---|---|
| Pure rules (`readState`) | `Failed to resolve import` | `findDivider` fixture with a single candidate (first = last); strict vs inclusive `isAtOrPast`; badge cap only on one side | last-unread not first; `>=` vs `>` at 99/100; includes own messages/tombstones |
| Throttle | `Failed to resolve import` | timeline not run as one test; `READ_WINDOW_MS` imported (NaN at red) | trailing-only; leading-only; window counted from request rather than from send; first-wins not latest-wins; one shared window for all channels |
| Cache writes, hold | import failure | hold test whose fetch starts *after* the hold; marker moving backwards one entry only | hold released on first fetch; hold re-applies on manual writes (loop); hold never released after ack |
| Receipts | import failure | only the "at newest" half; refetch half not asserting `invalidate` | always-write; always-refetch; counts `temp:` row as newest; applies other user's receipt |
| `useMarkRead` | import failure | "disconnected sends nothing" with no positive | queues for reconnect; retries on error ack; sends on new socket; flush missing on unmount/channel change; drop-on-workspace-switch passes only because socket closes |
| Read rule (MessageList) | no emit | each input flipped with no positive half; scroll tested at 0-height jsdom (never at bottom or always) | marks read when merely open; reads only visible not focus; `<=` 80; `atBottom` assumed true; marks pending id; sends before capture |
| Divider | separator not found | one candidate; marker moving checked on same fixture where either reading coincides | re-computes divider on each render (follows marker / grows on arrival / jumps on delete); no ceiling; divider for own messages / tombstones |
| Sidebar badge, poll | label not found / `expected 1 to be 2` | poll test passing because TanStack's default focus refetch fires; 30 s with `CHANNEL_POLL_MS` import | refetchInterval in background; two refetches on return; error replaces the list on failed refetch |
| Switch / ChannelView paths | no emit; request count short | cached-switch test where list is not mid-history (coincides with bottom) | assumes bottom after remount; no switch refetch; divider captured before refetch |
| Socket | not invalidated; `lastReadId` unchanged | receipt for another user without positive anchor | no connect refetch (only first); always refetch |
| BDD | parse | step binding / badge selector only | — |

**Clauses to pin in the issue's words:** "at most one emit per channel per second, latest winning";
"the newest *non-pending* message… including own and tombstones"; "at or past" no-op (equal
included); "never moves backwards"; "at or after the newest cached one"; "while the document is
visible, window has focus, **and** within STICK_THRESHOLD"; "until the `mark_read` is
acknowledged… after the ack, fetches as they come"; "dropped on a socket change or a workspace
switch, never sent on the new connection"; "stays above the tombstone"; "no divider when the
boundary is older than the loaded pages".

**Mutations I will sketch** (frontend): correct; trailing-only throttle; `<=` threshold; always-write
receipt; hold that never releases; divider that follows the marker; read on mount without
measuring.

---

## What ran

- `npm --prefix src/frontend test` (whole run): **10 files failed, 17 passed; 38 tests failed, 146 passed**
  — the report's numbers. Failures read: `Failed to resolve import` for `readState`, `readThrottle`,
  `readCache`, `useMarkRead`, `usePageAttention` (5 files); `expected [] to deeply equal [ … ]` (no
  `mark_read`), `Unable to find role="separator"`, `Unable to find a label with the text of …`,
  `expected 1 to be 2`, `expected 2 to be 3`, `expected false to be true`, `lastReadId` unchanged — each as
  the plan's *Expected red*. The one departure (`keeps the list it shows when a refetch fails` fails on the
  link, not the `alert`) is reported and sound: same cause, earlier assertion.
- `npm --prefix src/frontend run typecheck`: only `TS2307` ×5 (missing modules), `TS2322` (the two new
  props) and `readingChannelId` errors — the report's *Types*.
- `uv run pytest tests/bdd --collect-only -q`: 20 collected. `--generate-missing --feature tests/bdd/features`:
  no stubs. Every step binds.
- Sketch (`sketch.sh frontend`, to the plan's interfaces):
  - **Correct build**, pure modules (`readState`, `readThrottle`, `readCache`, `usePageAttention`): 45/45 green.
  - **Correct build**, `useMarkRead`, `ChannelList`, `useChannelSocket`: green.
  - **Correct build**, `MessageList` ×3, `ChannelView`, whole `src/features/channels` + socket: all green
    **except** `ChannelView › captures today's marker only after both refetches` (both orders): got
    `[{"channelId":"channel-random","messageId":"…0c"}]` where `[]` was expected (finding 1). With the
    two `marks(socket)` assertions in my *copy* of the test narrowed to `#general`, 8/8 green.
  - **Wrong builds, each red where it should be:** throttle trailing-only (8/9 fail); throttle with
    first-wins instead of latest (1 fail — "holds reads… latest"); throttle with no reopened window after
    a trailing send (1 fail); `useMarkRead` without the live-workspace check (1 fail — the unmount-drop
    test); divider that follows the marker, unpinned (2 fail: marker moves, tombstone); divider with no
    ceiling (1 fail: arrival during the visit); `<=` instead of `<` at 80px (1 fail); capture that ignores
    `channelFetching` and the history's `isFetching` (4 fail); `MessageList` with no `key` (the
    cached-return pair fail); no `key` plus "assume bottom on channel change" (the mid-history test fails);
    read rule ignoring focus (4 fail).
  - **Wrong build that passes, and was not a finding:** leaving TanStack's `refetchOnWindowFocus` on and
    adding the focus listener with the default `cancelRefetch` — `ChannelList` stays 13/13 green. I counted
    `queryFn` calls in the sketch: 2, same as the correct build, so the tests are not missing an extra
    request; the two refetches collapse inside TanStack. See finding 2.
- Reasoned, not sketched: receipt always-write / always-refetch / counting `temp:` (each has its own
  half in the `readCache` and socket tests, with a positive anchor); hold never released (the release and
  after-ack tests fail it); flush declared after the throttle effect (the unmount test would see nothing
  sent); queue-on-reconnect (positive half in the disconnect test).
- `.claude/delivery/sketch.sh clean` run.

## Coverage

| Plan test / expectation | Test as written | Outcome |
|---|---|---|
| Task 1 pure rules | `readState.test.ts`, `readThrottle.test.ts`; literal 1000; second candidate after the expected one | present |
| Task 2 `readCache` | hold fetches begin before the hold (`fetchQuery` with a held `queryFn`); receipts both sides; other user with positive anchor | present |
| Task 2 `useMarkRead` | disconnect, error ack, lost ack at 4999/5001, flush ×2, socket drop, workspace drop with positive half | present (2 added) |
| Task 2 `usePageAttention` | 4 tests | present |
| Task 3 `MessageList.reading` | 10 tests; "again", "visible again", "scrolled to bottom" merged into the negative tests' positive halves | departed, reasoned, sound |
| Task 3 `MessageList.divider` | 7 | present |
| Task 3 `ChannelView` | 8 (return test in two orders) | present — **one test broken (finding 1)** |
| Task 3 `ChannelList` | poll, pause, focus, failure, error | present |
| Task 3 `useChannelSocket` | 4 | present |
| Task 4 journey, page methods, named wait | `read_state.feature`, steps, `has_unread_badge`, `lacks_unread_badge` | present; binds |
| *Where the rules meet* (six rows) | hold tests; settled and cached-return tests; ceiling; badge-vs-refetch; flush and drop; failed poll | present |
| Real timers in component tests | departure; the 1000/999 and 5000/4999 pairs are fake-time unit tests | accepted |

## Findings

### 1. The cached-return test fails against a correct build — critical
**Where:** `ChannelView.test.tsx`, `ChannelView — returning to a cached channel › captures today's marker only after both refetches` (both rows) · **Checked:** ran it against a correct sketch; got `[{"channelId":"channel-random","messageId":"0199a000-0000-7000-8000-00000000000c"}]` at the `expect(marks(socket)).toEqual([])` after the first gate opens. With both `marks(socket)` assertions narrowed to `#general` in my copy, the file is 8/8 green.

The test sets `setPageAttention({ visible: false, focused: false })` first (line 342), then calls
`act(() => setPageAttention({ visible: true, focused: true }))` at line 357 — **before** it clicks
`#general` (line 359), while `#random` is still the open channel, loaded and (jsdom: all dimensions 0)
at the bottom. By R2 the rule is then true for `#random`, and a correct build sends `mark_read` for its
newest message (`m12`). The assertion that nothing was sent (line 370) and the final
`markIds(socket)` equal to `[idIn(GENERAL, 3)]` (line 380) both fail on a correct build, so the
code-writer could never make this pair green without breaking R2. The report says the page is "kept
hidden until the click"; the code does it the other way round.

The wrong build the test exists for — capturing before both refetches — does fail it (capture-on-success
fails both orders), so the intent is sound. Fix in the test, either:
- count only `#general`'s emits in those two assertions
  (`marks(socket).filter((m) => m.channelId === GENERAL)`), or
- move the `setPageAttention({ visible: true, focused: true })` to after `open(/general/)`, so
  nothing is readable while #random is open.

### 2. "Refetches once on return" doesn't separate a double fire — minor
**Where:** `ChannelList.test.tsx › pauses the poll while hidden…` and `refetches once when the window regains focus…` · **Checked:** a sketch with `refetchOnWindowFocus: true` plus the focus listener (default `cancelRefetch`) stays green, and `queryFn` runs twice, as in the correct build.
Not a hole as measured — TanStack collapses the two — but decision 18's `cancelRefetch: false` reasoning
is not something these tests prove, and the "one refetch, not two" comment promises more than the
assertion shows. Left for the code pair; act only if the real-browser run (Task 9) shows two requests.

## Left for later stages

- Finding 2 (minor).
- Carried from plan-reviewer-2: the journey doesn't wait for the `mark_read` ack before the reload;
  assumed decisions 15, 16, 22, 23, 28 for the human; the Playwright focus fallback in Task 9.
- `ChannelView` tests expect the list refetch at first mount as well as on switches; they take a baseline,
  so the plan's single `useEffect` on `channelId` satisfies them.
- Real-time sleeps (about 1.2 s, twice) in `MessageList.reading` and `ChannelView`: acceptable; the
  unit-level 1000/999 pair pins the boundary if they ever flake.

## Checked and sound

- Red for the right reason: every failure is a missing module, export or prop, or the new behaviour's
  assertion; none is a typo, fixture error or unmatched selector. The one green-by-design test (`shows
  the error when the list never loaded`) is the planned one; no other new test is green.
- No production code, config or docs written: `git status` shows only tests, `test/` helpers, BDD files
  and `docs/plans/issue-1/`.
- Existing tests: `MessageList.test.tsx` 6/6, the 3 existing `ChannelList` and 12 existing
  `useChannelSocket` tests still pass; `giveLayout` moved verbatim, plus `frozen`.
- Report matches the tree: every changed file is in the plan's file map.
- Throttle: *Timing* as one test with literals; trailing-only, first-wins and no-reopen builds fail.
- Cache and sender: hold starts before the fetch it must catch; release, ack, lost ack at 4999/5001,
  socket change and workspace change each have a positive half.
- Read rule: each input flipped alone with a positive half; 79/80 pinned with `frozen`; pending target;
  reconnect sends once.
- Divider: a second candidate after the expected one in every fixture; marker move, tombstone, arrival
  (both halves), settling and the older-page boundary each fail their wrong build.
- BDD: collects and binds; the last `Then` follows a reload; `lacks_unread_badge` anchors on the item.
