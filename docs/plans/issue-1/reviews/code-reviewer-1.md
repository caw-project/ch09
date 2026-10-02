# Code review — issue 1, round 1: send_back

The build matches the plan closely, and everything the plan names is green: Vitest 241/241,
typecheck, lint, build, and the journey in `e2e.xml`. One major finding stands. A read that hasn't
been acked yet loses its hold when `MessageList` unmounts, so the list refetch that every channel
switch starts can bring the badge back for the channel just read. A probe fails on the real code, and
no approved test covers this path. So it goes to the test pair first
(`code-reviewer-sendback-3.md`), and the plan's Task 2 has one line to change.

## Expectations

Written from the issue, the plan, the red report, plan-reviewer-1/2 and test-reviewer-1/2, and from the
pre-change `MessageList`, `ChannelView`, `ChannelList`, `useChannels`, `useChannelSocket` and
`stores/chat.ts` (`git show HEAD:`). None of the production files the writer touched was open.

**Task 5 — `readState.ts`, `readThrottle.ts`.**
- What no test pins: after a *trailing* send, the timer reopens only when `send` returned true.
  `dispose` makes later `request` and `flush` calls do nothing. `flush` clears the timer as well as
  sending.
- What it takes for granted: nothing outside itself.
- Plausible wrong builds: a window counted from the request rather than the send; first-wins. Both are
  pinned (test-reviewer-1 sketched them).

**Task 6 — `readCache.ts`, `useMarkRead.ts`, `usePageAttention.ts`, the store.**
- What no test pins:
  - `writeLocalRead` maps the list's *page* shape (`{items, nextCursor}`, which `select` unwraps)
    without dropping `nextCursor`.
  - The hold unsubscribes on release, and release is idempotent.
  - `applyReadReceipt` finds the newest cached message by its position in `pages[0].items`
    (newest-first) or by a max over ids.
- What it takes for granted:
  - (a) That **the effect cleanup that disposes the throttle runs only on a socket change**. It also
    runs on **unmount**, and the plan says that cleanup "releases its holds". On a channel switch the
    unmount flush emits `mark_read` and creates a hold, and the dispose releases it in the same commit.
    `ChannelView`'s switch effect then starts a list `GET`, which the server can answer before it
    commits the marker. That brings A's badge back until the next refetch, against *Where the rules
    meet*: "until the `mark_read` is acknowledged, such a fetch must not bring the badge back". The
    same happens to a leading-edge read sent just before a switch, whose ack hasn't come yet.
    **Must probe.**
  - (b) That a throttle created in render (`useMemo`/`useState`) and disposed in cleanup survives
    StrictMode (`main.tsx` wraps the app in `<StrictMode>`). If it doesn't, the effect's second setup
    reuses a disposed throttle and nothing is ever sent in dev. **Probe under StrictMode.**
  - (c) That cleanups run in declaration order on unmount (React does), so the flush comes before the
    dispose.
- Where it could go wrong:
  - the flush cleanup capturing a stale throttle, disposed after a socket change;
  - `connected` missing its listener cleanup;
  - `send` reading `workspaceId` from a ref rather than from `snapshot()`;
  - `socket.timeout(...)` not used, so a lost ack never releases the hold.
- Plausible wrong builds: the hold released at unmount (see (a)); no approved test unmounts with an
  un-acked hold and then fetches. A throttle in `useMemo`; no approved test runs StrictMode.

**Task 7 — the components.**
- What no test pins:
  - `refetchOnWindowFocus: false` (test-reviewer-1 finding 2: a build that leaves it on stays green);
  - the focus and visibility listeners removed on unmount and on a workspace change;
  - `visibilitychange` acting only when the tab is visible;
  - `cancelRefetch: false`;
  - `readingChannelId` cleared on unmount, and only its own value;
  - the `[channelId]` reset effect removed;
  - the header comment in `useChannelSocket`;
  - the bold name.
- What it takes for granted:
  - That `isFetching` is already true on the first render of a cached return (the issue's *assumes*;
    TanStack's optimistic result).
  - That `atBottom` is measured on every path that moves the list: a mount with cached data, the first
    load, growth, a prepend and a user scroll. A refetch that leaves the data the same length doesn't
    re-run a `[messages.length]` layout effect, and an empty channel needs a measure when its scroller
    appears.
  - That the capture effect reads the detail's `lastReadId` prop, not `cachedLastReadId`.
- Where it could go wrong:
  - the divider recomputed every render rather than pinned;
  - the pin also pinning a `null` before the boundary loads;
  - capture before the join-ack refetch, which is accepted;
  - `readingChannelId` set by the old list's cleanup after the new list's setup;
  - the receipt handler's closure over `userId` (it is in the effect's deps today).
- Plausible wrong builds:
  - `refetchOnWindowFocus` left on: survives, already known.
  - `channels === undefined` versus `!channels`: equivalent.
  - The badge condition reading `activeChannelId` instead of `readingChannelId`: pinned by the "hiding
    the tab shows it" half.

**Task 8 — the record.** Doc 06 §5.2 loses "throttle `mark_read`" and gains a *Read state* block: the
rule, the target, the throttle and *Timing*, no queue or retry, the local write and hold, polling,
receipts, the divider, and the remount per channel. Each must match the code. The *What exists already*
line about `MessageList` staying mounted is corrected. A new ADR,
`261002-unread-state-polls-rather-than-pushes.md`, carries the three alternatives and the revisit
condition. ADR 260915 lines 96–99 now cite `test_read_state.py`. The sweep leaves nothing stale.

**Task 9 — verification.** `docs/test-report.md` at this revision with `-dirty` shows lint, unit and
e2e passing, and `build/test-results/e2e.xml` lists the journey *Grace's unread count clears once she
has read the channel* among the passed.

## What ran

- `npm --prefix src/frontend test`: 27 files, **241 passed**. `run typecheck`: clean. `run lint`: clean.
  `run build`: built (368 kB JS).
- `python3 .claude/hooks/checks/conventions.py` over the 7 changed TS files and 4 BDD Python files:
  no output, so no findings.
- Evidence for `scripts/test.sh`:
  - `docs/test-report.md`: Lint ✅, Unit ✅ 563 (pytest 322 + Vitest 241), End-to-end ✅ 20, all at
    `14d0a0486d40-dirty`, which is HEAD `14d0a04`. Integration ⚪ not run: the plan's verification
    doesn't name it.
  - `build/test-results/e2e.xml`: `tests="20" failures="0"`, and
    `test_graces_unread_count_clears_once_she_has_read_the_channel` is present and passed.
- **Probe** `probe.hold.test.ts` (sketch, real `useMarkRead`, deferred `mark_read` ack):
  - Leading read not acked → `unmount()` → old-count list fetch: **failed**. Expected
    `{lastReadId: m2, unreadCount: 0}`, received `{lastReadId: null, unreadCount: 3}`.
  - Held read flushed on unmount → old-count fetch: **failed** the same way.
- **Fix check:** the cleanup's release loop removed. Both probes pass, and `useMarkRead`, `ChannelView`
  and `readCache` are 36/36.
- **Mutants:**

  | File | Change | Tests run | Result |
  |---|---|---|---|
  | `MessageList.tsx` | `readingChannelId` not cleared on unmount | `ChannelView`, `.reading` | caught (1) |
  | `useChannels.ts` | `visibilitychange` refetches when hidden | `ChannelList` | caught (1) |
  | `useChannels.ts` | focus and visibility listeners never removed | `ChannelList`, `ChannelView` | caught (2) |
  | `MessageList.tsx` | no measure in the layout effect | `ChannelView`, `.reading` | caught (14) |
  | `useMarkRead.ts` | flush in the throttle cleanup (send on a socket change) | `useMarkRead`, `ChannelView` | caught (1) |
  | `useChannels.ts` | `refetchOnWindowFocus: true` with the default `cancelRefetch` | `ChannelList` | **survived** 13/13 |

- `sketch.sh clean` run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T5 `readState` interfaces, `findDivider` rule, `isLiveWorkspace` | `readState.ts` | as planned |
| T5 throttle: `Map`, leading and trailing, reopens only on a true send, flush, dispose | `readThrottle.ts` | as planned |
| T6 `writeLocalRead` (forward-only, list page and detail), `cachedLastReadId` | `readCache.ts:20-62` | as planned |
| T6 / D12 hold on non-manual `success`, release | `readCache.ts:72-90` | as planned |
| T6 `applyReadReceipt` (other user ignored, newest non-pending, else invalidate) / D23, D29 | `readCache.ts:106-126` | as planned |
| T6 `useMarkRead`: per `[socket, workspaceId]`, live `snapshot()` (D30), no-op, `timeout(5000)`, flush declared first | `useMarkRead.ts` | as planned. **The plan's "cleanup … releases its holds" is the fault; finding 1** |
| T6 `usePageAttention`, store `readingChannelId` | as specified | as planned |
| T7 / D18–19 poll 30 s, `refetchOnWindowFocus: false`, `useChannelListRefresh` with `cancelRefetch: false` | `useChannels.ts` | as planned |
| T7 / D21 error only without data; badge and bold markup, `data-count`, `aria-label` / D24 | `ChannelList.tsx` | as planned (bold hidden while being read, recorded) |
| T7 / D13 capture after both settle; D14 `key`, measured `atBottom`, reset effect gone; pin | `MessageList.tsx`, `ChannelView.tsx` | as planned |
| T7 / D17 `readingChannelId` kept in step, cleared on unmount | `MessageList.tsx:124-128` | as planned |
| T7 / D20 switch refetch, connect refetch, receipt handler, header comment | `ChannelView.tsx:41-43`, `useChannelSocket.ts` | as planned |
| T8 doc 06 §5.2, the new ADR, the ADR 260915 correction, the sweep | docs | as planned; one line wrong (finding 1) |
| T9 lint, unit, e2e; conventions; first real run | report and evidence | done, except the hand-run, which is left to the human |

## Findings

### 1. A channel switch releases an un-acked read's hold, so the switch refetch can bring the badge back — major
**Where:** `src/frontend/src/features/channels/useMarkRead.ts:83-88`, with `ChannelView.tsx:41-43` and
`docs/design/06-frontend-spa.md` §5.2 *Local write and hold* · **Checked:** a probe failed; removing
the release loop fixes it (see *What ran*).

The throttle effect's cleanup releases every hold. That cleanup runs on unmount as well as on a socket
change, and `MessageList` now unmounts on every switch. A read sent at the leading edge, or flushed as
the list unmounts, therefore loses its hold before its ack. `ChannelView` then invalidates the channel
list in the same commit, and that `GET` races the `mark_read` on the server. If it lands first, the
channel the user has just read shows its badge again until the next poll, focus return or switch. That
breaks the issue's first *Where the rules meet* rule on the *Paths* row "Switch while a read waits in
its window", which is the ordinary way to leave a channel. The code does what the plan's Task 2 says
("the effect's cleanup disposes it and releases its holds"). The plan's premise is the fault: decision
12 needs holds released on a socket change, and socket.io-client already does that
(`socket.js:447-471`, `_clearAcks` calls each `timeout()` ack with an error on close). Doc 06's line
"holds that write … until the ack, an error ack, or the timeout" is therefore not what the code does
today. Graded major, not critical, because it is a race the next refetch heals. Sent back for a red
test first (D32), with the plan line to change and the one-line code fix:
`code-reviewer-sendback-3.md`.

## Unpinned

- **`refetchOnWindowFocus: false` and `cancelRefetch: false`** (decision 18): the mutant with both
  reverted survives 13/13. By reading, the real code makes one fetch on a tab return. A `visibilitychange`
  and a `focus` both call `refetchQueries(…, { cancelRefetch: false })`, and the second joins the
  fetch in flight. TanStack's own focus handler is off for the list. Only reading holds this, and the
  first real run's network tab is the check.
- **The bold name's half** of the shared `unread` condition (`ChannelList.tsx:59`). Recorded by the
  writer.
- **`if (throttle.current === live)`** in the cleanup, and StrictMode in general. No test runs under
  StrictMode. By reading, the throttle is created inside the effect (`useMarkRead.ts:81`), so StrictMode's
  second setup builds a fresh one. The worry in expectation (b) doesn't apply.

## Left for the human

- The plan's **first real run** by hand (two browsers): the issue's *Acceptance* list. Check one list
  request on a tab return, and that switching away right after reading leaves no badge. The second
  check needs finding 1 fixed first.
- Assumed decisions to read: 15, 16, 22, 23, 28 (as the green report lists).
- The journey doesn't wait for the `mark_read` ack before the reload (plan, *What no test covers* (c)).
- The pre-existing semgrep finding in `testkit/report.py:96`. The branch doesn't touch it.

## Checked and sound

- R1 badge: `badgeText`/`badgeLabel` (`99+`, singular), `data-count` holds the text shown, hidden only
  for `readingChannelId`.
- R2 rule: `attending && atBottom`; `atBottom` starts `false` and is measured after every programmatic
  scroll and on scroll (`<` 80). The target skips `temp:`. No read before capture.
- R3/R4: leading and trailing per channel; the no-op on `isAtOrPast`; `send` false while disconnected;
  `connected` re-triggers the read effect on reconnect; the ack's result only releases.
- D30: `isLiveWorkspace(snapshot(), workspaceId)` at call time. `loading` counts as live, as plan-reviewer-2
  noted.
- R6: poll, pause, focus, switch, connect; a failed refetch keeps the list.
- R7: receipt for own user only; newest non-pending; else list invalidate. `userId` is in the socket
  effect's deps.
- R8: capture waits for detail and history to settle; ceiling; boundary predicate; the pin survives
  marker moves and tombstones; a remount resets it.
- R9: `role="separator"` named "New messages", `data-testid`s present.
- Nothing outside the file map changed (`git status`). The BDD and test files belong to the test-writer.
  The ADRs and doc 06 match the code except finding 1. The sweep found nothing stale.
- The green report's *What ran* matches what I ran and what the evidence shows.
