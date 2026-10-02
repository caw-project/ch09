# Plan review — issue 1, round 1: changes_requested

A strong plan. Its library claims hold against the installed TanStack 5.101.4, and it settles
almost every expectation in a decision row. Two major findings send it back. First, a RED test
for the poll's pause and return would pass today, because TanStack already refetches on
`visibilitychange`. That listener is on `window`, which the plan's helper leaves unsettled.
Second, the plan says a workspace switch drops a pending read, but the app takes the unmount
path, which flushes it. The plan's own test of the drop runs a path the app never takes. Both
can be fixed from the code and this review.

## Expectations                 (round 1 — written before the plan was opened)

Formed from the issue, doc 06 §4/§5.2, doc 02 §3.1.3/§3.2, register D16/D28/D31/D37, and
`useChannels.ts`, `ChannelList.tsx`, `ChannelView.tsx`, `MessageList.tsx`, `useMessages.ts`,
`useChannelSocket.ts`, `ChatLayout.tsx`, `stores/chat.ts`, `test/socket.ts`, `main.tsx`, the
BDD page object and step registry.

**Decisions**
- D-a. Where does the "being read" signal live? `STICK_THRESHOLD` and `wasAtBottom` are
  private to `MessageList`; the rule needs visibility, focus and the measured bottom together.
  Is "as measured, never assumed" honoured when `wasAtBottom` starts `true` and is reset to
  `true` on every `channelId` change (MessageList.tsx:45, :100)?
- D-b. How is the list brought to the bottom on a cached switch, given `MessageList` only
  scrolls when the count *grows* and stays mounted (issue *What exists*)? Same-length switch
  path (R2, *Paths* row 3).
- D-c. Where does the throttle live — per channel, keyed how — and what flushes it on a
  channel switch / unmount, and what drops it on socket change and workspace switch?
- D-d. "Leading and trailing, the window counted from each send" — does a trailing send
  open a new window (the *Timing* says yes) and does a leading send after a quiet window
  go at once?
- D-e. The no-op check ("at or past") — compared against which cache: list, detail, or both?
  And does the *locally written* `lastReadId` count (making repeated targets no-ops)?
- D-f. How is the local read "held" against an older fetch until the ack — where is the
  pending-read state kept (Zustand is client state only, D24: is a held marker server
  state?), and what clears it on an error ack or 5s timeout?
- D-g. The divider's capture: from which fetch (detail? list?), when is it "captured" on a
  cached return (wait for both refetches — of detail *and* history), and where is it stored
  so it survives the marker moving but is gone on leave-and-return?
- D-h. Divider qualifying message: "existed when the channel was opened" — measured how
  (ids in the history at capture time, or id ≤ some boundary)? And "by someone else, not
  deleted" — deleted *at capture time*, while the divider "stays above the tombstone" later.
- D-i. R7 "at or after the newest cached one" — newest including `temp:` ids? and "cached"
  meaning the message history query, for the event's channel.
- D-j. Badge "N as displayed" for >99: label "99+ unread messages"? `data-count` = "99+" or
  the real number? (issue: "holding the number shown").
- D-k. Badge hidden on the open channel "while it is being read" — does the sidebar get the
  read-rule state (shared signal), not just `activeChannelId`?
- D-l. Window focus refetch: TanStack 5's focusManager — the issue says visibility only; plan
  must add a `focus` listener and avoid a double refetch on visibilitychange+focus
  ("one list refetch" on alt-tab).

**Conflicts**
- C-1. R6 "a refetch that fails keeps the list" vs current `ChannelList`, which shows the
  error whenever `error` is set — TanStack keeps `data` on a failed refetch but sets `error`.
- C-2. R5 "a cached marker never moves backwards" vs R6/R7 refetches that bring an older
  `lastReadId` *after* the ack (*Where the rules meet*: "after the ack, fetches are taken as
  they come"). Which wins for `lastReadId` after the ack?
- C-3. R2 "whenever it becomes true" vs *Where the rules meet* "no read is sent until the
  divider has captured" — a held read once captured, or the rule re-evaluated?
- C-4. R3 "nothing sent when cached `lastReadId` is at or past" vs the hold — a refetch that
  brings an older marker re-opens a send?

**Tests that must exist**
- Each read-rule input flipped alone (hidden, blurred, scrolled up) with the other two true;
  a positive in the same test. Bottom measured via `giveLayout()`, both sides of 80px.
- Throttle against *Timing*: t=0, 500, 999, 1000, 1400, 2000, 3000, fake timers only for
  setTimeout/Date as needed.
- No-op: equal id and older id; positive with a newer one.
- Disconnect: no emit, nothing queued; reconnect sends once.
- Error ack and 5s timeout: no toast, no retry, (and hold released?).
- Cache writes to list *and* detail; the hold re-applied to a fetch in flight, with a
  deferred response, both orders (ack before / after the fetch lands).
- Receipts: at/after newest cached → write; older or uncached → list refetch.
- Poll: 30s visible, none hidden, one refetch on return, focus listener, connect, switch;
  failed refetch keeps the list; first-load failure shows error.
- Badge 0/1/99/100, singular label, bold name, hidden on open channel only while read.
- Divider: null capture, nothing qualifies, own messages and tombstones skipped, live
  message never grows one, stays on delete, gone on return, boundary older than loaded
  pages then appears on scroll-back, factory ids are UUIDv4 (not time-ordered).
- Cached-switch path: scrolled-back channel → cached same-length channel → no read.
- Workspace switch / socket change drops pending read; channel switch flushes it.
- BDD `read_state.feature` with a server-proving last step (reload); new "Grace reloads"
  step (only "Ada reloads CollabHub" exists).

**Risks**
- R-a. `MessageList` stays mounted on a cached switch, `wasAtBottom` reset to `true`: the
  rule would fire before measurement.
- R-b. The join ack invalidates the history; a cached return refetches detail and history —
  the divider capture racing these.
- R-c. The 30s poll, focus listener and connect refetch amplify the list-error branch (C-1)
  and the D37 401 banner path.
- R-d. `useChannelSocket`'s effect closes the socket on token renewal too — dropping a pending
  read on every renewal; is that fine?
- R-e. Hold state keyed per workspace? Keys already lead with `workspaceId`.
- R-f. Record: doc 06 §5.2 rewrite, ADR, correction of ADR lines 96–99.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 badge: pill, bold, `99+`, hidden on open channel only while being read | dec. 5, 17; ChannelList + ChannelView tests | covered |
| R2 read rule: visible, focused, measured within 80px; on becoming true and on arrival; newest non-pending incl. own and tombstones | dec. 2, 3, 14; `MessageList.reading`, `readTarget` tests | covered (80px boundary: minor 7) |
| R3 socket, ≤1 emit per channel per second, latest wins, no-op at/past | dec. 4, 11, 22; throttle + `useMarkRead` | covered; per-visit window: minor 3 |
| R4 no queue, no retry, reconnect re-evaluates, error/timeout ignored | `useMarkRead` + reconnect tests | covered |
| R5 local write to list and detail, never backwards | `writeLocalRead` tests | covered |
| R6 poll 30s visible, none hidden, focus, connect, switch; failed refetch keeps list | dec. 18–21 | covered; pause test red is wrong (finding 1) |
| R7 receipts: write or refetch | `applyReadReceipt` | covered; "newest cached" excludes pending without a row (minor 4) |
| R8 divider: capture once, loaded, someone else's, not deleted, existed at open, fixed, gone on return, boundary | dec. 13, 15, 16; `findDivider` + divider tests | covered |
| R9 labels, separator, test ids, `data-count` | dec. 24; markup block | covered |
| Decided 1–10 | decisions 1–10 | covered |
| *Where the rules meet* ×6 | Self-review maps each | covered, except pending read on workspace switch (finding 2) |
| *Paths* table ×9 | Self-review maps each | covered, except "Workspace switch mid-window" (finding 2) |
| Tests — Vitest list, one BDD journey, setup waits for each channel | Test approach, Tasks 1–4, dec. 25 | covered |
| Record — doc 06 §5.2, ADR, ADR 96–99 fix | Task 8 | covered |
| *Not in this issue* | *Not in this plan* | covered |
| D-a / R-a measured bottom | dec. 14, `atBottom` initially false | settled |
| D-b cached switch to bottom | dec. 14 (remount via `key`) | settled; conflicts with "do not change" (minor 5) |
| D-c throttle home, flush, drop | dec. 11 | settled; drop path broken (finding 2) |
| D-d leading/trailing semantics | throttle tests to *Timing* | settled |
| D-e no-op source | `cachedLastReadId`: the further of list and detail | settled |
| D-f hold storage and release | dec. 12 | settled; released on socket change (minor 6) |
| D-g / R-b capture timing | dec. 13 | settled |
| D-h "existed when opened" | dec. 15 (assumed) | settled |
| D-i pending in R7 | test only | minor 4 |
| D-j label and `data-count` above 99 | dec. 24, `badgeLabel` test | settled |
| D-k sidebar knows "being read" | dec. 17 | settled |
| D-l focus listener, single refetch | dec. 18 | settled |
| C-1 failed refetch vs error branch | dec. 21 | settled |
| C-2 marker backwards after ack | hold scoped to ack; `writeLocalRead` guard | settled |
| C-3 read before capture | `sends nothing until … settled` test | settled |
| C-4 no-op vs hold | hold rewrites only where marker < id | settled |
| R-c amplification of list error / D37 | dec. 21 + D37 note | settled |
| R-d socket change on renewal drops read | `useMarkRead` per `[socket, workspaceId]` | settled |
| R-e keys per workspace | keys already lead with `workspaceId` | settled |

## Findings

### 1. The pause-and-return poll test passes before the code exists — major
**Where:** Task 3, `ChannelList.test.tsx` row "does not poll while the tab is hidden +
refetches once when it becomes visible"; Task 2 `test/page.ts`. **Checked:** installed
`query-core/src/focusManager.ts:17-31` — the listener is on **`window`**, bubble phase. Also
`queryObserver.ts:404-410`, and `render.tsx`, whose provider mounts the client.

Today the list has no interval, so "no poll while hidden" passes. The return half depends on
how `setPageAttention` fires `visibilitychange`, and the plan doesn't say:
- **Fired with `bubbles: true`, as browsers do.** TanStack's default `refetchOnWindowFocus`
  refetches the stale list exactly once. The whole test is green at red, and the stated
  "`expected 1 to be 2`" is wrong.
- **Fired without `bubbles`.** TanStack never hears it. The test's red is then right, but the
  helper doesn't behave like a browser. Every other query's refetch-on-visible goes unexercised,
  and so does decision 18's reason for turning TanStack's listener off.

**What would settle it:**
- The helper fires `visibilitychange` on `document` with `bubbles: true`.
- This test gets a half that is red today — for example, after the return, advance `30000` and
  expect one more `GET`.
- Its expected red is restated to match.

### 2. A workspace switch flushes the pending read instead of dropping it — major
**Where:** dec. 11; Task 2 `useMarkRead` ("refs updated during render", the flush "declared
before the throttle effect", and the test "dropped on a workspace switch" via `rerender`).
**Checked:**
- `session.changeWorkspace` (`session.ts:199-212`) adopts the new session in place, with no
  navigation and no loading state.
- `ChannelView` therefore re-renders with a new detail key. It has no data, so it renders the
  pending state, and `MessageList` unmounts **in the same commit** in which `useChannelSocket`'s
  `[accessToken, …]` cleanup closes the old socket.
- **Unverified (React internals not read):** React runs a child deletion's passive cleanups
  before the ancestor's own effect cleanup.

On that order, the unmount flush runs with refs from `MessageList`'s last render: the old
socket, still `connected`, and the old workspace. The held read is **sent on the old
connection**. The issue says it is dropped (*Where the rules meet*, *Paths* "Workspace switch
mid-window"). The plan's test only rerenders the mounted hook with a new `workspaceId`, a path
the app never takes. It passes for a build that still sends.

**What would settle it:**
- The rule that decides "dropped" must hold when the unmount and the switch land together. For
  example, `send` could check the live workspace or socket, not the hook's last-render refs.
- A test that switches through `ChannelView` (new `workspaceId` and socket props in one
  rerender), with a positive half: a plain channel switch with a read held does send.

### 3. The throttle window doesn't outlive a visit — minor
**Where:** dec. 11 and dec. 14. **Checked:** plan text. `useMarkRead` lives in a `MessageList`
keyed per channel, so A→B→A within a second starts a fresh window for A. A new target on return
is then sent at once. That is two emits for one channel inside a second, against R3's "at most
one per channel per second". The flush on leaving is mandated, so this is a corner case and
harmless given the forward-only marker. Dec. 11 says "nothing needs to outlive it". It should
say the window doesn't either, and accept the case. As written, the throttle's per-channel map
is only exercised in its unit test.

### 4. R7's "newest cached one" excludes pending sends without a decision row — minor
**Where:** Task 2 `applyReadReceipt` comment and test "the newest cached message ignores a
pending send". It is the right reading: `temp:` sorts after every UUIDv7, so including pending
sends would always refetch. It belongs in a decision row, though, not only in a test.

### 5. Remounting per channel isn't flagged against the issue's "do not change" — minor
**Where:** dec. 14. The issue lists "stays mounted across a channel switch" under *What exists
already — Do not change any of this*, yet leaves "how the list is brought to the bottom" to the
plan. Dec. 14 is defensible and names its alternative. It should also say it departs from that
line, and why.

### 6. Holds are released when the socket changes — minor
**Where:** Task 2, "the effect's cleanup disposes it and releases its holds". On a token renewal
after an emit, the new socket's connect refetch can land before the server commits, and the
badge comes back until the next refresh. That may be acceptable, since the ack can never arrive.
Say so in the plan, so that the code pair doesn't "fix" it.

### 7. Smaller test details — minor
- **Interval length:** `ChannelList`'s poll tests should advance by the literal `30000`, not
  `CHANNEL_POLL_MS`. That export is undefined at red, as Task 1 already warns for the throttle.
- **The 80px boundary:** the reading tests flip "scrolled back" from far away. One test at 79
  and at 80 pins `<` against `≤` for the new `atBottom` measure.
- **Reload wording:** the journey's reload uses `Grace opens CollabHub`. The vocabulary (§19)
  separates arriving from reloading, and the issue says "reloads". Either reuse it with a note,
  or add `Grace reloads CollabHub` beside Ada's.

## Left for later stages
- Minors 3–7 if the writer leaves any of them.
- The journey doesn't wait for the `mark_read` ack before the reload. The plan declares this
  under *what no test covers* (c); a flake would show as a badge after the reload.
- Assumed rows the human should see: 15 (ceiling), 16 (boundary loaded), 22 (no window
  without a send), 23 (another user's receipt).
- Playwright focus: Task 9's `bring_to_front` fallback.

## Checked and sound
- **Header:** the base commit `14d0a04` matches `git log -1`. No sibling branches
  (`git branch --no-merged main` is empty).
- **Line references hold:**
  - TanStack: `query.ts:232-244`, `:404-419`, `:578`; `queryClient.ts:206`, `:319`;
    `focusManager.ts:74-82`; `queryObserver.ts:404-410`. The `timeoutManager` wraps the global
    `setInterval`, so fake timers reach the poll.
  - jsdom: `hasFocus` at `Document-impl.js:370-372`.
  - Repo: `ChannelList.tsx:29`, `MessageList.tsx:98-103`, `MessageList.test.tsx:47-66`,
    `useMessages.ts:228-230`, `useChannelSocket.ts:81-90`, `test_realtime_steps.py:39-50`,
    `steps/conftest.py:3-7`, `tests/bdd/conftest.py:64`.
- **Hold loop:** the hold can't loop — a fetch's `setData` carries no `manual`, while
  `setQueryData` sets `manual: true`.
- **Ripple:**
  - The only callers of `MessageList` are `ChannelView` and `MessageList.test.tsx`.
  - `useChannels` is used only by `ChannelList`.
  - No list-request counts are asserted in `App.test` or `ChatLayout.test`.
  - The store is reset after each test (`setup.ts:40`).
  - No OpenAPI, env var, chart or migration changes.
- **Workflow:** every RED task comes before GREEN, with the test-reviewer as the gate. *Found
  while building* is empty and no task commits. The plan is 590 lines and follows the exemplar's
  sections. Verification names `lint unit` and `e2e` only.
- **Register and record:** nothing is built on a 🔴 entry (D28, D16 and D37 are named). The
  record task covers doc 06 §5.2, the ADR via `adr-writer`, and the correction at ADR 96–99.
- **Markup:** the `getByLabelText` and `separator` queries match the markup. The new step regex
  doesn't collide with `Grace sees "{body}"…`.
- **Missing modules:** expected reds that are a missing module (Tasks 1 and 2) are file-load
  failures where every test needs the module.
- **Journey:** the last `Then` follows a fresh load with no channel open, so it shows the
  server's marker.
