Issue: 2

# Issue 2 — Message search in the SPA

## Summary

Messaging already searches messages (`GET /api/v1/search/messages`, built in `b25612d`); the
SPA has no way to use it. This work adds a search box to the sidebar, a results page, and a
click-through that opens a result in its channel, scrolled to and highlighted — paging the
channel's history back to find it, since history can only be read backwards from the newest.

**Builds on issue 1** (`46f9214`, merged in `08fd0af`). R7 changes issue 1's read rule, and the
jump drives the `MessageList` scroll state issue 1 rewrote.

## Services touched

**The SPA only** (`src/frontend`), plus `scripts/test.sh` to run Elasticsearch and the Worker
in the e2e stack. No service, chart or compose change. Read `docs/design/02-messaging-service.md`
§3.1.6 for the server contract, consumed unchanged, and `docs/design/06-frontend-spa.md` §4 and
§5.2 (as issue 1 left it).

## What exists already

- **`GET /api/v1/search/messages`** — `q` required, trimmed, at most 200 characters; `limit`
  (default 50) and `cursor`. Returns `MessageListResponse` `{ items: Message[], nextCursor }`,
  the same DTO as history, **newest first**. Every word must match; no query syntax.
  - Only channels the caller can see (public + private they are in, archived excluded), and
    **no deleted messages** — hits are hydrated from Postgres, so index lag can't show either.
  - Bodies are current: an edited message shows its new text (it may still match on old words
    until the Worker catches up).
  - **A page can be shorter than `limit`; only `nextCursor: null` means the end.**
  - Blank or over-long `q` → 400 `validation-error`. Elasticsearch down → 503
    `"Search is unavailable."`. Index never created → an empty page. No 404 path.
  - No highlight data, no channel filter.
- Its types are generated (`types/messaging.ts`); no wrapper in `lib/api/messaging.ts`, no hook.
- **History** (`useMessages`, `messageKeys.list(ws, channelId)`) is a `useInfiniteQuery` paging
  backwards by cursor only; there is no `around`. `GET /api/v1/messages/{id}` (`getMessage`)
  fetches one message. Each row is `<article data-message-id>` (`MessageItem.tsx`).
- **`MessageList`** keeps the scroll position when older pages are prepended
  (`heightBeforePrepend`) and auto-scrolls only when the count grows while stuck to the bottom.
  `ChannelView` mounts it with `key={channel.id}`, so every channel switch is a fresh mount that
  starts at the newest message.
- **Issue 1's read rule** lives in `MessageList`: `beingRead = attending && atBottom`
  (`usePageAttention`, measured `atBottom`). While true it sets `readingChannelId` in the chat
  store, which hides the sidebar badge, and asks `useMarkRead` for a read of `readTarget(messages)`
  once the divider has captured. The divider (`readState.ts`: `captureFor`, `findDivider`) captures
  once per mount, when the detail and history have both stopped fetching.
- **Existing defect — fixed by R8.** `MessageList` calls `fetchNextPage` guarded only on
  `!isFetchingNextPage`. Scrolling to the top while the join-ack refetch
  (`useChannelSocket.ts`) is in flight cancels that refetch, so broadcasts missed in the join
  gap are lost, and leaves `heightBeforePrepend` set for the next unrelated height change.
- **The sidebar's channel list holds the first 50 channels only** — `useChannels` never follows
  `nextCursor`. `channelKeys.detail(ws, id)` / `getChannel` fetch one.
- **Author names** come from `useWorkspaceMembers(...).nameFor(id)`: any current member;
  a short id for anyone else.
- **`ProblemBanner`** takes `error` only — no action or retry.
- e2e: `scripts/test.sh` scales `elasticsearch` and `worker` to zero (`E2E_SCALE`, "delete this
  line when a search journey lands"). The per-scenario reset truncates Postgres, not the index.

## Requirements

1. **The box.** A search box at the top of the sidebar, on every chat route. Enter submits the
   trimmed text to `/search?q=…`; a blank or whitespace-only box submits nothing. The input
   accepts at most 200 characters. On `/search` it shows the current `q`; on any other route
   it is empty. Submitting the same `q` again refetches it.
2. **The results page.** `/search?q=…` shows the results in `<main>`, newest first, cached by
   workspace and `q`. Returning to it shows the cached list at once and refetches it. A list on
   screen never updates live.
3. **A result.** Each row shows the channel name (`#general`), the author's display name, the
   date and time, the body as plain text — never HTML — and "(edited)" when `editedAt` is set.
   The matched words are not highlighted.
4. **Channel names.** The name comes from the cached channel list when the channel is in it;
   otherwise from that channel's detail, fetched once per distinct channel, showing `#…` until
   it arrives. A 404 for the detail leaves the row as it is.
5. **Load more.** A "Load more" button shows while `nextCursor` is not null and appends the next
   page. A page shorter than the limit does not end the list.
6. **Empty and failed.** No results: `No messages match "x".` — no caveat. A 503 shows "Search
   is unavailable." with a Retry that refetches.
7. **The jump.** Clicking a result opens `/c/:channelId?message=<id>`. The SPA looks for the
   message in the loaded history, then pages back until **10 pages are loaded in total** —
   pages already cached count — so the reach is always the newest 500 messages. Found: it is
   scrolled to the centre and highlighted for 2 seconds, then the highlight fades, and the
   `message` param is removed with `replace`. Not found within 10 pages: the channel shows its
   newest messages with the notice "That message is too far back to show.", and the param is
   removed. A history fetch that fails mid-jump ends it: the param is removed, nothing scrolls
   or highlights, `MessageList`'s existing error banner shows the failure, no notice and no
   retry. A tombstone found is highlighted like any message. While a jump runs, a new message
   arriving does not pull the list to the bottom, and **no read is sent** (issue 1 R2). A jump
   ends when its highlight fades, at the cap notice, or on a failed fetch; then the read rule
   applies as usual.
8. **No fetch cancels another.** A page fetch for history — the jump's or a scroll to the
   top — never cancels a refetch of that history, and a refetch never loses a page already
   fetched.
9. **Leaving mid-jump.** Switching channel, going Back, or the list unmounting abandons the jump:
   nothing scrolls, nothing highlights, no notice. A second result clicked mid-jump starts its
   own; only the latest target is ever scrolled to or highlighted.
10. **Accessibility and test hooks.** The box is inside `role="search"` with an accessible name;
    the results are a list; the notice and "No messages match" are `role="status"`; the 503 is
    `role="alert"`. The box, each result, Load more and the highlighted message carry a
    `data-testid` for the BDD page object.

## Where the rules meet

- **The jump and the read rule (R7, issue 1 R2).** A jump opens a channel at its newest messages
  before scrolling away; without R7 it would be "at the bottom" for a moment and mark the channel
  read. During a jump nothing is read, and `beingRead` is false, so `readingChannelId` is cleared
  and an unread channel's badge shows until the user reaches the bottom (issue 1 R1).
- **The jump and the divider (R7, issue 1 R8).** Paging back for the jump may load the page with
  the divider's boundary; the divider appears there as R8 already says. The capture waits for
  history to stop fetching, so the jump's paging can delay it, but not change it: its ceiling is
  the newest message, and paging adds only older ones. The highlight and the divider are
  separate and may show together.
- **The jump and the join-ack refetch (R7, R8).** Opening the channel invalidates its history;
  the jump waits for that refetch rather than cancelling it, then looks again (see *Timing*).
- **A result and a later change (R2, R7).** A message deleted after the search ran is still
  listed; its jump finds and highlights the tombstone. A channel the user lost access to fails
  on the existing channel 404.
- **Two jumps (R9).** The first is abandoned; pages it fetched stay cached.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| Search from `/`, or from inside a channel | the box works the same on both |
| Back from a jumped-to channel | `/search?q=…` shows the cached list and refetches it |
| Reload on `/search?q=…` | the search runs again |
| Reload on `/c/:id?message=…` before the param is removed | the jump runs again |
| Reload after the jump ended | no jump: the param is gone |
| Workspace switch on `/search` | the search runs again in the new workspace; no old results show |
| Jump into a cached channel, or the one already open | the loaded pages are searched first, then paging back; it scrolls from wherever the list is |
| Jump into another channel | `MessageList` remounts (behind "Loading…" if uncached); the jump starts once the new list has its history |
| Reconnect mid-jump | the join-ack refetch runs to completion; the jump continues after it (R8) |
| A result whose channel is outside the first 50 | its name arrives from the detail (R4) |
| A second tab | n/a — nothing in search is live or shared between tabs |

## What this assumes — check before building on it

Checked against TanStack Query 5.101.4 and react-router 7.18.1; re-check if either has moved.

- **`fetchNextPage` and a refetch cancel each other** by default (`cancelRefetch: true`,
  `queryObserver.ts`, `query.ts`). The cancelled caller isn't rejected; it gets the new fetch's
  promise. **A successful `fetchNextPage` clears `isInvalidated`**, so a cancelled recovery
  refetch is never re-run.
- **A refetch of an infinite query re-fetches every loaded page in sequence**, deriving each
  later cursor from the fresh result, not the stored ones. Ten loaded pages cost ten requests.
- **`listMessages` ignores the abort signal**: a cancelled request still completes; its result
  is discarded.
- **Adding or removing `?message=` on the same channel remounts nothing**; `/c/A` → `/c/B`
  always remounts `MessageList` (`key={channel.id}`), behind "Loading…" when B's detail is
  uncached.
- **Queries have no `staleTime`** except `useWorkspaceMembers` (5 min), so a cached list renders
  at once and refetches on mount.
- **Indexing is asynchronous with no stated lag**, and recall is incomplete (D29).

## Timing

A jump to a message three pages back, opened fresh:

```
t0     click result M → /c/general?message=M; join → ack
t1     join-ack refetch of page 1 in flight → the jump waits
t2     refetch lands; M not loaded → jump fetches page 2
t3     page 2 lands; M not in it → fetch page 3
t4     page 3 lands; M found → scroll to centre, highlight; param removed (replace)
t4+2s  highlight fades; the read rule (issue 1 R2) is live again
```

A reconnect landing mid-jump:

```
t0  jump has fetched page 2, page 3 in flight
t1  socket reconnects → ack → history invalidated
t2  page 3 lands and is kept; the refetch of pages 1–3 runs after it, uncancelled
t3  refetch lands; the jump looks again in the loaded pages
```

## Decided already

1. Scope is R1–R10; everything in *Not in this issue* stays out.
2. SPA only. The jump pages back on the client; no `around` cursor.
3. Box in the sidebar, results on their own route, submit on Enter only.
4. No match highlighting; bodies render as text.
5. "Load more", not infinite scroll.
6. The jump target is a URL param, removed with `replace` when the jump ends.
7. Cap 10 loaded pages in total; highlight 2 seconds; no read during a jump; a failed fetch
   ends the jump.
8. Results are a snapshot: refetched on return, never live.
9. The existing `MessageList` cancel defect is fixed here (R8).
10. No 🔴 entry blocks this. Nearest: **D29** (no reindex — recall gaps, never visibility; not
    settled here), **D16** (tombstone retention — search returns no tombstones, untouched),
    **D12** (canvas search — out). **D8c** (🟡) is what this is built against.

Left to the plan, on purpose: how the jump waits on a refetch, how R7 holds reads off, how Retry
is added beside `ProblemBanner`, the date format, and the highlight's styling.

## Tests

- **Vitest** for everything below the journey: submit, trim and blank; the 200-character cap;
  the box's text per route; results order, rows, plain-text bodies, "(edited)"; the channel-name
  fallback and its 404; Load more on a short page; empty and 503 with Retry; the cached return
  and refetch; the workspace switch; the jump found in loaded pages, after paging, at the cap
  (cached pages count), after a failed fetch, and to a tombstone; the param removed; no pull to
  the bottom, no `mark_read` and the badge shown during a jump; both *Timing* sequences; abandon
  and latest-target-wins; the scroll-to-top-during-refetch defect. Use the MSW stubs,
  `aMessage()` / `aMessagePage()`, `FakeSocket`, and fake timers for the 2 seconds.
- **One BDD journey** in a new `search.feature`: Ada posts a word unique to the scenario in
  #general, searches for it, sees the result, clicks it, and lands in #general with that message
  highlighted. Turn on `elasticsearch` and `worker` in `scripts/test.sh` (delete `E2E_SCALE`
  and its comment). The page object retries the search for up to 10 seconds; scenarios use
  unique words rather than resetting the index.

## Record in this slice

- `docs/design/06-frontend-spa.md`: a new search section — the box, the route, the row, Load
  more, the jump, its cap and its exception to the read rule. Update §4's line on unified search:
  search is one workspace, the token's.
- Register **D8c**: a "built against it" note for the SPA. No new entry.
- An ADR: *jump to a search result by paging back, not an `around` cursor*. Alternative: an
  `around` param on history and a cache that grows both ways. Revisit when the cap is hit often.

## Not in this issue

- An `around` cursor on history, or any Messaging change.
- Highlighting matched words; a channel or author filter; search as you type.
- Live updates to a results list on screen.
- Recall fixes and reindexing (D29).
- The OpenAPI document's 422 for validation where the service returns 400.
- Following `nextCursor` in the sidebar's channel list.
- Cross-workspace search; canvas search (D12).

## Acceptance — first real run on Compose

Search only for words posted after the stack is up — older messages were never indexed (D29).
- Ada searches a word from a message ~3 pages back in a channel with unread messages: the result
  opens there, centred and highlighted, and the channel's badge stays.
- Back: the results are there.
- A result more than 10 pages back: the notice shows.
- Grace deletes a listed message; Ada clicks it: the tombstone is highlighted.
- Stop Elasticsearch: "Search is unavailable."; start it, Retry: results.
- Ada switches workspace on `/search`: the search runs in the new workspace.

## References

- `docs/design/02-messaging-service.md` §3.1.6, §5
- `docs/design/06-frontend-spa.md` §4, §5.2
- `docs/design/07-open-decisions-register.md` D8c, D16, D29
- `docs/adr/260914-message-search-index-is-a-candidate-list.md`
- `docs/issues/001.md` — R2, R3, R8 and its *Paths*, which this builds on
- Commit `b25612d` (message search pipeline) — the endpoint this consumes
