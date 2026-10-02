# Unread counts and read markers in the SPA — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** The sidebar shows each channel's unread count, reading a channel moves the user's marker
(and clears the count in their other tabs), and an opened channel shows a "New messages" divider
where the user left off.

**Architecture:** Pure rules in `readState.ts` (badge text, read target, divider) and a per-channel
leading-and-trailing throttle in `readThrottle.ts`. `useMarkRead` owns one throttle per socket, emits
`mark_read`, writes the caches and holds that write against older fetches until the ack
(`readCache.ts`). `MessageList` measures the bottom, combines it with `usePageAttention`, captures
the divider once per visit and asks for reads; it is remounted per channel (`key`). The channel list
polls every 30 s while visible, and refetches on focus, on connect and on every channel switch;
`read_receipt_updated` writes or refetches through the same cache helpers.

**Tech Stack:** React 19, TanStack Query 5.101.4, Zustand, socket.io-client 4.8, Tailwind v4 ·
Vitest 5 + MSW 2 + `FakeSocket` · pytest-bdd + Playwright.

**Issue:** `docs/plans/issue-1/00-issue.md` — read it first. This plan argues from it and does not
repeat it. R1–R9 below are its requirements.

**Worktree:** `../caw-issue-1-q1`, branch `feature/issue-1-q1`, from `main` at `14d0a04`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R9; *Not in this issue* stays out |
| 2 | What "read" means | visible **and** focused **and** measured within `STICK_THRESHOLD` (80px) of the bottom |
| 3 | Marker target | newest non-pending loaded message, own messages and tombstones included |
| 4 | Transport | socket `mark_read`, throttled per channel, 1 s leading + trailing, latest wins; REST `POST …/read` unused |
| 5 | Badge | pill, `99+` above 99, bold name, hidden on the open channel only while it is being read, singular label for one |
| 6 | After a read | write list + detail caches directly; hold the write against older fetches until the ack |
| 7 | Divider | fixed for the visit, follows the server's unread rule |
| 8 | Background counts | polling, not push |
| 9 | Open channel | no "new messages below" pill |
| 10 | Register | D31 🟢 covers the data; nothing settled, no 🔴 built on |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 11 | Where the throttle lives | `createReadThrottle` in `features/channels/readThrottle.ts`, a plain timer object; one per socket + workspace, owned by `useMarkRead` inside `MessageList` | Pure, so *Timing* is a fake-timer unit test. Alternative: a context beside `SocketProvider` in `ChatLayout` — survives the list unmounting, but the issue sends a pending read *on* unmount anyway, so no held read needs to outlive it. **The window doesn't outlive the visit either** — see decision 28 |
| 12 | How the local read is held | `holdLocalRead` subscribes to the query cache and re-applies `writeLocalRead` after every **non-manual** `success` on the list or detail key, until the ack, an error ack or the 5 s timeout releases it | A fetch result dispatches `success` without `manual` (`query-core/src/query.ts:578`); `setQueryData` dispatches it with `manual: true` (`queryClient.ts:206`, `query.ts:232-244`), so re-applying never loops. Mirrors `reapplyAfterFetch` in `useChannelSocket.ts:81-90`. **A socket change releases every hold** (its ack can never arrive): after a token renewal, the new socket's connect refetch may land before the server commits and bring the badge back until the next refresh. Accepted — the code pair must not "fix" it by keeping holds across sockets. Alternative: a pending-reads map in Zustand merged in `select` — a second copy of server state (D24) |
| 13 | How the divider's capture is kept | `MessageList` state `{ lastReadId, ceilingId }`, taken at the **first render where the detail is not fetching and the history is `success` and not fetching**; the divider's message id, once found, is pinned for the visit | On a cached return both queries are already fetching on the first render (issue *assumes*, `main.tsx` has no `staleTime`), so this waits for both refetches; on a first open the detail has just loaded before `MessageList` mounts. Alternative: in the Zustand store — but it belongs to one visit, and remounting forgets it for free |
| 14 | How the list reaches the bottom on a switch | `ChannelView` renders `<MessageList key={channel.id} …>`: every channel is a fresh mount, which scrolls to its newest message as on first load; the bottom is then **measured** into `atBottom` state (initially `false`), never assumed | Kills the "same length, sits mid-history" path at the root, and resets the capture and flushes the pending read as an unmount. The `[channelId]` reset effect in `MessageList.tsx:98-103` goes. **This departs from the issue's *What exists already* ("stays mounted across a channel switch … do not change")**, which also leaves "how the list is brought to the bottom" to the plan; the two can't both hold without hand-resetting every per-visit ref, and nothing outside `MessageList` relies on the mount surviving (its only callers are `ChannelView` and its own test). See *Corrections*. Alternative: a `useLayoutEffect` on `channelId` that scrolls and re-measures — keeps the mount, but every per-visit ref has to be reset by hand |
| 15 | "Only messages that existed when opened" — **assumed** | `ceilingId` = the newest non-pending message id at capture; a message qualifies only if `lastReadId < id ≤ ceilingId` | UUIDv7 ids are time order (issue R7), so anything later arrived during the visit. Changing it (e.g. to a captured id set) is one function and its tests |
| 16 | "Boundary older than the loaded pages" — **assumed** | the boundary is loaded when some loaded non-pending message has `id ≤ lastReadId`, or there is no older page (`hasNextPage` false) | The only two ways to know the first unread is on screen. Cost to change: one predicate |
| 17 | Where "being read" is shared | Zustand `readingChannelId` (client state), set by `MessageList`, read by `ChannelList` for R1 | The sidebar is a sibling of the list in `ChatLayout`; this is a fact about the screen, not the server (D24) |
| 18 | Focus and visibility refetch | `refetchOnWindowFocus: false` on the list; `useChannelListRefresh` listens to `window` `focus` and `document` `visibilitychange`→visible and calls `refetchQueries({ queryKey }, { cancelRefetch: false })` | TanStack listens to `visibilitychange` only (`focusManager.ts:17-31`). A tab return fires both events; with `cancelRefetch: false` the second joins the fetch in flight (`query.ts:404-419`) — "one refetch on return". Leaving TanStack's listener on and adding a focus one would cancel and restart (`queryClient.ts:319` defaults it to `true`) |
| 19 | Poll | `refetchInterval: 30_000` on `useChannels`; `refetchIntervalInBackground` left `false` | The interval skips its tick while `focusManager.isFocused()` is false (`queryObserver.ts:404-410`), which reads `visibilityState !== 'hidden'` (`focusManager.ts:74-82`) — "none while hidden" for free |
| 20 | Where the switch refetch lives | `ChannelView`'s effect on `channelId` invalidates `channelKeys.list(workspaceId)`; `useChannelSocket`'s `onConnect` does the same | The two events the issue names, each in the file that already reacts to it |
| 21 | Sidebar error | `ChannelList` shows `channel-list-error` only while there is no data | TanStack keeps `data` on a failed refetch but sets `error`; today's `if (error)` (`ChannelList.tsx:29`) would replace the list |
| 22 | A no-op send and the window — **assumed** | `send` returns whether it emitted; a window opens only on an emit | "the window counted from each send": nothing sent, nothing counted. Cost to change: one branch, one test |
| 23 | A receipt for another user — **assumed** | ignored (`event.userId !== myUserId`) | The room is the user's own, so this never happens today; ignoring is the safe reading if a server bug ever sent one |
| 24 | `data-count` above 99 | holds `"99+"`, the text shown | R9: "the number shown" |
| 25 | Shared BDD steps | move `Given Grace is looking at the "{name}" channel` from `test_realtime_steps.py` to `steps/conftest.py`; `create_channel_and_wait` waits for the view **named** after the channel | pytest-bdd can't reach a sibling module's steps (`steps/conftest.py:3-7`). Waiting on any `channel-view` passes at once for the channel already open — the issue's "setup waits for each" |
| 26 | Sortable ids in tests | `messageIdAt(n)` in `test/factories.ts`: a UUIDv7-shaped id ordered by `n` | `aMessage()` ids are UUIDv4 (issue), so string order means nothing without it |
| 27 | Ack timeout | `MARK_READ_TIMEOUT_MS = 5000`, `socket.timeout(…).emit`, as `useSendMessage` does (`useMessages.ts:228-230`) | R4 |
| 28 | A→B→A inside one second — **assumed** | The return visit starts a fresh window, so a new target for A is sent at once: two emits for A inside a second | A departure from R3's "at most one per channel per second" in this one corner. The flush on leaving is mandated, and the forward-only marker makes the second emit harmless. Alternative: lift the throttle into a `ChatLayout` context keyed by channel (decision 11's alternative). Cost to change: move one object and its owner, no test of the rule changes |
| 29 | R7's "newest cached one" | the newest **non-pending** cached message; a `temp:` row is skipped | `temp:` sorts after every UUIDv7, so counting pending rows would make every receipt a refetch while a send is in flight. Same reading as R2's target |
| 30 | What decides "dropped on a workspace switch" | `send` reads the **live** session (`session.snapshot()`, `lib/auth/session.ts:72`) through the pure `isLiveWorkspace(state, workspaceId)` — `false` when signed out or signed in to another workspace, `true` when signed in to this one or still `loading` — never refs from the hook's last render | `changeWorkspace` (`session.ts:199-212`) sets the module state synchronously, before React renders; `MessageList` then unmounts in the same commit in which `useChannelSocket` closes the old socket, and the unmount's flush may run first, with the old socket still connected. The live session already names the new workspace, whatever the effect order. `loading` passes because no `MessageList` exists before sign-in, and it is what every Vitest test sees unless it sets the session. Alternative: rely on React running a deleted child's cleanups after the parent's — unverified, and a build that sends would pass |

Nothing here touches a 🔴 entry. The nearest: **D28** (no per-user preference, so no "don't mark
read" setting), **D16** (a tombstone may be marked read and never earns a divider — rule 15's
`deletedAt` filter), **D37** (a failed poll is a failed query, kept by decision 21 like any other).

## Corrections to the issue

The issue leaves four things to the plan (decisions 11–14); they are settled above. One line of
*What exists already* changes: **`MessageList` no longer stays mounted across a channel switch** —
`ChannelView` keys it by channel (decision 14). Task 8 records the remount in doc 06 §5.2. R3's
one-emit-per-second has one accepted corner (decision 28).

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** This is a new capability the user sees in the SPA, and only a
browser proves the server's marker moved (the badge stays clear after a reload). The journey goes
first; every rule below it goes down the pyramid, almost all to Vitest.

| Behaviour | Layer | File |
|---|---|---|
| Ada posts in #random; Grace's switch shows the badge; Grace reads it, leaves, reloads — still clear | **BDD** | `tests/bdd/features/read_state.feature` |
| Badge text and label, read target, `isAtOrPast`, divider placement | Vitest (pure) | `features/channels/readState.test.ts` |
| The throttle against *Timing* | Vitest (pure, fake `setTimeout`) | `features/channels/readThrottle.test.ts` |
| Cache writes, the hold, receipts · emit, no-op, disconnect, ack, flush and drop · visible and focused | Vitest | `features/channels/readCache.test.ts` · `useMarkRead.test.ts` · `usePageAttention.test.ts` |
| The read rule, input by input; reconnect; before capture | Vitest | `features/channels/MessageList.reading.test.tsx` |
| The divider in the DOM and its fixes | Vitest | `features/channels/MessageList.divider.test.tsx` |
| Switch paths: refetch, bottom, flush, R1 vs refetch, cached return | Vitest | `features/channels/ChannelView.test.tsx` |
| Badge, `99+`, poll, pause, focus, failed refetch | Vitest | `features/channels/ChannelList.test.tsx` |
| Receipt and connect through the socket | Vitest | `lib/realtime/useChannelSocket.test.tsx` |

**What no test covers:** (a) a real browser's focus — jsdom's `hasFocus()` is
`Boolean(_lastFocusedElement)` (`Document-impl.js:370-372`), so Vitest stubs it; only the journey
checks it. (b) The poll and a second tab end to end — Vitest proves both. (c) The `mark_read` ack
before the reload's `GET`: nothing waits for it. Accepted; a flake shows as a badge after reload.

**Baseline**, from `docs/test-report.md` at `e4d3396`: Vitest (frontend unit) 145 passed; unit total
467; end-to-end 19 passed. Expected counts are "N or more".

## Global constraints

- TanStack Query owns every channel and message; Zustand gets `readingChannelId` only (D24).
- Message ids are UUIDv7, compared as strings. Every emit has an ack timeout; no retry, no queue.
- Vitest queries by role, label or text, never `data-testid`; BDD selectors only in `chat_page.py`.
- No backend, chart, compose, script, env var or OpenAPI change: `Channel` already carries both fields.

## File map

Paths under `src/frontend/src/` unless they start `tests/` or `docs/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `test/factories.ts` | modify | `messageIdAt(n)` | 1 |
| `features/channels/readState.test.ts` · `readThrottle.test.ts` | create | the pure rules | 1 |
| `test/page.ts` · `test/layout.ts` · `test/setup.ts` | create · create · modify | `setPageAttention`/`resetPageAttention`; `giveLayout` (moved), `layoutEveryElement`; reset after each test | 2 |
| `features/channels/readCache.test.ts` · `useMarkRead.test.ts` · `usePageAttention.test.ts` | create | cache, sender, attention | 2 |
| `features/channels/MessageList.test.tsx` | modify | import `giveLayout` from `test/layout`; pass the two new props | 3 |
| `features/channels/MessageList.reading.test.tsx` · `MessageList.divider.test.tsx` · `ChannelView.test.tsx` | create | the components' red | 3 |
| `features/channels/ChannelList.test.tsx` · `lib/realtime/useChannelSocket.test.tsx` | modify | badge, poll; receipts, connect | 3 |
| `tests/bdd/features/read_state.feature` · `steps/test_read_state_steps.py` | create | the journey | 4 |
| `tests/bdd/pages/chat_page.py` | modify | badge readers; named wait in `create_channel_and_wait` and its private twin | 4 |
| `tests/bdd/steps/conftest.py` · `steps/test_realtime_steps.py` | modify · modify | the moved `Grace is looking at` step; new `Grace reloads CollabHub` | 4 |
| `features/channels/readState.ts` · `readThrottle.ts` | create | rules, throttle | 5 |
| `features/channels/readCache.ts` · `useMarkRead.ts` · `usePageAttention.ts` | create | cache, sender, attention | 6 |
| `stores/chat.ts` | modify | `readingChannelId`, `setReadingChannel` | 6 |
| `features/channels/useChannels.ts` | modify | poll, `refetchOnWindowFocus: false`, `useChannelListRefresh` | 7 |
| `features/channels/ChannelList.tsx` | modify | badge, bold, error only without data, calls `useChannelListRefresh` | 7 |
| `features/channels/MessageList.tsx` | modify | `atBottom`, capture, divider, read requests, `readingChannelId` | 7 |
| `features/channels/ChannelView.tsx` | modify | `key`, new props, switch refetch | 7 |
| `lib/realtime/useChannelSocket.ts` | modify | list refetch on connect, `read_receipt_updated` | 7 |
| `docs/design/06-frontend-spa.md` · `docs/adr/261002-unread-state-polls-rather-than-pushes.md` · `docs/adr/260915-read-state-follows-channel-visibility.md` | modify · create · modify | the record | 8 |

Deliberately unchanged: `tests/bdd/conftest.py` (truncation already lists `channel_reads`, :64);
`charts/`, `.env.example`; `types/messaging.ts`, `test/api.ts` (contract unchanged). Ripple,
checked: `App.test.tsx`, `ChatLayout.test.tsx` answer the extra list `GET`s with a function stub;
`ChannelList.test.tsx`'s exact `{ name: 'random' }` queries hold (`unreadCount: 0`, no badge).

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing Vitest and a journey that collects, each failing for the reason given — **test-reviewer gate** |
| GREEN — rules | 5 | code-writer | Task 1 passes |
| GREEN — cache, sender | 6 | code-writer | Task 2 passes |
| GREEN — components | 7 | code-writer | Task 3 passes; `tsc` clean |
| Finish | 8–9 | code-writer | the record, then verification — the journey's first run |

One red phase: nothing is generated, so every red is a missing module, a missing prop or an assertion.

---

## Task 1: The pure rules (RED)

**Files:** `test/factories.ts` (modify), `features/channels/readState.test.ts`,
`features/channels/readThrottle.test.ts` (create)

`messageIdAt(n: number): string` → `` `0199a000-0000-7000-8000-${n.toString(16).padStart(12, '0')}` ``,
so `messageIdAt(2) > messageIdAt(1)` as strings.

**Interfaces** — `features/channels/readState.ts`; `messages` are oldest-first, as
`useMessages`'s `select` returns them:

```ts
export const BADGE_MAX = 99
export function badgeText(count: number): string        // "1"…"99", then "99+"
export function badgeLabel(count: number): string       // `${badgeText(n)} unread message` + (n === 1 ? '' : 's')
export function isAtOrPast(marker: string | null | undefined, messageId: string): boolean // marker != null && marker >= messageId
export function readTarget(messages: readonly Message[]): string | null  // newest id without the `temp:` prefix
export interface DividerCapture { lastReadId: string | null; ceilingId: string | null }
export function captureFor(lastReadId: string | null, messages: readonly Message[]): DividerCapture // ceilingId = readTarget(messages)
export function findDivider(messages: readonly Message[], capture: DividerCapture,
                            userId: string, hasOlder: boolean): string | null
export function isLiveWorkspace(state: State, workspaceId: string | null): boolean
  // State from lib/auth/session (type import). signedIn → activeWorkspaceId === workspaceId;
  // signedOut → false; loading → true (decision 30)
```

`findDivider`: `null` if `capture.lastReadId` is null; `null` unless the boundary is loaded
(decision 16); else the first message with `lastReadId < id ≤ ceilingId`, `authorId !== userId`,
`deletedAt === null`, not pending.

`features/channels/readThrottle.ts`:

```ts
export const READ_WINDOW_MS = 1000
export interface ReadThrottle {
  request(channelId: string, messageId: string): void
  flush(channelId: string): void   // send a held read now, close that channel's window
  dispose(): void                  // clear every timer, drop every held read; later calls do nothing
}
export function createReadThrottle(
  send: (channelId: string, messageId: string) => boolean, // true when it emitted
  windowMs?: number,
): ReadThrottle
```

| Test (`readState.test.ts`) | Proves | Expected red |
|---|---|---|
| `badgeText shows 99 as 99 and 100 as 99+` | the cap, both sides | `Failed to resolve import "./readState"` |
| `badgeLabel is singular for one and plural otherwise` (1, 2) | R9 | same |
| `badgeLabel uses the number displayed` (100 → `"99+ unread messages"`) | R9 "N as displayed" | same |
| `isAtOrPast: null is never past; equal is; older is not; newer is` | R3 no-op, both sides | same |
| `readTarget skips a pending send at the end` | R2 | same |
| `readTarget includes the user's own message and a tombstone` (each newest in turn) | R2 | same |
| `readTarget is null with nothing confirmed loaded` | guard | same |
| `captureFor keeps the marker and takes the newest confirmed message as the ceiling` (pending row at the end) | decision 15 | same |
| `findDivider sits above the first message after the marker by someone else` | R8 | same |
| `findDivider skips the user's own messages` · `skips tombstones` (each with a qualifying message after it) | R8, each input alone | same |
| `findDivider: no divider for a null marker` (qualifying messages present) | R8 | same |
| `findDivider: nothing above the ceiling` (only qualifying message is after `ceilingId`) | live messages never grow one | same |
| `findDivider: none while the boundary is older than the loaded pages` · `found once a page holding it loads` · `found with no older page even if the marker precedes everything` | decision 16, both sides | same |
| `findDivider: none when the channel was read to the end` | R8 | same |
| `isLiveWorkspace: true for this workspace, false for another, false signed out, true while loading` (one test, all four) | decision 30 | same |

Every fixture uses `messageIdAt` and puts a second candidate after the expected one, so "first" is
told from "last".

| Test (`readThrottle.test.ts`) — `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` | Expected red |
|---|---|
| `sends the first read at once` (t=0, m2) | `Failed to resolve import "./readThrottle"` |
| `holds reads inside the window and sends the latest at its end` (m3, m4 at 500; nothing at 999; m4 at 1000) | same |
| `opens a new window from each send` (m5 at 1400; nothing at 1999; m5 at 2000) | same |
| `closes the window when nothing new was asked` (nothing at 3000; m6 at 3100 sent at once) | same |
| `throttles each channel on its own` | same |
| `flush sends a held read at once` · `flush sends nothing when nothing is held` | same |
| `dispose drops a held read` (advance 2 s: nothing) | same |
| `a send that emits nothing opens no window` (`send` returns false; next request sent at once) | same |

The *Timing* tests are one test each with the timeline, the window size written as the literal
`1000`, never `READ_WINDOW_MS` (an undefined import advances by `NaN`).

- [ ] Write both files and the factory helper; run `npm --prefix src/frontend test -- src/features/channels/readState.test.ts src/features/channels/readThrottle.test.ts`; record the failures. Leave uncommitted.

## Task 2: Cache, sender, attention (RED)

**Files:** `test/page.ts`, `test/layout.ts`, `readCache.test.ts`, `useMarkRead.test.ts`,
`usePageAttention.test.ts` (create); `test/setup.ts` (modify)

Test helpers (test code, so they exist at red):
- `test/page.ts`: `setPageAttention({ visible, focused }: { visible: boolean; focused: boolean })`
  defines `document.visibilityState`, spies `document.hasFocus`, and dispatches
  `new Event('visibilitychange', { bubbles: true })` on `document` — **bubbling, as browsers fire
  it**, so it reaches TanStack's listener on `window` (`query-core/src/focusManager.ts:23`; jsdom's
  `Document-impl.js:297-303` makes the window the document's parent) — and `focus`/`blur` on
  `window`, for what changed only; `resetPageAttention()` restores both. `setup.ts`'s `afterEach`
  calls it.
- `test/layout.ts`: `giveLayout` moved verbatim from `MessageList.test.tsx:47-66`, plus a `frozen`
  option whose `scrollTop` setter ignores writes; `layoutEveryElement(layout): () => void` defines the
  same getters on `HTMLElement.prototype` (per-element `scrollTop` in a `WeakMap`) for a list that
  mounts inside the test — a remount (decision 14) gives no chance to stub the new node first.

**Interfaces** — `features/channels/readCache.ts`:

```ts
export function cachedLastReadId(qc: QueryClient, workspaceId: string | null, channelId: string): string | null
  // the further of the list entry's and the detail entry's lastReadId
export function writeLocalRead(qc: QueryClient, workspaceId: string | null, channelId: string, messageId: string): void
  // in channelKeys.list and channelKeys.detail, where the entry's lastReadId is null or < messageId:
  // lastReadId = messageId, unreadCount = 0. Other channels and absent entries untouched.
export function holdLocalRead(qc: QueryClient, workspaceId: string | null, channelId: string, messageId: string): () => void
  // re-applies writeLocalRead after each non-manual `success` on either key; returns release()
export interface ReadReceiptEvent { channelId: string; userId: string; messageId: string }
export function applyReadReceipt(qc: QueryClient, workspaceId: string | null, event: ReadReceiptEvent, myUserId: string): void
  // other user: nothing. Messages cached and messageId >= newest non-pending cached id:
  // writeLocalRead. Otherwise invalidate channelKeys.list(workspaceId).
```

`features/channels/useMarkRead.ts`:

```ts
export const MARK_READ_TIMEOUT_MS = 5000
export function useMarkRead(socket: Socket | null, workspaceId: string | null, channelId: string):
  { request: (messageId: string) => void; connected: boolean }
```

- One throttle per `[socket, workspaceId]`; the effect's cleanup disposes the throttle; each hold is released only by its own ack, error ack or timeout — on a socket change the library calls every pending ack with an error, which releases them.
- Its `send`, read live at call time: `false` unless `socket.connected` and
  `isLiveWorkspace(session.snapshot(), workspaceId)` (decision 30 — the hook's last-render refs
  are not enough, because the unmount flush can run before the old socket closes); `false` when
  `isAtOrPast(cachedLastReadId(…), messageId)`; otherwise `writeLocalRead`, replace the channel's
  hold with `holdLocalRead`, `socket.timeout(5000).emit('mark_read', { channelId, messageId }, release)`,
  `true`. Whatever the ack says, it only releases.
- `channelId` change and unmount: `flush(previous channelId)` — declared **before** the throttle
  effect, so an unmount flushes before it disposes.
- `connected` starts from `socket?.connected ?? false` and follows the socket's `connect` /
  `disconnect` events.

`features/channels/usePageAttention.ts`: `usePageAttention(): boolean` —
`document.visibilityState === 'visible' && document.hasFocus()`, re-read on those three events.

| Test (`readCache.test.ts`) | Expected red |
|---|---|
| `writeLocalRead sets the marker and clears the count in the list and the detail` | `Failed to resolve import "./readCache"` |
| `writeLocalRead never moves a marker back` (list entry ahead: unchanged; detail behind: written — one test, both entries) | same |
| `writeLocalRead leaves other channels alone` | same |
| `cachedLastReadId reads the further of list and detail` (each ahead in turn) | same |
| `a held read is re-applied to a list fetch that lands with the old count` — the fetch is started before the hold and answered after it, as *Timing*'s t0–t2 | same |
| `a held read is re-applied to a detail fetch that lands with the old count` | same |
| `after release a fetch is taken as it comes` (count 3 stays 3) | same |
| `the hold leaves a fetch whose marker is already past it` | same |
| `a receipt at the newest cached message writes the list and the detail` · `…after it` | same |
| `a receipt older than the newest cached message refetches the list and writes nothing` | same |
| `a receipt for a channel with no cached messages refetches the list` | same |
| `the newest cached message ignores a pending send` (temp row at head; receipt at newest confirmed → written) | same |
| `a receipt for another user changes nothing` (not written, not invalidated) | same |

| Test (`useMarkRead.test.ts`) — `renderHookWithProviders`, `FakeSocket` with a `mark_read` responder | Expected red |
|---|---|
| `emits mark_read with the channel and the message` | `Failed to resolve import "./useMarkRead"` |
| `writes the caches as it emits, with no request` (`requests()` empty) | same |
| `sends nothing when the cached marker is at or past the id` + `sends when it is behind` (one test, both) | same |
| `sends nothing while disconnected, and nothing on reconnect by itself` | same |
| `an error ack is not retried` (responder `{ ok: false, problem: { status: 404 } }`; advance 2 s: one emit) | same |
| `a lost ack releases the hold after five seconds` (no responder; fetch with old count at 4999 → re-applied; at 5001 → taken) | same |
| `a read held in its window is sent when the channel changes` (`rerender` with another `channelId`) | same |
| `a read held in its window is sent when the hook unmounts` | same |
| `a read held in its window is dropped when the socket changes` (new `FakeSocket`, both connected: neither emits it) | same |
| `a read held in its window is dropped on unmount once the session is in another workspace` — two mounts in one test: the first unmounts with the session in this workspace and **sends** its held read (positive); the second holds a read, the mocked `snapshot` moves to another workspace, then unmounts: nothing more emitted after advancing 2 s. The socket stays connected throughout, so only decision 30 can stop it | same |

`useMarkRead.test.ts` and `ChannelView.test.tsx` mock `../../lib/auth/session` with
`vi.mock(path, async (importOriginal) => ({ ...(await importOriginal()), snapshot: vi.fn(() => ({ status: 'loading' })) }))`,
set per test with `vi.mocked(snapshot).mockReturnValue(…)`. No other test file needs it: `loading`
is what an unset session reads, and it sends.

| Test (`usePageAttention.test.ts`) | Expected red |
|---|---|
| `true when visible and focused` · `false when hidden` · `false when visible but blurred` | `Failed to resolve import "./usePageAttention"` |
| `follows visibilitychange, focus and blur` (false → true → false, one event each) | same |

- [ ] Write the helpers and the three files; run them; record each failure. Leave uncommitted.

## Task 3: The components (RED)

**Files:** `MessageList.reading.test.tsx`, `MessageList.divider.test.tsx`, `ChannelView.test.tsx`
(create); `MessageList.test.tsx`, `ChannelList.test.tsx`, `lib/realtime/useChannelSocket.test.tsx`
(modify)

**Interfaces** — props and state the code must expose:

```ts
// MessageList: two new required props
lastReadId: string | null     // the detail's, as ChannelView holds it
channelFetching: boolean      // the detail query's isFetching
// stores/chat.ts
readingChannelId: string | null
setReadingChannel: (channelId: string | null) => void
// useChannels.ts
export const CHANNEL_POLL_MS = 30_000
export function useChannelListRefresh(workspaceId: string | null): void
```

Markup the tests query (and `chat_page.py` reads):

```tsx
// ChannelList, inside the NavLink, when unreadCount > 0 and channel.id !== readingChannelId
<span className="font-semibold">{channel.name}</span>
<span data-testid="channel-unread-badge" data-count={badgeText(n)} aria-label={badgeLabel(n)} …>{badgeText(n)}</span>
// MessageList, immediately before the divider message's MessageItem
<div role="separator" aria-label="New messages" data-testid="new-messages-divider" …>New messages</div>
```

A link with a badge is named e.g. `general 3 unread messages` — query it by regex; the badge by
`getByLabelText('3 unread messages')`.

`MessageList.test.tsx`: import `giveLayout` from `../../test/layout`, pass
`lastReadId={null} channelFetching={false}`. Its tests stay green at runtime; `tsc` is red.

| Test (`MessageList.reading.test.tsx`) — socket connected, `setPageAttention`, `giveLayout` | Proves | Expected red |
|---|---|---|
| `marks read up to the newest message when visible, focused and at the bottom` | R2, R3 | no `mark_read` in `socket.emitted` (`expected [...] to deep equally contain …`) |
| `not while the tab is hidden` · `not while the window is blurred` · `not while scrolled back` — each with the other two true; nothing emitted once the history has rendered, then that one input flipped and exactly one emit | R2, each input alone, with its positive | no emit after the flip |
| `marks read when the page becomes visible again` · `when scrolled to the bottom` | "whenever it becomes true" | no emit |
| `79px from the bottom counts as the bottom and 80px does not` (`giveLayout({ frozen: true })` so the list's own scroll-to-newest can't move it, held at `scrollHeight - scrollTop - clientHeight` = 80: no emit after a scroll event; the test calls `giveLayout` again at 79 (the properties are `configurable`) and fires another: one emit) | `<`, not `≤`, against `STICK_THRESHOLD` | no emit at 79 |
| `marks read again when a message arrives while being read` (second emit after 1000 ms, new id) | R2, R3 | no emit |
| `targets the newest confirmed message, not a pending send` | R2 | no emit |
| `sends nothing until the channel and its history have settled` (`channelFetching` true → none; false → one) | where the rules meet: capture first | no emit in the positive half |
| `evaluates again on reconnect and sends once` (message arrives while disconnected; `serverConnect` → exactly one) | R4, *Paths* reconnect | no emit |
| `reports the channel as being read only while all three hold` (`readingChannelId` toggles with each input) | R1's source | `undefined` ≠ channel id |

| Test (`MessageList.divider.test.tsx`) | Expected red |
|---|---|
| `draws the divider above the first message after the marker by someone else` (next article holds that body) | `Unable to find role="separator"` |
| `no divider when the marker is null, and one when the same history has a marker` — two renders in one test, the same messages | separator not found in the second half |
| `a message arriving during the visit grows no divider`: with one earlier unread message the divider stays above it when Grace's message arrives; in a second render read to the end, the arrival draws none | separator not found in the first half |
| `the divider stays where it is as the marker moves` (rerender with the newer `lastReadId`) | separator not found |
| `the divider stays above its message once it is deleted` (tombstone upserted) | separator not found |
| `no divider until scrolling back loads the page holding the boundary`, then above the right message | separator not found |
| `the divider waits for the channel to settle` (`channelFetching` true → none) | separator not found |

| Test (`ChannelView.test.tsx`) — `ChannelList` + `ChannelView` at `path="/c/:channelId"`, switching by clicking links | Expected red |
|---|---|
| `refetches the channel list on every channel switch` (list `GET`s grow by one per click) | request count short by one |
| `a cached channel opened from one scrolled back is read once measured at the bottom` (`layoutEveryElement`) | no emit for B |
| `a cached channel that sits mid-history is not read` (`frozen`, anchored on B's history refetch landing; then a scroll to the bottom sends one) | positive half: no emit |
| `a read waiting in its window is sent when the user switches channel` (A's held id emitted before B's) | no emit |
| `a read waiting in its window is sent on a channel switch and dropped on a workspace switch` — the app's own path: hold a read in A, click to B (A's held id is emitted: the positive); hold a read in B, set the mocked `snapshot` to signed in to another workspace and rerender `ChannelView` (and `ChannelList`) with that `workspaceId` in one `rerender`, as `App` does after `changeWorkspace` — the detail key changes, `ChannelView` renders its pending state and `MessageList` unmounts. Advance 2 s: B's held id is never emitted. The test's `FakeSocket` stays connected, so the old connection is live, as it is in the app when the child's cleanup runs first | positive half: no emit for A |
| `a refetch with a count for the channel being read does not show its badge, and hiding the tab does` | badge label not found in the second half |
| `returning to a cached channel captures today's marker after both refetches` (detail and history held separately: no divider while either is held; then above the message that arrived while away; no `mark_read` before) | separator not found |

| Test (`ChannelList.test.tsx`) | Expected red |
|---|---|
| `shows a count pill and a bold name for a channel with unread messages` | `Unable to find a label with the text of: 3 unread messages` |
| `no pill for a channel with none` — beside one with a count in the same list, whose pill is found first | label not found |
| `shows 99 as 99 and 100 as 99+` · `labels one unread message in the singular` | label not found |
| `hides the badge of the channel being read only` (`readingChannelId` set; the other channel's badge still shows) | label not found (positive half) |
| `refetches every 30 seconds while visible` (`useChannelListRefresh` and the interval, through `ChannelList`; fake `setInterval`/`clearInterval`; none at 29 999, one at 30 000 — the literal `30000`, never `CHANNEL_POLL_MS`, undefined at red) | `expected 1 to be 2` (list `GET`s) |
| `pauses the poll while hidden, refetches once on return, then polls again` — one test: hide, advance `30000`: still 1 `GET`; return (`setPageAttention` fires the bubbling `visibilitychange` and `focus`): 2; advance `30000`: 3. Today TanStack's default `refetchOnWindowFocus` hears the bubbling event and makes the return's refetch, so the first two counts pass at red — the last half is the one red today | `expected 2 to be 3` |
| `refetches once when the window regains focus with the tab visible` | `expected 1 to be 2` |
| `keeps the list it shows when a refetch fails` (500 Problem on the second `GET`: links stay, no `alert`) | `alert` role found |
| `shows the error when the list never loaded` | passes today — kept as the other side of the line |

| Test (`useChannelSocket.test.tsx`, new `describe('read state')`) | Expected red |
|---|---|
| `refetches the channel list on every connect` (connect, drop, connect: invalidated each time) | `isInvalidated` false |
| `applies the user's own receipt to the list and the detail` | `lastReadId` unchanged |
| `refetches the list for a receipt older than the newest cached message` | not invalidated |
| `ignores a receipt for another user` — anchored on the user's own receipt applying in the same test | first half fails as above |

- [ ] Write all six; run `npm --prefix src/frontend test -- src/features/channels src/lib/realtime/useChannelSocket.test.tsx` and `npm --prefix src/frontend run typecheck`; record each failure. Leave uncommitted.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/read_state.feature`, `steps/test_read_state_steps.py` (create);
`pages/chat_page.py`, `steps/conftest.py`, `steps/test_realtime_steps.py` (modify)

```gherkin
@bdd
Feature: Read state

  Each channel in the sidebar counts other people's messages you haven't read.
  Looking at a channel's newest message — window in front, scrolled to the end —
  reads it, and the count stays clear wherever you open CollabHub next.

  Background:
    Given Ada is signed in

  # Rules are proven in Vitest; this proves the server's marker moved.
  Scenario: Grace's unread count clears once she has read the channel
    Given Ada has created a public channel named "general"
    And Ada has created a public channel named "random"
    And Ada has created a public channel named "design"
    And Grace is looking at the "general" channel
    When Ada opens the "random" channel
    And Ada sends "lunch is in the kitchen"
    And Grace opens the "design" channel
    Then Grace sees 1 unread message in "random"
    When Grace opens the "random" channel
    Then Grace sees "lunch is in the kitchen" in the channel
    When Grace opens the "general" channel
    And Grace reloads CollabHub
    Then Grace sees no unread messages in "random"
```

- Reused verbatim: `Ada is signed in`, `Ada has created a public channel named`, `Ada opens the`,
  `Ada sends`, `Grace opens the "{name}" channel`, `Grace sees "{body}" in the channel` (all
  `steps/conftest.py`) and `Grace is looking at the "{name}" channel`, **moved** from
  `test_realtime_steps.py:39-50` into `steps/conftest.py` unchanged (decision 25).
- New, in `steps/conftest.py` beside `Ada reloads CollabHub` (`:116-118`) and in its shape:
  `@when("Grace reloads CollabHub")` → `grace.open()`. Vocabulary §19 keeps arriving and reloading
  apart, and the issue says "reloads".
- New, in `test_read_state_steps.py`: `parsers.re(r'Grace sees (?P<count>\d+) unread messages? in
  "(?P<name>[^"]*)"')` with `converters={"count": int}` → `grace.has_unread_badge(name, count)`;
  `Grace sees no unread messages in "{name}"` → `grace.lacks_unread_badge(name)`.
- `ChatPage`: `has_unread_badge(name, count)` — `_settle()`, then a retrying
  `to_have_attribute("data-count", str(count))` on `_channel_item(name).get_by_test_id("channel-unread-badge")`;
  `lacks_unread_badge(name)` — `_settle()`, the item visible (the anchor: the badge renders in the
  same render as the item), then `to_have_count(0)` on the badge. `create_channel_and_wait` and
  `create_private_channel_and_wait` wait for `[data-testid='channel-view'][data-channel-name='{name}']`.
- The last `Then` follows a reload, so it shows what the server holds (vocabulary §22, §23).
- Expected red, at e2e only (Task 9): `assert grace.has_unread_badge(...)` fails — no badge. Before
  that: `uv run pytest tests/bdd --collect-only -q` lists the scenario, and `--generate-missing
  --feature tests/bdd/features` prints nothing.

- [ ] Write the feature, steps and page methods; move the step; run the two checks above. Leave uncommitted.

> **Gate:** the test-reviewer approves Tasks 1–4 before any GREEN task starts.

## Task 5: The rules (GREEN)

- [ ] `readState.ts` and `readThrottle.ts` to Task 1's interfaces. Throttle state is a
  `Map<channelId, { timer, held: string | null }>`; a timer firing sends `held` if any and reopens
  only when `send` returned `true`.
- [ ] Task 1 passes. Leave uncommitted.

## Task 6: Cache, sender, attention (GREEN)

- [ ] `readCache.ts`. The hold, because it is the non-obvious line:

  ```ts
  // A fetch result dispatches `success` without `manual` (query.ts:578); our own
  // setQueryData carries `manual: true` (queryClient.ts:206) — so this never loops.
  const unsubscribe = qc.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success' || event.action.manual) return
    if (!hashes.has(event.query.queryHash)) return
    writeLocalRead(qc, workspaceId, channelId, messageId)
  })
  ```
- [ ] `useMarkRead.ts` — `send` calls `isLiveWorkspace(snapshot(), workspaceId)` at call time,
  never a ref (decision 30) — and `usePageAttention.ts`; `stores/chat.ts` gains `readingChannelId: null` and
  `setReadingChannel`.
- [ ] Task 2 passes. Leave uncommitted.

## Task 7: The components (GREEN)

- [ ] `useChannels`: `refetchInterval: CHANNEL_POLL_MS`, `refetchOnWindowFocus: false`.
  `useChannelListRefresh(workspaceId)`: window `focus`, and `visibilitychange` when visible, call
  `queryClient.refetchQueries({ queryKey: channelKeys.list(workspaceId) }, { cancelRefetch: false })`.
- [ ] `ChannelList`: calls `useChannelListRefresh`; the badge and bold name (Task 3's markup); the
  error branch only when `channels === undefined` (decision 21).
- [ ] `MessageList`: `atBottom` state measured in `onScroll` and at the end of the layout effect
  after any programmatic scroll (`scrollHeight - scrollTop - clientHeight < STICK_THRESHOLD`), never
  initialised `true`; drop the `[channelId]` reset effect. Capture (decision 13) in an effect, then
  `dividerId` = the pinned `findDivider(messages, capture, userId, hasNextPage)`. `beingRead =
  usePageAttention() && atBottom`; an effect keeps `readingChannelId` in step and clears it on
  unmount. An effect on `[beingRead, capture, connected, readTarget(messages)]` calls
  `request(target)` when all hold. Render the separator before the divider message.
- [ ] `ChannelView`: `key={channel.id}`, `lastReadId={channel.lastReadId}`,
  `channelFetching={isFetching}`; the `channelId` effect also invalidates the list.
- [ ] `useChannelSocket`: `onConnect` invalidates `channelKeys.list(workspaceId)`;
  `live.on('read_receipt_updated', (e) => applyReadReceipt(queryClient, workspaceId, e, userId))`.
  Its header comment gains the receipt.
- [ ] Task 3 passes; `npm --prefix src/frontend run typecheck` clean; the whole Vitest run is 145
  or more plus the new tests, none failing. Leave uncommitted.

## Task 8: The record

- [ ] Doc 06 §5.2: "Debounce `typing`; throttle `mark_read`." becomes "Debounce `typing`.", plus
  **Read state — added 2026-10-02**: read rule and measurement, target, throttle and *Timing*, no
  queue/retry, local write and hold, polling, receipts, the divider, the remount per channel.
- [ ] ADR (`adr-writer`), `docs/adr/261002-unread-state-polls-rather-than-pushes.md`, with the
  issue's three alternatives and its revisit condition (a push to the user room).
- [ ] `docs/adr/260915-read-state-follows-channel-visibility.md:96-99`: the Postgres-only rules are
  now covered by `src/services/messaging/tests/integration/test_read_state.py`.
- [ ] Sweep `docs/design` and `src/frontend/src` for "throttle `mark_read`" and
  `read_receipt_updated` still described as ignored. Leave uncommitted.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit`, then `scripts/test.sh e2e` — each once. No `integration`: no
  service's Python, SQL or stream changes. Counts at or above the baseline: Vitest ≥ 145 + new,
  e2e ≥ 20.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`.
- [ ] **First real run**, `docker compose up -d --build`: the issue's *Acceptance* list, every line
  (read devtools' network tab *after* closing it — it steals focus). Fix what it finds with a test.
- [ ] If the journey sends no read, check `document.hasFocus()` under Playwright; if false, add
  `self.page.bring_to_front()` to `ChatPage.open_channel`. Record either below.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Filled in by the code-writer, round 1.

- **No deviation from the plan's interfaces or decisions.** All GREEN tasks went green on the first
  run of their tests; the journey passed on its first e2e run, so the `bring_to_front` fallback in
  Task 9 was not needed (`document.hasFocus()` is true under Playwright's headed-less Chromium here).
- **Placement of one detail the plan leaves open:** `ChannelList`'s bold name and badge share one
  condition (`unreadCount > 0 && id !== readingChannelId`), so a channel being read is not bold
  either. Pinned by `ChannelList.test.tsx` (hides the badge of the channel being read) for the badge;
  the bold half has no test of its own.
- **`measure` and `NO_MESSAGES`** are module-level in `MessageList.tsx` (a stable empty array and a
  pure function), so the layout effect and the capture effect satisfy `react-hooks/exhaustive-deps`
  without a suppression. `isPending` is a dependency of the layout effect so an empty channel is
  still measured once its scroller appears. No test.
- **Round 2 (code-reviewer-1 finding 1, via test send-back):** `useMarkRead`'s throttle cleanup no
  longer releases holds — it also runs on unmount, so a channel switch dropped an un-acked read's
  hold. Pinned by the new tests in `useMarkRead.test.ts`; doc 06 §5.2 and Task 2 corrected.
- **Not done:** the plan's *first real run* by hand (two browsers, `docker compose up`) — left to the
  human, see the green report. Real-browser focus is covered by the journey passing.

## Not in this plan

Everything under the issue's *Not in this issue*.

## Self-review

- **Issue coverage:** R1 → Tasks 3 (`ChannelList`, `ChannelView` badge tests), 7 · R2 → 1
  (`readTarget`), 2 (`usePageAttention`), 3 (`MessageList.reading`), 7 · R3 → 1 (throttle, `isAtOrPast`),
  2 (`useMarkRead` no-op) · R4 → 2 (disconnect, error ack, lost ack), 3 (reconnect) · R5 → 2
  (`writeLocalRead`, hold) · R6 → 3 (`ChannelList` poll/pause/focus/failure; `ChannelView` switch;
  `useChannelSocket` connect) · R7 → 2 (`applyReadReceipt`), 3 (socket) · R8 → 1 (`findDivider`), 3
  (divider, cached return) · R9 → 1 (labels), 3 (markup), 4 (`data-count`).
- **Where the rules meet:** local read vs refetch → hold tests (2) · divider vs own read → `sends
  nothing until … settled` and `returning to a cached channel…` (3) · divider vs live → ceiling (1, 3)
  · badge vs refetch → `ChannelView` badge test (3) · pending read and leaving → `useMarkRead` flush
  and drop (2), `ChannelView` switch flush (3) · polling and failure → `ChannelList` (3).
- **Paths:** first open → divider test + journey · cached return → `ChannelView` (3) · scrolled-back
  switch → two `ChannelView` tests · switch mid-window → flush test · reconnect → reading test ·
  second tab → receipt tests · hidden/blurred → reading + poll tests · workspace switch →
`isLiveWorkspace` (1), the unmount drop (2) and `ChannelView`'s switch-then-workspace test (3) ·
  scroll-back loads boundary → divider test.
- **Names:** `read_receipt_updated`, `mark_read` as the server spells them; `readingChannelId`
  everywhere; `channel-unread-badge` and `new-messages-divider` only in `chat_page.py` and the markup.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** `setPageAttention` fires a bubbling `visibilitychange` (Task 2, sources cited); the
   pause test's last half (a third `GET` 30 s after the return) is red today: `expected 2 to be 3`.
2. **Fixed.** Decision 30: `send` checks the live session via the pure `isLiveWorkspace`, not
   last-render refs. Tests: `isLiveWorkspace` (Task 1); unmount drop with a sending positive, socket
   connected (Task 2, replacing the `rerender` test); `ChannelView` switch-sends, workspace-drops (Task 3).
3. **Fixed.** Decision 11 notes it; decision 28 (**assumed**) records the corner and its cost.
4. **Fixed.** Decision 29.
5. **Fixed.** Decision 14 names the departure; *Corrections to the issue* records it.
6. **Fixed.** Decision 12 says so, and that it is accepted.
7. **Fixed.** Literal `30000`; a 79/80 test in `MessageList.reading`; new `Grace reloads CollabHub`.
