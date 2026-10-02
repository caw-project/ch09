Issue: 3

# Issue 3 — Message threads

## Summary

Anyone who can see a channel can reply to a message in a thread. Replies live in a panel beside
the channel, not in the channel's history; the message they reply to — the root — shows how many
replies it has and when the last one came. Threads are single-level (D8a), and everyone looking
at the channel sees replies and counts change live.

**Built from `main`, alongside issue 2** (message search in the SPA), which is not merged yet
and will likely merge first. Nothing here may depend on issue 2's code. Expect a merge overlap in
`MessageList.tsx`, `MessageItem.tsx`, `ChannelView.tsx` and `useChannelSocket.ts`: keep this
issue's changes to `MessageList` and the read rule as small as the requirements allow, and put
the panel in its own components.

## Services touched

**Messaging and the SPA.** Read `docs/design/02-messaging-service.md` §3.1 (endpoint table,
§3.1.3 DTO, §3.1.5, §3.1.6, §3.1.7), §3.2.4 and §4, and `docs/design/06-frontend-spa.md` §3 and
§5.2. No Worker, chart or compose change.

## What exists already

- **`messages.thread_root_id`** — nullable, FK to `messages(id)`, never set
  (`alembic/versions/0002_messages.py`, `models.py`). `ix_messages_thread (thread_root_id, id)
  WHERE thread_root_id IS NOT NULL` is designed in doc 02 §4 and deliberately not created.
- **`MessageResponse.thread_root_id`** serializes as `threadRootId`, always `null`
  (`schemas.py`, `routers/messages.py:_as_message`). `GET /messages/{id}/thread` is in doc 02's
  endpoint table, marked unbuilt.
- **Sending:** `SendMessageRequest` (REST `POST /channels/{id}/messages`) and
  `SendMessagePayload` (socket `send_message`, `realtime_writes.py`) take `body` only; an extra
  `threadRootId` is silently ignored (`CamelRequest` does not forbid extra keys).
- **History** (`messages.history_page`) is `WHERE channel_id = ? ORDER BY id DESC`, keyset on
  `id`, with no thread filter. **Unread** (`channels._with_read_state`) counts every row in the
  channel after the marker, written by someone else, not deleted — no thread filter.
  **`read_state.mark_read`** accepts any message in the channel.
- **Search** hydration (`search.py`) selects visible, non-deleted messages by id — no thread
  filter. The index mapping is `strict` and has no thread field; it does not change here.
- **Broadcasts** to `channel:{id}`: `message_received`, `message_edited`, `message_deleted` carry
  the full `MessageResponse`; `reaction_changed` carries `{messageId, channelId, emoji, count,
  userId, reacted}` — no `threadRootId`.
- **SPA:** one key, `messageKeys.list(ws, channelId)` = `['messages', ws, channelId]`, a
  `useInfiniteQuery` paged backwards (`useMessages.ts`). The socket handler upserts every message
  event into that key by `channelId` alone, and `upsertMessage` prepends an unknown id to
  `pages[0]` (`useChannelSocket.ts`, `useMessages.ts`). `MessageItem` has react, edit and delete
  in a hover menu; `MessageComposer` sends over the socket, optimistically (`temp:` ids), with a
  Zustand draft per channel. `ChannelView` puts `MemberPanel` in a right column.
- **Template:** reactions (`c02dcd7`) — new DTO fields aggregated per page, a channel-room
  broadcast, a cache writer applied from both the response and the echo.

## Requirements

1. **Start a thread.** A non-deleted, non-pending top-level message offers "Reply in thread" in
   its menu. A reply, and the root shown inside the panel, offer no such action. Clicking a
   root's reply summary in the channel also opens its thread — including on a deleted root,
   where the summary is the only way in.
2. **Send a reply.** `send_message` and `POST /channels/{id}/messages` accept an optional
   `threadRootId`. A reply is optimistic like a channel message. A `threadRootId` naming a reply
   is normalised to that reply's root. A root that is unknown, in another channel, or in a
   channel the caller can't see is refused, and nothing is created.
3. **Out of history.** A reply never appears in channel history — not from the server, not in the
   cache, not from a socket event.
4. **The summary.** Every message carries `replyCount` and `lastReplyAt`, counting non-deleted
   replies only. A root with at least one shows "N replies" (or "1 reply") and the time of the
   last; with none it shows nothing.
5. **The panel.** The open thread shows its root (with reactions and react, edit and delete, but
   no reply summary), then the
   replies oldest-first, then a composer. Deleted replies show as tombstones. It reads
   `GET /messages/{id}/thread`, cursor-paged, newest page first; scrolling to the top loads older
   replies and keeps the position.
6. **Where it lives.** The open thread is the URL param `/c/:channelId?thread=<rootId>`; the panel
   takes the right column in place of `MemberPanel` and has a close button. Opening a thread,
   or another one, pushes a history entry, so Back returns to the previous thread or the closed
   panel; closing removes the param with `replace`. Switching channel or workspace closes it.
7. **A bad thread.** `?thread=` naming a reply, an unknown id, or a message outside the channel
   shows "This thread isn't available" in the panel; the channel is unaffected.
   `GET /messages/{id}/thread` on a reply is a 404.
8. **Live.** Replies, and edits, deletes and reactions on replies, reach everyone looking at the
   channel through the existing `channel:{id}` room — in the open panel, once, not twice. A
   root's new `replyCount` and `lastReplyAt` reach everyone in the channel, and the client
   always sets the server's value — never adds to its own.
9. **Reply actions.** A reply is edited, deleted and reacted to under the same rules as any
   message (D8d, D39).
10. **A deleted root** is a tombstone that keeps its summary; its thread stays readable and still
    accepts replies.
11. **Unread.** Replies never count toward a channel's unread count. `mark_read` naming a reply
    is refused and the marker does not move. Reading a thread moves nothing.
12. **Search** returns no replies: they are filtered when hits are hydrated. Roots still match.
13. **Scroll.** Your own reply scrolls the panel to the bottom; someone else's does only when the
    panel is within 80px of it (`STICK_THRESHOLD`). Nothing in the panel moves the channel's
    scroll or touches its read rule.
14. **Drafts.** The thread composer keeps its own draft per root, apart from the channel's.

## Where the rules meet

- **The response and the echo (R2, R8):** the sender gets the reply from the ack and from
  `message_received`, in either order — it shows once in the panel, never in history, and the
  root's count is the server's, so a duplicate can't count twice. No optimistic count bump.
- **The socket handler and history (R3, R8):** today a reply event would be prepended into
  `messageKeys.list` because routing is by `channelId` alone. Every message event with a
  `threadRootId` goes to that thread's cache, or nowhere if it isn't cached.
- **Reactions on a reply (R8, R9):** `reaction_changed` has no `threadRootId`; a reaction on a
  reply must still reach the open panel.
- **A reply deleted (R4, R9):** it becomes a tombstone in the panel, and the root's count and
  `lastReplyAt` drop for everyone in the channel.
- **The root edited or deleted while open (R5, R10):** the panel's root and the channel's root
  both show the change; the panel stays open and the composer still sends.
- **Unread and the read rule (R3, R11):** issue 1's read target, divider and badge are computed
  over channel history only, so with replies out of history they see roots only — the read rule
  itself needs no change. The server's unread count must exclude replies separately.
- **Search and issue 2's jump (R12):** issue 2 opens a result by paging channel history. A reply
  can never be found there, which is why replies are out of search until a later issue opens
  them in their thread.
- **Issue 2's `?message=` and `?thread=` (R6):** both may sit on `/c/:channelId`; issue 2 removes
  its param with `replace`, which must not drop `thread`. (Issue 2 is not on `main`; this is
  for whichever merges second.)

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First open of a thread | root and replies come from the server |
| Reopen a thread whose replies are cached | the cache shows at once and is refetched; a reply made while it was closed appears |
| Reload with `?thread=` set | the panel reopens on that thread |
| Back after opening thread A, then thread B | thread A shows; Back again closes the panel |
| A root not in the loaded channel history (old, or from the URL) | the panel still shows it, fetched on its own |
| Switching thread while a thread fetch is in flight | the response lands in its own thread's cache, or nowhere |
| Reconnect, or a channel join-ack | the open thread is refetched with history, recovering broadcasts missed in the gap |
| A second tab or device of the same user | sees replies and counts live, like anyone else |
| Losing access to the channel, or it archived | the panel goes with the channel; nothing shows from a cached thread |
| Switching channel or workspace | the panel closes; no thread from the old one is shown |

## What this assumes — check before building on it

- **TanStack Query 5.101.4 invalidates by prefix and refetches only active queries.** Both
  join-ack refetches invalidate `['messages', ws, channelId]`; a thread key nested under it is
  refetched with it, and one that isn't is not (`@tanstack/query-core` `partialMatchKey`).
- **A broadcast sent before the join ack never reaches the joiner**, and python-socketio replays
  nothing on reconnect (`useChannelSocket.ts`, its header) — the reason for the refetch above.
- **An event for an absent cache key is dropped** (`upsertMessage`'s `if (!cached)` guard); a
  reply event for a thread that isn't open changes nothing but the root's summary.
- **`message_edited` and `message_deleted` carry `threadRootId`** (the full DTO); only
  `reaction_changed` lacks it.
- **Issue 2's contract that a search page can be shorter than `limit`** makes filtering replies
  at hydration safe for its "Load more".

## Timing

No throttle or window. The one ordering that matters, Ada replying while Grace watches:

```
t0  Ada sends reply R to root M  → R (temp:) in Ada's panel; M's count unchanged
t1  message_received R           → Grace's open panel adds R; Ada's replaces temp: with R
t1  M's summary (count 1)        → both channels show "1 reply"
t2  Ada's ack R                  → already there; still once, count still 1
    (t1 and t2 may land in either order; the result is the same)
```

## Decided already

1. Scope is R1–R14; *Not in this issue* stays out.
2. Single-level threads: **D8a goes 🟢** in this slice.
3. Replies are out of channel history, out of unread, and out of search results.
4. A deleted root keeps its thread open. Reply actions follow D8d and D39 unchanged.
5. The panel is a URL param and replaces `MemberPanel` while open.
6. Broadcasts use the existing channel room; no new room or join.
7. No 🔴 entry blocks this. Nearest: **D16** (tombstone retention — a deleted root or reply is
   a tombstone like any other, untouched), **D29** (reindex — replies stay in the index, only
   hydration filters them), **D28** (preferences — nothing per-user is stored).

Left to the plan, on purpose: whether counts are stored or aggregated, the event that carries a
root's summary and its payload, the status code for a refused root or a reply id on `mark_read`,
the thread query key, the panel's width, and the `ix_messages_thread` migration.

## Tests

- **pytest below the journey:** normalising a reply id to its root; refusing an unseen, unknown
  or other-channel root; history, unread and search excluding replies; `mark_read` refusing a
  reply; the summary counting non-deleted replies only; the thread route's paging and its 404
  on a reply; the room-only broadcast of a reply and of the summary.
- **Vitest:** the menu action; the summary text; the panel's order, tombstones and paging; the
  bad-`?thread=` notice; a reply event never reaching history; a reaction on a reply reaching
  the panel; the response and echo in both orders; the count set, not added; the cached return
  and refetch; the join-ack refetch; the scroll rules; the per-root draft; switching closes the
  panel. Use the MSW stubs, `aMessage()` / `aMessagePage()` and `FakeSocket`.
- **One BDD journey:** Ada replies in a thread on a message in #general; Grace, already looking
  at #general, sees "1 reply" appear without reloading, opens the thread and sees Ada's reply.

## Record in this slice

- Doc 02: the thread route, `replyCount` / `lastReplyAt`, `threadRootId` on send, the summary
  event, `ix_messages_thread` created, and replies excluded from history, unread and search.
- Doc 06: the thread panel, its URL param and its scroll rules, under `/features/threads`.
- Register: **D8a** 🟢, with the date and the ADR.
- An ADR: *single-level threads, kept out of channel history, unread and search*. Alternatives:
  "also send to channel", replies counted as unread, replies searchable now.

## Not in this issue

- Opening a reply from search — a follow-up once issues 2 and 3 are both merged.
- Following threads, a "threads" view, thread unread state or notifications (D18).
- "Also send to channel"; nested replies; a typing indicator in threads.

## Acceptance — first real run on Compose

With Ada and Grace in two browsers, both in #general:
- Ada replies in a thread: Grace's root shows "1 reply" at once; Ada's panel shows the reply once.
- Grace closes the thread, Ada replies again, Grace reopens it: both replies are there.
- Ada deletes the root: the tombstone keeps "2 replies", and Grace can still reply.
- Ada reloads with `?thread=` in the URL: the panel reopens.
- A reply does not raise Grace's unread badge for #general.
- Searching a reply's words finds nothing; the root's words still find the root.

## References

- `docs/design/02-messaging-service.md` §3.1, §3.1.3, §3.1.5–§3.1.7, §3.2.4, §4
- `docs/design/06-frontend-spa.md` §3, §5.2
- `docs/design/07-open-decisions-register.md` D8a, D8d, D16, D29, D31, D39
- `docs/issues/001.md` (the read rule), `docs/issues/002.md` (the jump, `?message=`)
- Commit `c02dcd7` (message reactions) — the template for DTO fields, a broadcast and its writer
