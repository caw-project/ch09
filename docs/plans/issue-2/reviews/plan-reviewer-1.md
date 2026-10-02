# Plan review — issue 2, round 1: changes_requested

A strong plan: every library claim it leans on holds in the installed TanStack 5.101.4, the R8 design
(`cancelRefetch: false` on page fetches, `refetchHistory` waiting out an in-flight page) answers the
hardest race the issue sets, and the decision rows settle nearly everything the issue left open.
Four major findings stop approval: a Timing test with the wrong red and a fixture a correct build
fails, no test that tells "cached pages count" apart from its wrong reading, no test or start rule
for a jump into the channel already open, and an unanswered interaction between the jump and the
list's own scroll position and scroll-to-top loading.

## Expectations

Written from the issue, doc 06 §3–§5.2, doc 02 §3.1.6, the register (D8c, D16, D29, D12),
`MessageList`, `useMessages`, `ChannelView`, `useChannelSocket`, `App`, `ChatLayout`,
`ChannelList`, `useChannels`, `ProblemBanner`, the test helpers, `scripts/test.sh`, and
TanStack Query 5.101.4 / react-router 7.18.1 from the primary checkout — before the plan.

### Decisions
- E1. The box (R1): where its text lives — derived from `q` on `/search`, local while typing;
  what happens to typed-but-unsubmitted text on a route change? Is "Submitting the same `q`
  again refetches it" an explicit `refetch` (the URL doesn't change)? Is the shown `q` the
  trimmed one?
- E2. `/search` with a blank or >200 `q` in the URL (typed by hand) — fetch, 400, or nothing?
- E3. "Never updates live" (R2) — TanStack's defaults `refetchOnWindowFocus` and
  `refetchOnReconnect` would update a list on screen. Are they off? Does "refetches it" on
  return refetch every loaded page (infinite query) or only the first?
- E4. Channel name (R4): "fetched once per distinct channel" — once per results render, per
  cache lifetime, or per mount (no `staleTime`)? Which key — shared `channelKeys.detail`
  (then a cached 404 meets ChannelView on click) or its own? What happens while the channel
  list is still pending — detail fetched for every row, or wait?
- E5. Errors other than 503 (a 400 from a hand-typed URL, a network failure, a 500) — what is
  shown, with or without Retry? A 503 on "Load more" — does the list stay, and where does the
  failure show?
- E6. The date/time format and the highlight styling (left to the plan — must be named).
- E7. The jump's home — in `MessageList` (abandoned on unmount for free) or above it; how it
  reads `?message=` and survives its own removal of the param (removing it must not abandon
  the jump whose highlight is still running).
- E8. "Highlighted for 2 seconds, then the highlight fades" / "a jump ends when its highlight
  fades" — does the jump end at 2 s, or at 2 s plus a fade transition? When is the param
  removed — at found (Timing t4) or at the end?
- E9. "10 pages are loaded in total" — counted as `data.pages.length`? What does the jump do
  when history ends (`nextCursor: null`) before 10 pages without finding it — the notice, or
  something else? A message id from another channel (hand-edited URL)?
- E10. How the jump waits for the join-ack refetch (left to the plan) — how does it know one
  is coming on a fresh mount, and not wait forever when the channel is already open (no join,
  no refetch)?
- E11. How R7 holds reads off — `beingRead` gated on "no jump", so `readingChannelId` clears
  and the badge shows. A trailing read already held by the throttle when a jump starts on the
  open channel — sent during the jump or not?
- E12. "The existing error banner" (R7 failed fetch) — today a `MessageList` error replaces
  the whole list (`if (error)`); is that what the plan means, and does it still replace the
  list when a `fetchNextPage` fails with data present?
- E13. "Scrolled to the centre" — `scrollIntoView({ block: 'center' })` or computed
  `scrollTop`? jsdom implements neither layout nor `scrollIntoView`; how do tests observe it?
- E14. Retry beside `ProblemBanner` — a new prop, or a component beside it (callers of
  `ProblemBanner` if its props change).

### Conflicts
- C1. R7 "the read rule applies as usual" after the jump vs. *Where the rules meet*: the list
  is scrolled away from the bottom, so the read rule is false until the user reaches it —
  consistent, but the plan must not "restore" reading by scrolling back.
- C2. R1 "Submitting the same `q` again refetches it" vs. R2 "A list on screen never updates
  live" — a resubmit is a user act, not live; the plan should say so.
- C3. R7 "the channel shows its newest messages" at the cap vs. "it scrolls from wherever the
  list is" (Paths) and the prepend anchoring that keeps position as pages load — after 10
  pages the list is no longer at the newest; who scrolls it back?
- C4. Paths "Reload on `/c/:id?message=…` before the param is removed — the jump runs again"
  vs. Timing (param removed at t4, jump ends at t4+2s) — a reload between t4 and t4+2s has no
  jump. Consistent if the param goes at t4; the plan must pick one moment.
- C5. R8 (a refetch never loses a page; never cancelled) vs. the library: a successful
  `fetchNextPage` clears `isInvalidated`, so an invalidation that joined an in-flight page
  fetch is lost — Timing 2 requires the refetch to run *after* page 3.

### Tests
- T1. Every R1 clause: trim, blank/whitespace submits nothing, 200 cap, box text per route
  (`/search`, `/`, `/c/x`), resubmit of the same `q` makes a second request.
- T2. R2: order kept as served (two items, not one); cached return shows at once *and* a
  second request goes out; no refetch on focus/reconnect (guard with positive).
- T3. R3: HTML in a body renders as text; "(edited)" present and absent; author fallback.
- T4. R4: list hit (no detail request), miss (one detail request for two rows of one
  channel), `#…` before it arrives, 404 leaves `#…`.
- T5. R5: a short page with a non-null cursor still shows Load more; null hides it; appended
  not replaced.
- T6. R6: empty text exact, `role="status"`; 503 text, `role="alert"`, Retry refetches and
  recovers.
- T7. R7: found in loaded pages (no extra fetch); found after paging; cap with cached pages
  counting (e.g. 3 cached + 7 fetched = 10, no 11th request); failed fetch; tombstone; param
  removed with `replace` (history length / Back target); highlight on at 1999 ms and off at
  2000+ ms; no pull to bottom on a new message mid-jump with the positive after it ends; no
  `mark_read` mid-jump *and* one after it ends; badge shown during.
- T8. Both Timing sequences with a held (deferred) response: join-ack refetch in flight →
  the jump's page fetch waits; reconnect with page 3 in flight → page 3 kept and a refetch of
  3 pages after it.
- T9. R8 defect: scroll-to-top during a refetch doesn't cancel it (the refetch's response is
  the one kept), and `heightBeforePrepend` isn't left set.
- T10. R9: channel switch, Back, unmount mid-jump — no scroll/highlight/notice later;
  latest-target-wins with the first target's page landing after the second starts.
- T11. Workspace switch on `/search` — new request with the new token, old rows gone.
- T12. One BDD journey whose last step shows server state; the 2 s highlight vs. Playwright's
  retry window; unique words; ES and worker scaled up.

### Risks
- K1. `invalidateQueries` defaults to `cancelRefetch: true` (`queryClient.ts:319`), so the
  join-ack invalidation in `useChannelSocket` cancels a jump's in-flight `fetchNextPage` and
  refetches only the pages present when it started (`infiniteQueryBehavior.ts:94`) — the
  in-flight page is lost. With `cancelRefetch: false` the invalidation joins the in-flight
  fetch and is then cleared by its success (`query.ts:736`). Which writer changes, and how?
- K2. `fetchNextPage` with `cancelRefetch: false` during a refetch returns the refetch's
  promise without fetching a page (`query.ts:414-418`) — a jump loop that counts "one more
  page" per call miscounts.
- K3. A refetch of 10 loaded pages is 10 sequential requests; a reconnect mid-jump near the
  cap amplifies load; refetched page boundaries shift if new messages arrived.
- K4. Stale closures: the jump effect sees `data` from a render; latest-target-wins needs a
  token/ref check after every await.
- K5. The jump's paging and the divider capture (`isFetching`) — capture delayed, not
  changed; and `heightBeforePrepend` for the jump's own prepends.
- K6. The cap notice / failed fetch / found all remove the param — a removal that re-runs the
  jump effect, or a stale-param re-run on remount.
- K7. Sibling branch `feature/issue-3` is at the same base — overlap unknown.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 box: Enter, trim, blank, 200, text per route, resubmit refetches | D19, D23; SearchBox tests | covered |
| R2 newest first, cached by ws+q, return shows cached and refetches, never live | D17; SearchPage tests | covered (minor 8) |
| R3 row: channel, author, date/time, plain text, "(edited)", no match highlight | D15; SearchPage tests | covered |
| R4 name from list, else detail once per channel, `#…`, 404 leaves it | D20; three tests | covered |
| R5 Load more while cursor not null; short page doesn't end it | test with 1-item page + cursor | covered |
| R6 empty text, no caveat; 503 + Retry | D16; tests | covered |
| R7 found in loaded / after paging; cap 10 "pages already cached count" | D6, jump tests | **misread in tests** — finding 2 |
| R7 centre, highlight 2 s, fade, param `replace`; not found → newest + notice | D12–14, D21–22 | covered; "newest" while seeking — finding 4 |
| R7 failed fetch ends it, existing error, no notice/retry; tombstone | tests | covered |
| R7 no pull to bottom, no read during a jump | D11; tests | covered for a fresh mount; **missing** for the open channel — finding 3 |
| R8 no fetch cancels another; no page lost | D7–D9; Task 1, Timing tests | covered; Timing 1 test flawed — finding 1 |
| R9 switch/Back/unmount abandons; latest wins | D10, D12; tests | covered |
| R10 roles, testids | Task 3 table; Correction (data-highlighted) | settled by correction |
| Where the rules meet: read rule, divider, join-ack, later delete, two jumps | tests named in Self-review | covered |
| Paths: "Jump into … the one already open … scrolls from wherever the list is" | Self-review maps to the cached-pages test, which mounts with the param | **missing** — finding 3 |
| Paths: reconnect mid-jump | Timing 2 test | covered |
| Decided already 1–10 | Decisions 1–5, 25 | covered |
| Tests section: Vitest list, one BDD journey, `E2E_SCALE` deleted, page-object 10 s retry | Tasks 1–4, 8 | covered |
| Record: doc 06 section + §4 line, D8c note, ADR | Task 9 | covered |
| Not in this issue | *Not in this plan* | covered |
| E1 box text source; resubmit | `key` remount + D19 | settled |
| E2 blank/over-long `q` in URL | D18 (blank); over-long reaches the 400 → banner + Retry (D16) | settled |
| E3 focus/reconnect refetch off | D17 | settled (reconnect untested — minor 8) |
| E4 detail fetch lifetime, key, list pending | D20 | settled |
| E5 non-503 errors; Load more failure | D16 | settled |
| E6 date format, highlight style | D14, D15 | settled |
| E7 jump's home; survives own param removal | D10, D12 | settled |
| E8 end at 2 s vs fade; param removed when | D12, D14 (class removed at 2 s; param at found) | settled |
| E9 page count; history exhausted | `loadedPageCount`; D21 | settled |
| E10 how the jump knows a refetch is coming | D6 (only one in flight) | settled — note in *Left for later stages* |
| E11 reads held off; held trailing read on the open channel | D11 for a fresh mount only | **unsettled** — finding 3 |
| E12 "existing error banner" | the list's `role="alert"` | settled |
| E13 centring in jsdom | `stubScrollIntoView` | settled |
| E14 Retry beside ProblemBanner | D16 | settled |
| C1–C2, C4 | D11, D17/D19, D12 | settled |
| C3 newest messages vs. list position during seek | D11 removes the mount's scroll to newest, unstated | **unsettled** — finding 4 |
| C5 / K1 / K2 library cancel and invalidation | D7, D8, Corrections | settled, verified |
| K3 refetch of 10 pages | accepted by the issue | settled |
| K4 latest-target-wins after awaits | D12, test | settled |
| K5 divider capture | test | settled |
| K7 sibling branch | "none for an issue after 2" | wrong — minor 5 |

## Findings

### 1. Timing 1's test has the wrong red and a fixture a correct build fails — major
**Where:** Task 2, `waits for the join-ack refetch, then pages back (Timing 1)` · **Checked:**
`useMessages.ts` (no `refetchHistory` today), `infiniteQueryBehavior.ts`, `queryObserver.ts`.
The test calls `refetchHistory` "after page 1". At red that export is `undefined`, so the test dies
with `TypeError: refetchHistory is not a function`, not "no `p2` request after release" as stated.
Worse, at green: once page 1 lands with the target absent, the jump's effect issues
`fetchNextPage` (p2) before the test can call anything, so "no `p2` request while held" fails a
correct build — `refetchHistory` then (rightly) waits for p2. Timing 1 is a refetch already in
flight *when the jump first looks*. Settle: a fixture where the refetch starts before the jump can
look — e.g. page 1 seeded in the cache and the mount refetch held (the observer reports `isFetching`
from the first render), or the join ack driven through `FakeSocket` — and the red the runtime would
really give for that arrangement.

### 2. "Pages already cached count" has no test that fails the wrong reading — major
**Where:** Task 2, `finds a message on the tenth page, cached pages included` and `stops at ten
loaded pages with the notice` · **Checked:** the two fixtures as written.
R7's clause is that cached pages count towards the 10. The cached-pages test (4 seeded, target on
page 10) is found at page 10 by a build that counts only the jump's own fetches too — it never
reaches its cap. The cap test has no cached pages, so both readings stop at 10. A build that counts
`fetchNextPage` calls would request p11–p14 and pass both. Settle: a test with pages cached before
the jump *and* the target beyond page 10 (e.g. 4 cached, target on page 11 → no `p11` request, the
notice). Two readings, two outcomes.

### 3. A jump into the channel already open: no start rule for reads, no test — major
**Where:** Decision 11, Task 6 bullet 1, Self-review *Paths* · **Checked:** `MessageList.tsx:124-137`,
`ChannelView.tsx:85` (no remount on a param change), issue *Paths* row 7 and *What this assumes*.
`jumping` is set from a `useState` initialiser — only at mount. On the open channel the list is
already mounted (often at the bottom, being read); `?message=` arriving is "a param change", handled
in an effect, so the render in which it arrives has `jumping` false: `beingRead` stays true, and the
auto-scroll and read request run for that render — the very "at the bottom for a moment" the
decision exists to avoid. A trailing read already held by the throttle when the jump starts is also
unanswered (E11). The Self-review maps this path to the cached-pages test, which mounts *with* the
param. Settle: say how `jumping` is true in the first render the param is present on a mounted
list, what happens to a held read, and a test that mounts at the bottom without the param, adds it,
and proves no `mark_read` until the jump ends (and one after).

### 4. Where the list sits while seeking, and the scroll handler during a jump — major
**Where:** Decision 11 ("the auto-scroll … also requires `!jumping`"), Task 6 bullet 3 · **Checked:**
`MessageList.tsx:139-175`; issue *Where the rules meet* ("a jump opens a channel at its newest
messages before scrolling away") and *Paths* ("scrolls from wherever the list is").
The guard also removes a fresh mount's own scroll to the newest message (that is the same
`grew && wasAtBottom` branch), so a jumped-into channel sits at `scrollTop` 0 — the oldest loaded
page — for the whole seek; that departs from the issue's description and isn't stated. And at the
top, `onScroll`'s load is armed during the jump: a user scroll, or `scrollIntoView` landing a target
from page 9–10 within `LOAD_THRESHOLD` of the top, fetches pages the jump didn't ask for — past the
cap in the browser, invisible in jsdom where `scrollIntoView` is a stub. Settle in a decision row:
where a fresh list sits while seeking (newest, as the issue says, or top, with why), whether the
scroll handler loads older pages while `jumping`, and the jump's own prepends and
`heightBeforePrepend` for a list that is not at the top (the open-channel path).

### 5. The sibling-branch line is wrong — minor
**Where:** File map, "Sibling branches" · **Checked:** `git worktree list` — `caw-issue-3` on
`feature/issue-3` at `950e66a`. Not yet diverged; Task 10's merge covers it. Correct the line.

### 6. README's by-hand command isn't in the file map — minor
**Where:** Task 8 · **Checked:** `README.md:191-192` has `--scale elasticsearch=0 --scale worker=0`
in the manual recipe, beside the `:206-211` the map names. Task 9's sweep would find it; name it.

### 7. The sweep's `--exclude-dir=docs/plans` excludes nothing — minor
**Where:** Task 9 · `grep --exclude-dir` matches a directory's base name, so `docs/plans` never
matches. Use `--exclude-dir=plans` or a pathspec with `git grep`.

### 8. R2 details unpinned — minor
**Where:** Decision 17 · `refetchOnReconnect: false` has no test; and on return an infinite query
refetches every loaded "Load more" page (`infiniteQueryBehavior.ts:94-107`) — say that is the
intended "refetches it".

### 9. The R8 defect's `heightBeforePrepend` half has no assertion — minor
**Where:** Task 2, `MessageList.test.tsx` addition · The issue names two harms; the test proves
the cancel only. An assertion that `scrollTop` is untouched when the refetch's (same-height or
taller) response lands would pin the second.

## Left for later stages

- **Decision 6 vs. Timing 1 (accepted):** the jump waits only for a refetch already in flight; a
  join ack arriving after the jump has started waits for the jump's page instead
  (`refetchHistory`), and the jump may find and highlight before the refetch lands. Harmless —
  the refetch keeps every page and the highlight is by id — and consistent with R8.
- **Pre-existing, out of scope:** on an uncached channel, a join ack arriving while the *first*
  history load is in flight joins that load (`query.ts:411` cancels only when data exists), and its
  success clears `isInvalidated`, so the join-ack refetch never runs. Not this issue's to fix;
  `refetchHistory`'s plain path keeps today's behaviour. Worth a register or issue note.
- Decisions 18, 20, 21, 22, 23 are **assumed** and defensible — for the human at the end.
- Correction (R10 testid → `data-highlighted`) accepted: `_item_for` (`chat_page.py:293-294`)
  selects by `message-item`, and a second testid on that element is impossible.

## Checked and sound

- Header, base commit `950e66a` = `git log -1`; length 594 lines; RED 1–4 before GREEN 5–7, gate
  named; *Found while building* empty; no task commits; Task 10 names `lint unit` and `e2e` only.
- TanStack 5.101.4 (primary checkout): `fetchNextPage`/`refetchQueries` default `cancelRefetch: true`
  (`queryObserver.ts:328`, `queryClient.ts:319`); cancel vs. join (`query.ts:404-420`); success clears
  `isInvalidated` (`query.ts:731-738`); refetch re-fetches every loaded page from fresh cursors.
- `useChannelSocket.ts:134,202` are the only history invalidations; `MessageList.tsx:150` the only
  `fetchNextPage` — the file map covers every writer.
- Expected reds in Task 1 (`Failed to resolve import "./jump"`; `… is not a function` for the new
  `useMessages` exports; `expected 1 to be 2` for the join-ack test) match what the runtime reports.
- Focus guard test is real: `setPageAttention` dispatches a bubbling `visibilitychange`, which
  `focusManager.ts:23` hears on `window`.
- `ProblemError.message` is the Problem `detail` (`client.ts:69`), so "Search is unavailable." shows.
- Types for `/api/v1/search/messages` exist (`types/messaging.ts:297,1236`); `/api/v1/search` is in
  the Ingress allow-list (`ingress.yaml:57`); no env var, OpenAPI or migration change.
- `docker-compose.test.yml:96-100` already un-publishes Worker and Elasticsearch ports; the ES
  healthcheck is `docker-compose.yml:109-114`.
- BDD: reused phrases exist in `steps/conftest.py:44,84,119`; "zeppelin" is used nowhere else;
  testids live in the page object; the last `Then` reads server-backed state.
- Baseline counts match `docs/test-report.md` at `d4be439`. No 🔴 built on (D29, D16, D12, D28 named).
- Helpers named exist: `deferred()` (`ChannelView.test.tsx:72`), `gate`, `holdJoins`,
  `aReturningUser`, `isInvalidated` (`useChannelSocket.test.tsx:52,143-147,186-190`).
