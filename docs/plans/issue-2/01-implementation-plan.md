# Message search in the SPA — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A search box in the sidebar, a `/search?q=` results page, and a click-through that opens
the result in its channel — paged back to, centred and highlighted — without marking the channel read
on the way.

**Architecture:** Search is a new `features/search/` folder: a `useInfiniteQuery` keyed
`['search', workspaceId, q]` over the existing `GET /api/v1/search/messages`, rendered as a list of
links to `/c/:channelId?message=<id>`. The jump is a hook inside `MessageList`
(`useMessageJump`), driven by a pure step function (`nextJumpStep`): it decides only while history is
idle, pages back with `fetchNextPage({ cancelRefetch: false })` up to 10 loaded pages, and holds
reads and auto-scroll off while it runs. R8 is two changes to who cancels whom: every page fetch passes
`cancelRefetch: false`, and the join-ack refetch goes through `refetchHistory`, which waits for an
in-flight page fetch to land before refetching.

**Tech Stack:** React 19, react-router 7, TanStack Query 5.101.4, Zustand, Tailwind v4, Vitest + MSW +
Testing Library · pytest-bdd + Playwright · bash (`scripts/test.sh`).

**Issue:** `docs/plans/issue-2/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-2`, branch `feature/issue-2`, from `main` at `950e66a`.

## Decisions

Decided by the issue (its *Decided already* 1–10 and R1–R10):

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R10, SPA plus `scripts/test.sh`; no Messaging change, no `around` cursor |
| 2 | Where search lives | Box in the sidebar, results on `/search?q=`, submit on Enter only |
| 3 | Results | Newest first as served, plain text, no match highlighting, "Load more", a snapshot never updated live |
| 4 | The jump | URL param `message`, removed with `replace`; cap 10 loaded pages in total; highlight 2 s; no read during a jump; a failed fetch ends it |
| 5 | R8 | The `MessageList` cancel defect is fixed here |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 6 | How the jump waits on a refetch | `nextJumpStep` returns `wait` whenever history `isFetching`; it looks at the loaded pages only when idle | The issue's *Timing* (t1 "the jump waits"). Alternative: look while fetching and race the refetch's replace of `pages` |
| 7 | How R8's "no page fetch cancels a refetch" holds | Every `fetchNextPage` passes `{ cancelRefetch: false }`; one that lands on a refetch in flight gets that refetch's promise and fetches nothing (`query.ts:411-419`), so the caller looks again after | The default is `true` (`queryObserver.ts:328`) — the defect. Alternative: a guard on `isFetching` alone, which leaves the jump's own calls unprotected |
| 8 | How R8's "a refetch never loses a page" holds | `refetchHistory(queryClient, key)`: if a page fetch is in flight (`state.fetchMeta?.fetchMore?.direction === 'forward'`, the same test as `infiniteQueryObserver.ts:153-156`), wait for it to go idle, then invalidate; otherwise `invalidateQueries` as today | `invalidateQueries` refetches with `cancelRefetch: true` (`queryClient.ts:319`), and a successful page fetch clears `isInvalidated` (`successState`, `query.ts:731-738`), so a cancelled recovery refetch would never re-run. A refetch still cancels a *refetch*: no page is lost, and it is today's behaviour |
| 9 | A scroll to the top while a refetch runs — **assumed** | Nothing is fetched and `heightBeforePrepend` is not set; the wish is remembered and the older page is fetched when the refetch lands, if the list is still within `LOAD_THRESHOLD` of the top | The issue says only "never cancels". Dropping the wish would strand a reader at `scrollTop` 0, where no further scroll event can fire. Changing it is one ref and one test |
| 10 | Where the jump lives | `useMessageJump` inside `MessageList`, reading `useSearchParams` | `ChannelView` keys `MessageList` by channel, so a switch or Back unmounts it, and its cleanup is R9's abandon for free. Alternative: in `ChannelView`, which survives a same-channel param change but would need its own abandon logic |
| 11 | How R7 holds reads off | `jumping` is true **in the first render the param is present** — on a fresh mount (`useState` initialiser) *and* on a mounted list it arrives on (the hook keeps `seenParam` in state and adopts a changed param **during render**, React's "adjusting state when a prop changes", so the render that commits already has `jumping` true). `beingRead = attending && atBottom && !jumping` | Issue *Where the rules meet*: a fresh mount is "at the bottom" for a moment, and the open channel usually *is* at the bottom — a flag set in an effect would be one committed render late, and the read effect would run in it |
| 26 | Where the list sits while seeking (C3) | A fresh list still makes its **first** scroll to the newest message (the layout effect's growth from 0 messages); after that, growth does not pull while `jumping`. Every page the jump loads goes through `loadOlder`, which sets `heightBeforePrepend`, so a prepend keeps the view where it was — the newest on a fresh mount, "wherever the list is" on the open channel. At the cap, `give-up` scrolls to the newest | Issue *Where the rules meet* ("opens a channel at its newest messages before scrolling away") and *Paths* row 7. Alternative: no scroll at all while jumping, which leaves a fresh list at the oldest loaded page for the whole seek |
| 27 | The scroll handler during a jump — **assumed** | Stays armed. `onScroll` and the jump both load through one `loadOlder()`, which fetches only when `hasNextPage` and the query is idle **now** (`queryClient.isFetching({ queryKey, exact: true }) === 0`, not the render's `isFetching`), so there is one page fetch at a time whoever asks. A page a user's scroll loads while seeking counts towards the 10 (R7 counts loaded pages, not the jump's calls). After `found`, a target centred near the top may load an older page as any reader at the top does — anchored, so the target stays put; the cap bounds the *seek* only | Alternative: disarm loading while seeking, which strands a reader who scrolled to the top (decision 9's reason). Changing it is one condition in `onScroll` |
| 28 | A read held by the throttle when a jump starts — **assumed** | Flushed at once, in the commit the jump starts in: `useMarkRead` returns `flush()` (the throttle's existing `flush(channelId)`), and `MessageList` calls it when `jumping` turns true. Nothing is requested after that until the jump ends | It was asked for before the jump, for messages read at the bottom; sending it at its window's end (≤1 s, `READ_WINDOW_MS`) would be a read *during* the jump (R7). Alternative: drop it, losing a read the user earned. Changing it is one line |
| 12 | Who removes the param, and what a removed param means | The hook removes `message` with `setSearchParams(fn, { replace: true })` at each end (found, cap, failed). A param that disappears while the jump is still **seeking** abandons it | Distinguishes the hook's own removal from navigation without a second ref. A param changing to another id restarts — latest target wins (R9) |
| 13 | The highlighted message's test hook | The existing `<article data-testid="message-item">` gains `data-highlighted="true"` while highlighted, the same pattern as `data-pending` | See *Corrections*. One element cannot carry two `data-testid`s, and a swapped testid would break `_item_for` mid-highlight |
| 14 | Highlight styling | `bg-accent/15` on the article while highlighted, with `transition-colors duration-700` always on, so removing the class at 2 s is the fade | No new CSS; light palette only (D26) |
| 15 | Date and time format | `<time dateTime={createdAt}>` showing `toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })` | Same reasoning as `MessageItem`'s `timeOfDay`: the browser locale, never a stored preference (D28 🔴 is untouched) |
| 16 | Retry beside `ProblemBanner` | `SearchPage` renders `<ProblemBanner error>` and, when there is **no data**, a `Retry` button calling `refetch()`. A failed Load more keeps the list and the banner; the Load more button stays and clicking it again is the retry | `ProblemBanner` stays `error`-only, unchanged. Alternative: an `action` prop on the banner, which touches every caller's tests |
| 17 | Search query options | `enabled: q !== ''`, `refetchOnWindowFocus: false`, `refetchOnReconnect: false`; default `staleTime` 0 so a remount refetches — **every** loaded "Load more" page, from fresh cursors (`infiniteQueryBehavior.ts:94-107`): that is R2's "refetches it" | R2 "never updates live": TanStack's focus and reconnect refetches would change a list on screen. The app-wide `retry` (one retry for 5xx, `main.tsx:21-24`) still applies |
| 18 | `/search` with a blank or missing `q` — **assumed** | Shows "Type in the search box to find messages." and fetches nothing | The server would answer 400; a hand-edited URL is not an error worth a banner. One branch to change |
| 19 | Resubmitting the same `q` — **assumed** | The box invalidates `searchKeys.results(ws, q)` and navigates only when the URL would change, so no duplicate history entry | R1 "refetches it". Alternative: push a duplicate entry, which makes Back a no-op once |
| 20 | Channel-name lookups — **assumed** | Wait for the channel list to settle; for ids not in it, `useQueries` over `channelKeys.detail(ws, id)` with `retry: false`, `staleTime: Infinity` | Shares the detail cache with `ChannelView`; `staleTime: Infinity` makes "once per distinct channel" survive re-renders; `retry: false` makes a 404 settle at once. Fetching before the list settles would ask for details the list was about to supply |
| 21 | Not found, history exhausted under the cap — **assumed** | Treated as the cap: newest messages, the same notice, param removed | Only a hand-edited URL reaches it (a result's message is in its channel; tombstones stay in history). Alternative: silent end. Changing it is one branch and one string |
| 22 | The notice's lifetime — **assumed** | Shown above the list until the list remounts or another jump starts | The issue says when it appears, not when it goes. A timer would be a second clock to test |
| 23 | Box placement — **assumed** | First child of the sidebar `<aside>`, above `WorkspaceSwitcher` | R1 "at the top of the sidebar", read literally |
| 24 | A result row | A react-router `<Link>` (an anchor), so middle-click and the reload path work | Alternative: a button calling `navigate`, which loses both |
| 25 | The register | No new entry. D8c gets an SPA "built against it" note | The issue's *Record in this slice* |

Nothing here touches a 🔴 entry. Nearest: **D29** (no reindex) — the journey searches only words
posted in the same scenario, and stale index hits for truncated rows are dropped by Postgres
hydration; **D16** (tombstone retention) — search returns no tombstones and the jump only highlights
one already in history; **D12** (canvas search) — out; **D28** (preferences) — the date format is the
browser locale, nothing is stored.

## Corrections to the issue

- **R10: "the highlighted message carry a `data-testid`".** It already carries `message-item`; the
  highlight is `data-highlighted="true"` on that element (decision 13). The page object selects
  `[data-testid='message-item'][data-highlighted='true']`. Task 9 writes this into doc 06.
- **What it assumes** holds in TanStack 5.101.4 (decisions 7–8 cite the lines). jsdom has no
  `Element.scrollIntoView` (nothing under `jsdom/lib/jsdom/living/nodes` defines it): Task 2 stubs it.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** Search is a new capability a user sees and uses through the
SPA, and only a real stack proves the whole chain: a message posted, indexed by the Worker into
Elasticsearch, found through Messaging, and opened highlighted in its channel. Write the journey
first; everything under it goes down the pyramid, and almost all of it is Vitest.

| Behaviour | Layer | File |
|---|---|---|
| Ada posts a unique word, searches it, opens the result, lands in #general with it highlighted | **BDD** | `tests/bdd/features/search.feature` |
| The jump's step rule: wait / found / fetch / give up / failed, both sides of the cap | Vitest (pure) | `features/channels/jump.test.ts` |
| `refetchHistory` waits for a page fetch, keeps its page, then refetches; a plain refetch still invalidates | Vitest (hook) | `features/channels/useMessages.test.ts` |
| The join ack's refetch no longer cancels a page fetch | Vitest (hook) | `lib/realtime/useChannelSocket.test.tsx` |
| The jump in `MessageList`: loaded, paged, capped, cached pages counted, failed, tombstone, param removal, no pull, no read (fresh and open channel), badge, both *Timing* sequences, abandon, latest-wins, divider | Vitest | `features/channels/MessageList.jump.test.tsx` |
| Scroll to top during a refetch (R8 defect) | Vitest | `features/channels/MessageList.test.tsx` |
| Jump into another channel behind "Loading…" | Vitest | `features/channels/ChannelView.test.tsx` |
| The box: submit, trim, blank, 200 cap, text per route, resubmit refetches, `role="search"` | Vitest | `features/search/SearchBox.test.tsx` |
| The page: order, row, plain text, "(edited)", names and 404, Load more, empty, 503 + Retry, cached return, no live update, workspace switch, blank `q`, link target | Vitest | `features/search/SearchPage.test.tsx` |
| `/search` is a protected route inside the shell | Vitest | `App.test.tsx` |

**What no test covers:** the highlight's *fade* (a CSS transition — jsdom has none; the class
removal at 2 s is tested); centring in a real layout (the test proves `scrollIntoView({ block:
'center' })` is called on the right element, not where the browser puts it — nor an older page a
target centred near the top then loads, decision 27); the index's recall
(D29); the existing channel-404 path for a channel the user lost access to (unchanged code). The
first real run (Task 10) looks at the first two.

**Baseline**, from `docs/test-report.md` at `d4be439`: Unit 565 passed (frontend 243), Integration 381
passed, End-to-end 20 passed. Expected counts are "N or more", because a sibling branch may land first.

## Global constraints

- **TanStack Query owns all server state** (D24). Nothing about search results or the jump's pages
  goes in Zustand; `jumping` and the highlight are component state in `useMessageJump`.
- The workspace id leads every query key (`searchKeys.results(ws, q)`), so a workspace switch reads
  a different entry and no old results show (doc 06 §4).
- Bodies render as React text children — never `dangerouslySetInnerHTML`.
- Vitest queries by role, label or text; `data-testid`s are added for the BDD page object only and
  no Vitest test reads one (CLAUDE.md). `data-highlighted` and `data-message-id` are attributes, not
  testids, and tests may read them.
- No new environment variable, no chart, no compose service change, no OpenAPI regeneration:
  `/api/v1/search/messages` and `MessageListResponse` are already in `src/types/messaging.ts:297,1236`
  (checked), and `/api/v1/search` is already in the Ingress allow-list
  (`charts/collabhub/templates/ingress.yaml:57`, checked).

## File map

Paths under `src/frontend/src/` are shortened.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `features/channels/jump.test.ts` | create | the step rule | 1 |
| `features/channels/useMessages.test.ts` | modify | `refetchHistory`, `loadedPageCount` | 1 |
| `lib/realtime/useChannelSocket.test.tsx` | modify | join ack vs page fetch | 1 |
| `test/layout.ts` | modify | `stubScrollIntoView()` | 2 |
| `features/channels/MessageList.jump.test.tsx` | create | the jump | 2 |
| `features/channels/MessageList.test.tsx` | modify | R8 scroll-to-top | 2 |
| `features/channels/ChannelView.test.tsx` | modify | jump into another channel | 2 |
| `features/search/SearchBox.test.tsx` · `SearchPage.test.tsx` | create | the search UI's red | 3 |
| `App.test.tsx` | modify | the `/search` route | 3 |
| `tests/bdd/features/search.feature` · `steps/test_search_steps.py` · `pages/chat_page.py` | create · create · modify | the journey | 4 |
| `lib/api/messaging.ts` | modify | `searchMessages` | 5 |
| `features/channels/jump.ts` | create | `JUMP_PARAM`, `JUMP_PAGE_CAP`, `HIGHLIGHT_MS`, `nextJumpStep` | 5 |
| `features/channels/useMessages.ts` | modify | `loadedPageCount`, `refetchHistory` | 5 |
| `lib/realtime/useChannelSocket.ts` | modify | both join-ack invalidations (`:134`, `:202`) go through `refetchHistory` | 5 |
| `features/channels/useMessageJump.ts` | create | the jump hook | 6 |
| `features/channels/MessageList.tsx` | modify | the hook, `loadOlder`, R7 guards, R8 scroll fix, the notice | 6 |
| `features/channels/useMarkRead.ts` | modify | return `flush()` (decision 28) | 6 |
| `features/channels/MessageItem.tsx` | modify | `highlighted` prop | 6 |
| `features/search/useSearch.ts` · `useChannelNames.ts` | create | the queries | 7 |
| `features/search/SearchBox.tsx` · `SearchPage.tsx` · `SearchResult.tsx` | create | the UI | 7 |
| `features/channels/ChatLayout.tsx` · `App.tsx` | modify | box in the aside; `/search` route | 7 |
| `scripts/test.sh` | modify | delete `E2E_SCALE` (`:227-229`) and its use (`:290`) | 8 |
| `README.md:191-192`, `:206-211` · `CLAUDE.md:229-230` · `docker-compose.test.yml:85-88` | modify | stop saying the test stack scales ES and the Worker to zero | 8 |
| `docs/design/06-frontend-spa.md` · `07-open-decisions-register.md` · `docs/adr/261002-jump-to-a-search-result-by-paging-back.md` | modify · modify · create | the record | 9 |

Deliberately unchanged: `components/ProblemBanner.tsx` (decision 16); `tests/bdd/conftest.py` — its
per-scenario `TRUNCATE` leaves the index alone, and stale hits are dropped by hydration, so no index
reset is needed; `useChannels.ts` (R4 does not follow `nextCursor`, *Not in this issue*);
`src/types/messaging.ts`. **Known ripple:** `useChannelSocket.test.tsx`'s two `isInvalidated(...)`
assertions (`:143-147`, `:186-190`) seed history with no fetch in flight, so they still hold through
`refetchHistory`'s plain path — run them in Task 5. `MessageList.test.tsx`'s scroll tests call
`fireEvent.scroll` at `scrollTop` 0 with nothing fetching, so the new `isFetching` guard leaves them
green.

Sibling branches: `caw-issue-3` on `feature/issue-3`, at the same base `950e66a` and not yet
diverged; the `issue-1-*` worktrees are tuning runs of issue 1, already in `main` (`08fd0af`).
Task 10 merges `main` again if issue 3 lands meanwhile.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing Vitest tests for the rule, the jump, R8 and the search UI; the journey written and parsing — **test-reviewer gate** |
| GREEN — history | 5–6 | code-writer | Tasks 1–2 pass |
| GREEN — search | 7 | code-writer | Task 3 passes; `tsc` clean |
| Finish | 8–10 | code-writer | e2e harness, the record, verification and the journey's first run |

One RED phase: every stub types against `src/types/messaging.ts` today. The journey's red is that
it parses and binds; it runs first in Task 10.

---

## Task 1: The step rule and the refetch helper (RED)

**Files:** `features/channels/jump.test.ts` (create), `features/channels/useMessages.test.ts`,
`lib/realtime/useChannelSocket.test.tsx` (modify)

**Interfaces** — produced for Task 5, in `features/channels/jump.ts`:

```ts
export const JUMP_PARAM = 'message'
export const JUMP_PAGE_CAP = 10
export const HIGHLIGHT_MS = 2000
export type JumpStep = 'wait' | 'found' | 'fetch' | 'give-up' | 'failed'
export function nextJumpStep(input: {
  target: string
  messages: readonly Message[]
  loadedPages: number
  hasNextPage: boolean
  fetching: boolean   // history isFetching — any fetch
  failed: boolean     // history isError
}): JumpStep
// precedence: failed → 'failed'; fetching → 'wait'; target loaded → 'found';
// loadedPages >= JUMP_PAGE_CAP → 'give-up'; hasNextPage → 'fetch'; else 'give-up'
```

and in `features/channels/useMessages.ts`:

```ts
export function loadedPageCount(queryClient: QueryClient, key: readonly unknown[]): number  // 0 if uncached
export function refetchHistory(queryClient: QueryClient, key: readonly unknown[]): void
```

| Test | File | Proves | Expected red |
|---|---|---|---|
| `fetches while under the cap and more history exists` | jump.test | `fetch` at 9 loaded pages | `Failed to resolve import "./jump"` (every test in the file needs it) |
| `gives up at ten loaded pages without the target` | jump.test | the cap is inclusive: 10 → `give-up`, 9 → `fetch`, in one test | same |
| `finds a target on the tenth page` | jump.test | `found` beats the cap at 10 | same |
| `waits while history is fetching, even with the target loaded` | jump.test | `wait` beats `found`; flipped to `fetching: false` → `found` | same |
| `fails on a failed fetch before anything else` | jump.test | `failed` beats `wait` and `found` | same |
| `gives up when history is exhausted under the cap` | jump.test | decision 21: `hasNextPage: false`, 3 pages → `give-up` | same |
| `finds a tombstone` | jump.test | a target with `deletedAt` set → `found` | same |
| `counts loaded pages, and none for an uncached key` | useMessages.test | `loadedPageCount` → 3 for a seeded 3-page entry, 0 for none | `TypeError: loadedPageCount is not a function` |
| `refetchHistory waits for a page fetch, keeps its page, then refetches` | useMessages.test | `useMessages` rendered with a page-2 response held; `refetchHistory`; no `cursor=null` request while held; release → 2 pages cached, then a refetch requests `null` then the page-2 cursor | `TypeError: refetchHistory is not a function` |
| `refetchHistory invalidates at once when no page fetch is in flight` | useMessages.test | seeded, idle → `isInvalidated` true and, with an observer, one refetch | same |
| `keeps a page fetched while the join is acknowledged` | useChannelSocket.test | `useMessages` + the socket; page 2 held; `holdJoins(...).reply({ ok: true })`; release → `pages.length` 2, and a refetch follows | `expected 1 to be 2` — today's `invalidateQueries` cancels the page fetch and refetches page 1 alone |

Build history with `aMessagePage()` and `messageIdAt(n)` ids. Hold a response with the
`deferred()` pattern `ChannelView.test.tsx:72-78` uses, inside the MSW stub.

## Task 2: The jump and the R8 defect (RED)

**Files:** `test/layout.ts` (add `stubScrollIntoView`), `features/channels/MessageList.jump.test.tsx`
(create), `features/channels/MessageList.test.tsx`, `features/channels/ChannelView.test.tsx` (modify)

**Interfaces** — produced for Task 6:

```ts
// features/channels/useMessageJump.ts
export interface JumpHistory {
  messages: readonly Message[]
  loadedPages: number
  hasNextPage: boolean
  isFetching: boolean
  isError: boolean
  isSuccess: boolean
  loadOlder: () => void       // MessageList's: heightBeforePrepend, then fetchNextPage({ cancelRefetch: false }),
}                             // only when hasNextPage and the query is idle now (decision 27)
export interface Jump {
  jumping: boolean            // seeking or highlighting: reads and auto-scroll held off
  highlightedId: string | null
  tooFarBack: boolean         // the notice
}
export function useMessageJump(
  history: JumpHistory,
  scroller: RefObject<HTMLElement | null>,
  onScrolled: () => void,     // MessageList re-measures atBottom
): Jump
// useMarkRead(...) returns { request, connected, flush: () => void }  — flushes this channel's held read
// MessageItem gains `highlighted?: boolean` → <article data-highlighted="true"> and bg-accent/15
// The notice: <p role="status" data-testid="jump-notice">That message is too far back to show.</p>,
// rendered above the scroller (MessageList returns a fragment; ChannelView's parent is a flex column)
```

On `found`: `element.scrollIntoView({ block: 'center' })` on `scroller.current.querySelector(
'[data-message-id="<id>"]')`, `highlightedId` set, param removed (`replace`), a `HIGHLIGHT_MS` timer,
then `highlightedId` null and `jumping` false. On `give-up`: `scroller.scrollTop = scrollHeight`,
`onScrolled()`, `tooFarBack` true, param removed, `jumping` false. On `failed`: param removed,
`jumping` false, no scroll, no notice. On `fetch`: `loadOlder()`.
Cleanup on unmount cancels the timer and anything pending.

`stubScrollIntoView(): Mock` defines `HTMLElement.prototype.scrollIntoView` as a `vi.fn()` and deletes
it at `onTestFinished`, like `layoutEveryElement`.

**`MessageList.jump.test.tsx`** renders `MessageList` with `route: '/c/channel-general?message=<id>'`,
`path: '/c/:channelId'`, a connected `FakeSocket` acking `mark_read` (as
`MessageList.reading.test.tsx:55-60`), and a paged stub: pages of 2 messages, `cursor` `p2`…`p12`,
ids `messageIdAt(n)`. A test that navigates renders a tiny `useNavigate` button beside the list.

| Test | Proves | Expected red |
|---|---|---|
| `jumps to a message already loaded: centres it, highlights it, removes the param` | R7 found in loaded pages; `scrollIntoView` called once with `{ block: 'center' }` on that article; `data-highlighted="true"`; `location().search` is `''` | spy never called — nothing jumps today |
| `pages back until it finds the message` | `layoutEveryElement` (not frozen), target on page 3, page 2 held: while held `scrollTop === scrollHeight` — the fresh list opened at its newest (decision 26; a build that blocks every scroll while jumping leaves 0); release → cursors `[null, 'p2', 'p3']`, then found | only `[null]` requested |
| `counts pages cached before the jump towards the ten` | seed pages 1–4 in the cache (`pageParams` `[undefined, 'p2', 'p3', 'p4']`, last `nextCursor` `p5`); target on page 11 → the mount refetch asks `null, p2, p3, p4`, the jump `p5`…`p10`; **no `p11`**; the notice. A build counting only its own fetches asks `p11`–`p14` | no status element |
| `stops at ten loaded pages with the notice` | target on page 11 → no `p11` request; `role="status"` "That message is too far back to show."; `scrollTop === scrollHeight` (`layoutEveryElement`, not frozen); param removed; no highlight | no status element |
| `ends on a failed fetch with the list's own error` | page 2 → 503; the existing `role="alert"` shows; param removed; no notice; spy not called | param still present |
| `highlights a tombstone` | target with `deletedAt` set on page 2 → `data-highlighted` on its article | no attribute |
| `fades the highlight after two seconds` | fake `setTimeout`/`clearTimeout` only, from the start; flush with a bounded loop of `advanceTimersByTimeAsync(0)` — never `vi.waitFor` — so found lands at fake t=0; at +1999 still highlighted, at +1 more not | no attribute at +0 |
| `holds reads and the badge off during the jump, then reads once it ends` | attention true, `BOTTOM` layout, target on page 1: no `mark_read` and `readingChannelId` null while highlighted (checked after a settle); after the fade (fake time as above) `mark_read` for the newest id and `readingChannelId` the channel | `mark_read` sent at once |
| `does not pull to the bottom when a message arrives mid-jump` | page 2 held; `upsertMessage` a new message; `scrollTop` unchanged (`giveLayout` at bottom, not frozen); then release and found | `scrollTop` set to `scrollHeight` |
| `waits for a refetch already in flight, then pages back (Timing 1)` | page 1 (target absent) **seeded in the cache**, target on page 3; mount with the param — the mount refetch is in flight from the first render (cached data, `staleTime` 0: `queryObserver.ts:461-474` reports `fetching` optimistically), its response held and carrying a new newest message. While held: no `p2` request. Release → the new message shows, then `p2`, `p3`, found. A build that looks while fetching and pages with the default `cancelRefetch` asks `p2` while held | the final cursor assertion fails on `[null]` — nothing pages back today (the "none while held" half passes at red; it is the half the wrong build above fails) |
| `holds reads off when a jump starts on the open channel, after flushing a held read` | fake `setTimeout`/`clearTimeout`; mount **without** the param, attention true, at the bottom: `mark_read` for the newest sent; `upsertMessage` a newer one → its read is held by the throttle. Navigate to `?message=<page-2 id>` with page 2 held → the held read is sent at once (no time advanced) and `readingChannelId` null; upsert another message → no `mark_read`, `scrollTop` unchanged (`giveLayout` at the bottom, `scrollTop` = `scrollHeight − clientHeight`, so a pull writes a different value); release → found; +2000 → `mark_read` for the newest (decisions 11, 28) | `mark_read` sent 1 time where 2 are expected — the held read waits for its window today |
| `keeps a page fetched across a reconnect, then looks again (Timing 2)` | target on page 4; page 3 held; `refetchHistory`; no `null` request while held; release → 3 pages kept, refetch requests `null, p2, p3`; then `p4` and found | times out waiting for the `p3` request the arrangement holds — nothing pages back today |
| `abandons the jump when the list unmounts` | target on page 3; page 2 held; `unmount()`; release → spy not called, no status; page 2 is cached (`loadedPageCount` 2) and no `p3` request follows | times out waiting for the `p2` request the arrangement holds |
| `abandons the jump when the param is removed by navigation` | target on page 3; page 2 held; navigate to `/c/channel-general` (no param); release → spy not called, no notice, no `p3` request | same |
| `follows only the latest target` | seeking A (page 3), page 2 held; navigate to `?message=B` (B on page 2); release → spy called only for B's article; A never highlighted, no `p3` request | same |
| `shows the divider and the highlight together` | `lastReadId` on page 2, target on page 3 → `role="separator"` "New messages" and the highlight both present | no highlight |

**`MessageList.test.tsx`**, added:

| Test | Proves | Expected red |
|---|---|---|
| `lets a refetch finish when the top is reached during it, then loads the older page` | history loaded; `invalidateQueries` with the refetch held (its page 1 carries a new newest message); scroll at top → no `cursor=older` request while held; `giveLayout` again 100 px taller (the new message), then release → `scrollTop` still 0, where a stale `heightBeforePrepend` would add 100; the new message shows, then `older` is requested (its response held, so the check comes before any real prepend) | an `older` request is made while held, and the refetch's new message never shows |

**`ChannelView.test.tsx`**, added in a `describe('ChannelView — jumping to a message')`:

| Test | Proves | Expected red |
|---|---|---|
| `starts a jump into another channel once its history arrives` | on `#general`, navigate to `/c/channel-random?message=<random 2>` with `gate.detail` held: "Loading…" shows, spy not called; release → highlighted in `#random` | spy never called |

## Task 3: The search UI (RED)

**Files:** `features/search/SearchBox.test.tsx`, `features/search/SearchPage.test.tsx` (create),
`App.test.tsx` (modify)

**Interfaces** — produced for Task 7:

```ts
// lib/api/messaging.ts
export async function searchMessages(accessToken: string, q: string, cursor?: string): Promise<MessagePage>
// features/search/useSearch.ts
export const searchKeys = { results: (workspaceId: string | null, q: string) => ['search', workspaceId, q] as const }
export function useSearch(accessToken: string, workspaceId: string | null, q: string)  // select: pages flattened in served order
// features/search/useChannelNames.ts
export function useChannelNames(accessToken: string, workspaceId: string | null,
  channelIds: readonly string[]): (channelId: string) => string | null
// features/search/SearchBox.tsx    export function SearchBox({ workspaceId }: { workspaceId: string | null })
// features/search/SearchPage.tsx   export function SearchPage({ accessToken, workspaceId }: { accessToken: string; workspaceId: string | null })
// features/search/SearchResult.tsx export function SearchResult({ message, channelName, authorName }:
//   { message: Message; channelName: string | null; authorName: string })
```

Markup the tests query, and the testids the page object uses:

| Element | Role / name | testid |
|---|---|---|
| `<form role="search" aria-label="Search messages">` with `<input type="search" aria-label="Search messages" maxLength={200}>` | `search` / `searchbox`, both "Search messages" | `search-box` (the input) |
| `<ul aria-label="Search results">`, one `<li>` per result holding a `<Link to="/c/<channelId>?message=<id>">` | `list` "Search results", `listitem`, `link` | `search-result` on the link, with `data-message-id` |
| Channel name `#general` (or `#…`), author, `<time dateTime>`, body `<p>`, `(edited)` | text | — |
| `<button>Load more</button>` | `button` "Load more" | `search-load-more` |
| `<p role="status">No messages match "x".</p>` | `status` | `search-empty` |
| `ProblemBanner` (`role="alert"`) + `<button>Retry</button>` | `alert`, `button` "Retry" | (`problem-banner`, existing) |

`searchMessages`, `useSearch`, `useChannelNames` and `SearchResult` are tested through
`SearchPage`, which is the boundary a user meets; the tests below name each one's behaviour.

The box remounts on `key={pathname === '/search' ? 'search:' + q : 'other'}` with `defaultValue`,
so its text follows the route without an effect.

**`SearchBox.test.tsx`** — `SearchBox` rendered with `route` set, and `SearchPage` beside it where a
test needs results:

| Test | Proves | Expected red |
|---|---|---|
| `submits the trimmed text to /search` (`it.each` over `/` and `/c/channel-general`) | `"  zeppelin  "` + Enter → `location()` `/search`, `q=zeppelin` — the same from both routes | `Failed to resolve import "./SearchBox"` (all tests in the file) |
| `submits nothing for a blank box, and does once there is text` | `"   "` + Enter → location unchanged; then `"x"` + Enter → `/search?q=x` | same |
| `takes at most 200 characters` | typing 201 → value length 200 | same |
| `shows the query on /search and nothing elsewhere` | at `/search?q=zeppelin` value `zeppelin`; after navigating to `/c/channel-general` value `''` | same |
| `refetches when the same query is submitted again` | on `/search?q=x` with `SearchPage`: Enter again → search requests 1 → 2; `location()` unchanged | same |
| `sits inside a named search landmark` | `getByRole('search', { name: 'Search messages' })` contains `getByRole('searchbox', { name: 'Search messages' })` | same |

**`SearchPage.test.tsx`** — `SearchPage` at `route: '/search?q=zeppelin'`, `path: '/search'`;
`messaging.get('/api/v1/search/messages', …)`, `messaging.get('/api/v1/channels', …)`,
`auth.members([...])`:

| Test | Proves | Expected red |
|---|---|---|
| `lists results in the order served, newest first` | `[newer, older]` served → rows in that order (a reversing build fails) | `Failed to resolve import "./SearchPage"` (all tests) |
| `shows channel, author, date and time, and the body as plain text` | `#general`, "Ada Lovelace", `<time dateTime={createdAt}>`, body `<b>bold</b>` shown as literal text with no `b` element and no `mark` | same |
| `marks an edited result, and only that one` | two rows, one with `editedAt` → one "(edited)" | same |
| `names a channel outside the list from its detail, fetched once` | two results in `design`, absent from the list; detail held → both rows `#…`; one detail request; release → `#design` | same |
| `leaves the row as it is when the channel's detail is a 404` | `#…` stays; the other row's name still shows | same |
| `does not fetch a detail for a channel in the list` | no `/api/v1/channels/{id}` request after the list settles | same |
| `loads more after a short page until nextCursor is null` | page 1: 1 item, `nextCursor: 'c2'` → "Load more"; click → `cursor=c2` requested, page 2 appended below; `nextCursor: null` → button gone | same |
| `says nothing matches, with no caveat` | empty page → `status` text exactly `No messages match "zeppelin".` | same |
| `says search is unavailable on a 503, and Retry fetches again` | `problem(… 503, { detail: 'Search is unavailable.' })` → `alert` with that text and "Retry"; re-stub results, click → results, alert gone | same |
| `keeps the list and offers Load more again when a later page fails` | page 2 → 503: rows still shown, alert shown, "Load more" present, no "Retry" | same |
| `shows the cached list at once on return, then refetches` | unmount, remount with the same `QueryClient` and the second response held → old rows present before release, 2 requests; release → new rows | same |
| `does not update a list on screen on focus or reconnect` | `setPageAttention` hidden → visible, focus; then `onlineManager.setOnline(false)` → `true`; settle → still 1 request; then a remount → 2 (the positive: the count would move) | same |
| `searches the new workspace on a switch and shows nothing from the old one` | `rerender` with workspace B and token B, B's response held → A's rows gone at once; the request carried `Bearer` B (read in the stub); release → B's rows | same |
| `fetches nothing for a blank query` | `/search?q=%20%20` → the prompt text, 0 search requests | same |
| `links each result to its message in its channel` | the row's `link` → `href` `/c/<channelId>?message=<id>`; click → `location()` matches | same |

**`App.test.tsx`**, added: `shows search results on /search for a signed-in user` — `aReturningUser()`,
route `/search?q=zeppelin`, search stub → the result's body shows inside the shell (the sidebar's
`search` landmark present). Expected red: "No such page." — no route.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/search.feature` (create), `tests/bdd/steps/test_search_steps.py`
(create, the only module calling `scenarios()` on it), `tests/bdd/pages/chat_page.py` (modify)

```gherkin
@bdd
Feature: Search

  Ada can find something said in any channel she can see by searching for its
  words, and open it where it was said — scrolled to and highlighted, in the
  middle of the conversation around it.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: posted, indexed by the Worker, found
  # through Messaging, opened in place. Rows, paging, the jump's cap and its
  # races are proven in Vitest.
  Scenario: Ada finds a message and opens it in its channel
    Given Ada has created a public channel named "general"
    And Ada has sent "the zeppelin lands at dawn" in "general"
    When Ada searches for "zeppelin"
    Then Ada sees "the zeppelin lands at dawn" in the search results
    When Ada opens the search result "the zeppelin lands at dawn"
    Then Ada sees "the zeppelin lands at dawn" highlighted
    And Ada is looking at the "general" channel
```

- The Background, `has created…`, `has sent…` and `is looking at…` are reused verbatim from
  `steps/conftest.py`; the four search phrases are new, in `test_search_steps.py`.
- "zeppelin" is in no other feature; a stale index hit's id is gone from Postgres and hydration drops
  it. The highlight check precedes "looking at" because it holds for 2 s only.
- Page object, selectors only there: `search(q)` fills `search-box`, presses Enter, and — because
  indexing is asynchronous (D29) — waits for a `search-result` or `search-empty`; on `search-empty`
  it presses Enter again (R1: a resubmit refetches), up to 10 seconds. The retry is inside the act,
  so no `Then` performs an action (vocabulary §16). `has_search_result(body)` retries via `expect`;
  `open_search_result(body)` clicks the `search-result` filtered by text;
  `has_highlighted(body)` expects `[data-testid='message-item'][data-highlighted='true']` filtered
  by text to be visible.
- Expected red, before the code-writer: `uv run pytest tests/bdd --collect-only -q` collects the
  scenario; `--generate-missing` prints nothing. At the first e2e run without the code, `search()`
  times out waiting for `search-box`.

## Task 5: The API wrapper, the rule and the refetch helper (GREEN)

**Files:** `lib/api/messaging.ts`, `features/channels/jump.ts`, `features/channels/useMessages.ts`,
`lib/realtime/useChannelSocket.ts`

- [ ] `searchMessages` beside `listMessages`, same shape: `client.GET('/api/v1/search/messages',
  { params: { query: cursor ? { q, cursor } : { q } } })`, `throw problem(...)` on error.
- [ ] `jump.ts` to Task 1's interface.
- [ ] `loadedPageCount` and `refetchHistory` in `useMessages.ts`. `refetchHistory`:

```ts
// A page fetch in flight is never cancelled: wait for it, then refetch everything loaded.
const query = queryClient.getQueryCache().find({ queryKey: key, exact: true })
const pageInFlight =
  query?.state.fetchStatus === 'fetching' && query.state.fetchMeta?.fetchMore?.direction === 'forward'
if (!pageInFlight) { void queryClient.invalidateQueries({ queryKey: key, exact: true }); return }
// subscribe as reapplyAfterFetch does; on fetchStatus 'idle', unsubscribe and call refetchHistory again
```

- [ ] `useChannelSocket.ts:134` and `:202`: `refetchHistory(queryClient, messageKeys.list(...))` in
  place of `invalidateQueries`. Update the file's docstring paragraph on join refetches.
- [ ] Task 1 passes; `useChannelSocket.test.tsx` whole file passes (the ripple). Leave uncommitted.

## Task 6: The jump in the list (GREEN)

**Files:** `features/channels/useMessageJump.ts` (create), `MessageList.tsx`, `MessageItem.tsx`

- [ ] `useMessageJump` to Task 2's interface. State: `target` (initialised from `?message=`),
  `phase: 'seeking' | 'highlighting' | 'idle'`, `highlightedId`, `tooFarBack`, `seenParam`.
  `jumping = phase !== 'idle'`. **During render**, when the param differs from `seenParam`: set
  `seenParam`, and a new id restarts (`target`, `phase: 'seeking'`, `tooFarBack` false; the effect
  cleanup clears the old timer) while a param gone during `seeking` abandons (decision 11). Run
  `nextJumpStep` in an effect on every history change while `seeking`; guard `fetch` with an
  in-flight ref so one step issues one call.
- [ ] `MessageList`: `loadOlder()` per decision 27, used by `onScroll` and passed to the hook;
  `loadedPages` from `loadedPageCount(useQueryClient(), messageKeys.list(...))`;
  `beingRead = attending && atBottom && !jump.jumping`; an effect calls `flush()` when
  `jump.jumping` turns true (decision 28); the layout effect's growth branch scrolls when
  `grew && wasAtBottom && (!jump.jumping || previousCount === 0)` (decision 26); `onScrolled` =
  `setAtBottom(measure(el))`; render the notice above the scroller; pass
  `highlighted={message.id === jump.highlightedId}`.
- [ ] `useMarkRead`: return `flush: () => throttle.current?.flush(channelId)`, memoised like `request`.
- [ ] R8 in `onScroll`: at the top, `loadOlder()`; when it declines because a refetch is running
  (fetching and not `isFetchingNextPage`), set `olderWanted.current = true` and nothing else. An
  effect on `isFetching` turning false: if `olderWanted`, clear it, and if still within
  `LOAD_THRESHOLD`, `loadOlder()`. Extend the file's docstring with a third paragraph: who may
  cancel whom.
- [ ] `MessageItem`: `highlighted` → `data-highlighted={highlighted ? 'true' : undefined}`,
  `transition-colors duration-700` always, `bg-accent/15` while highlighted.
- [ ] Task 2 passes; the rest of `features/channels` passes unchanged. Leave uncommitted.

## Task 7: The search UI (GREEN)

**Files:** `features/search/*` (create), `ChatLayout.tsx`, `App.tsx`

- [ ] `useSearch`: `useInfiniteQuery` on `searchKeys.results(ws, q)`, `getNextPageParam: last =>
  last.nextCursor ?? undefined` (a short page with a cursor still has a next page, R5), `select`
  flattening pages **without** reversing, options per decision 17.
- [ ] `useChannelNames` per decision 20: names from `useChannels(...).data`; once that query is
  settled (`isSuccess || isError`), `useQueries` for the distinct ids not in it; a pending or failed
  detail reads `null` (rendered `#…`).
- [ ] `SearchResult`, `SearchPage` (trim `q` from `useSearchParams`; the prompt for blank; "Searching…"
  while pending; markup per Task 3's table; author via `useWorkspaceMembers(...).nameFor`).
- [ ] `SearchBox`: on submit, trim; blank → nothing; else `invalidateQueries(searchKeys.results(ws,
  q))`, then `navigate('/search?q=' + encodeURIComponent(q))` only if that differs from the current
  location (decision 19).
- [ ] `ChatLayout`: `<SearchBox workspaceId={current.activeWorkspaceId} />` first in the `<aside>`.
  `App`: `<Route path="/search">` inside `Protected`, a `SearchRoute` like `ChannelRoute`.
- [ ] Task 3 passes; `npm --prefix src/frontend run typecheck` clean. Leave uncommitted.

## Task 8: The e2e harness

**Files:** `scripts/test.sh`, `README.md`, `CLAUDE.md`, `docker-compose.test.yml`

- [ ] `scripts/test.sh`: delete lines 227–229 (the comment and `E2E_SCALE=`) and the
  `"${E2E_SCALE[@]}"` argument at 290. Elasticsearch and the Worker now start with the test stack;
  `--wait` already waits on both healthchecks (`docker-compose.yml:109-114`, the Worker's
  `*http-healthcheck`).
- [ ] `README.md:191-192`: drop `--scale elasticsearch=0 --scale worker=0` from the by-hand recipe.
  `README.md:206-211`, `CLAUDE.md:229-230`: say the test stack runs Elasticsearch and the Worker,
  because the search journey needs both. `docker-compose.test.yml:85-88`: the comment says the suite
  touches none of the unpublished services — the Worker and Elasticsearch are now reached, over the
  Compose network.
- [ ] Leave uncommitted.

## Task 9: The record

- [ ] `docs/design/06-frontend-spa.md`: a new **§5.4 Search — added 2026-10-02** — the box and its
  route behaviour, the results route and its cache key, the row, Load more, channel names, the jump
  (decide only while idle, `cancelRefetch: false`, `refetchHistory`, cap 10 loaded pages, 2 s
  highlight via `data-highlighted`, the notice, param removal, abandon and latest-wins) and its
  exception to the read rule. §4's line on unified search (`:141-142`): search is one workspace, the
  token's; cross-workspace search still needs an aggregate endpoint. §5.2's "Every connect re-joins
  *and* refetches" bullet: the refetch now waits for an in-flight page fetch.
- [ ] Register D8c: append "**Built against it 2026-10-02 (SPA):** the search box, `/search` and the
  jump consume `GET /api/v1/search/messages` unchanged; the jump pages history back on the client
  (doc 06 §5.4)."
- [ ] ADR with the `adr-writer` skill, `docs/adr/261002-jump-to-a-search-result-by-paging-back.md`:
  paging back up to 10 pages, over an `around` param on history and a two-way cache; revisit when the
  cap is hit often.
- [ ] Sweep: `git grep -n -i -e E2E_SCALE -e "scale elasticsearch" -e "scale worker" -- . ':!docs/plans'`
  returns nothing; `grep -rn "unified search" docs/design` matches the new wording.

## Task 10: Verification

- [ ] `scripts/test.sh lint unit`, then `scripts/test.sh e2e` — the whole layer once: the journey's
  first run, and every existing journey against a stack that now runs Elasticsearch and the Worker.
  No `integration`: no service Python, SQL or stream changes. Counts at or above the baseline: Unit
  565 + the new Vitest tests, End-to-end 21. `-- -k search` only for iterating on a failure.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`.
- [ ] **First real run**, on the Compose stack (`docker compose up -d --build`), with words posted
  after it is up (D29):
  1. Ada searches a word ~3 pages back in a channel with unread messages: opens centred and
     highlighted, the badge stays until she scrolls to the bottom.
  2. Back: the results are there, then refreshed.
  3. A result more than 10 pages back: the notice.
  4. Grace deletes a listed message; Ada clicks it: the tombstone is highlighted.
  5. `docker compose stop elasticsearch`: "Search is unavailable."; start it, Retry: results.
  6. Ada switches workspace on `/search`: the search runs in the new workspace.

  Expect this run to find something the tests didn't. Fix it with a test, and record it below.
- [ ] If a sibling branch merged while this was in flight, merge `main` and rerun all of the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Code-writer, round 1:

- **No in-flight ref in `useMessageJump`.** Task 6 asked for a ref so one step issues one call. `loadOlder` already declines unless the cache says nothing is fetching *now* (decision 27), which gives the same guarantee and also covers plan-reviewer-2 C (a declined call leaves nothing stuck). Pinned by `MessageList.jump.test.tsx` (every paging test). 
- **`onScrolled` also updates `wasAtBottom`**, not only `atBottom` state, so a give-up's scroll to the newest leaves the next arrival free to follow. No test of its own.
- **`historyKey` is memoised** in `MessageList` so `loadOlder` (a dependency of the jump's effect) is stable; no lint suppression needed.
- **Sweep (Task 9):** `docs/issues/002.md` and the accepted ADR `260815-pytest-bdd-and-playwright-for-acceptance-tests.md` still say the test stack scales ES/Worker to zero; the issue is the spec and the ADR is a dated record of what was true then, so both are left (plan-reviewer-2 B).
- **Doc 06 §5.4 sits before §5.3 in the file** (inserted ahead of the Canvas heading); numbering is correct, order is not. Cosmetic.
- **The e2e stack shared one database across worktrees.** `scripts/test.sh` now gives each worktree its own Compose project and starts every run from empty volumes (human answer); that cleared the unhealthy Messaging. No test pins the script change. `scripts/test.sh` also prints the tail of the Worker's and Messaging's logs when an e2e run fails, before the teardown deletes them (small, kept).
- **The search journey's 503 was the host's full disk**, not the code: Elasticsearch went read-only past its flood-stage watermark. With space freed and Docker restarted, all 21 scenarios pass, the journey included. The diagnostic warning log added to `messaging/search.py` was removed again; Messaging is unchanged.
- **First real run (Task 10): not done** — a person's, listed in the green report.

## Not in this plan

Everything in the issue's *Not in this issue*, unchanged.

## Self-review

- **Requirements:** R1–R6 → Tasks 3, 7; R7 → 1, 2, 5, 6 (every clause, incl. cached pages counted
  and no read on the open channel); R8 → 1, 2, 5, 6; R9 → 2, 6; R10 → 3, 4, 6.
- ***Where the rules meet:*** read rule → both `holds reads…` tests; divider → `shows the divider…`;
  join-ack → Timing 1; later delete → `highlights a tombstone`; two jumps → `follows only the latest…`.
- ***Paths:*** `/` and channel → `it.each` submit; Back → cached return; reloads → mount with or
  without the param; workspace switch → its test; cached channel → `counts pages cached…`; the open
  one → `holds reads off when a jump starts on the open channel…`; another channel → ChannelView;
  reconnect → Timing 2; outside first 50 → detail test.
- **Names:** `JUMP_PARAM`, `searchKeys.results`, `refetchHistory`, `loadOlder`, `flush`,
  `data-highlighted`, and the five testids — the page object uses exactly these.
- **Writers to the same state:** history has three fetchers — mount refetch, join-ack
  `refetchHistory`, and `loadOlder` (scroll or jump, one at a time, never cancelling: 7, 27);
  `refetchHistory` never cancels a page fetch (8); a refetch cancelling a refetch loses nothing;
  socket upserts are re-applied by `reapplyAfterFetch`, unchanged. The URL param has two writers,
  the hook and navigation, told apart by phase (12). `mark_read` is held off by `jumping` (11, 28).

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** Timing 1 test reworked: page 1 seeded, the mount refetch held from the first render
   (`queryObserver.ts:461-474`); red is the cursor assertion on `[null]`; the wrong build named.
2. **Fixed.** `counts pages cached before the jump towards the ten` (4 cached, target on page 11).
3. **Fixed.** Decision 11 adopts the param during render; decision 28 (assumed) flushes a held read;
   test `holds reads off when a jump starts on the open channel, after flushing a held read`.
4. **Fixed.** Decision 26 (opens at newest, pinned in `pages back…`; prepends anchor via
   `loadOlder`); decision 27 (assumed): the scroll handler stays armed, one page fetch at a time.
5–9. **Fixed:** sibling line; `README.md:191-192`; `git grep … ':!docs/plans'`; reconnect tested and
   decision 17 says every page refetches; the R8 test grows `scrollHeight` and asserts `scrollTop` 0.
