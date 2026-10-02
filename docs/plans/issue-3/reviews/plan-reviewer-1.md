# Plan review — issue 3, round 1: changes_requested

The plan is in good shape: well-sourced, every decision row has its reason, and the library claim
it relies on (decision 15) checks out against the installed 5.101.4. It goes back for six major
findings: two RED test specs that would pass the gate or fail a correct build; a summary that
no test pins on the edit and reaction paths; an old root that the panel's own writes would
insert at the head of history; a reply count read before commit; and an error branch that a
background refetch can trigger to replace a loaded thread. All six can be fixed from the code and
this review.

## Expectations

Written from the issue, doc 02 §3.1/§3.2/§4, doc 06 §3/§5.2, the register (D8a, D8d, D16,
D29, D31, D39) and the code (`messages.py`, `routers/messages.py`, `routers/reactions.py`,
`routers/search.py`, `search.py`, `read_state.py`, `channels._with_read_state`,
`realtime_writes.py`, `useMessages.ts`, `useChannelSocket.ts`) — before the plan was opened.

### Decisions any plan must make

- E1. Counts: stored on the root row, or aggregated per page like reactions? If stored, how is
  a delete decremented and `lastReplyAt` recomputed when the newest reply is deleted?
- E2. The summary event: a new event (name, payload — full `Message` or `{messageId,
  channelId, replyCount, lastReplyAt}`)? A full `Message` carries per-caller `reactions[].reacted`
  — the same reason `reaction_changed` is not a `Message` (doc 02 §3.2).
- E3. Status for a refused root (unknown / other channel / unseen) on REST and on the socket ack —
  404 "No such channel." to keep ids unprobeable, or 400? And for `mark_read` naming a reply?
- E4. The thread query key — nested under `['messages', ws, channelId]` (so the join-ack prefix
  invalidation refetches it) or not? And where the panel's root lives in the cache.
- E5. What `GET /messages/{id}/thread` returns: replies only, or root + replies? Paging order on
  the wire, cursor shape, page size. Its guard: visibility (doc 02 §3.1.1) or "channel member"
  (the endpoint table)? Deleted root → 200?
- E6. `replyCount`/`lastReplyAt` on a reply itself — 0/null, or absent? Required in OpenAPI?
- E7. "When the last one came" — `lastReplyAt` is the newest non-deleted reply's `createdAt`?
  Edited replies don't move it?
- E8. "Your own reply scrolls the panel to the bottom" — on the optimistic insert, on the
  confirm, or both?
- E9. Migration: `ix_messages_thread` in a new 0005 (plus any stored columns, with what default
  and backfill)?
- E10. How `reaction_changed` (no `threadRootId`) reaches the panel: search thread caches by
  `messageId`, or add a field to the event (an additive contract change)?
- E11. `?thread=` validation: how does the panel know the root is a reply, unknown, or in
  another channel — thread-route 404, or the root's own `threadRootId`/`channelId` checked
  client-side? `GET /messages/{id}/thread` on another channel's (visible) root is a 200, so
  the "outside the channel" case must be a client check.
- E12. The panel's width; the panel's components in their own files (merge with issue 2).
- E13. Back after a channel switch lands on `/c/A?thread=X` — reopens the thread. Intended?

### Conflicts to name

- C1. R2 (`threadRootId` on send) vs doc 02 §3.1.3 and §3.2.4 ("no `threadRootId`", "nothing
  else") — a record item, not a deviation, but the plan must update both.
- C2. R5/R7 thread route vs doc 02's endpoint-table auth "channel member" vs §3.1.1's
  visibility rule.
- C3. R10 (tombstone keeps its summary) vs today's delete path, which builds the tombstone DTO
  with nothing aggregated (`_as_message(result.message, reactions=[])`) — the count must survive.
- C4. R11 (`mark_read` refuses a reply) vs doc 02 §3.1.7 ("the message must be in that channel"
  — a reply is) — the doc changes.
- C5. R1 ("non-deleted … top-level offers Reply") vs R10 ("deleted root still accepts replies")
  — server accepts a reply on a deleted root; the UI way in is the summary only.

### Tests that must exist

- Server: normalise reply→root (stored `thread_root_id` is the root, ack/response show it);
  refuse unknown / other-channel / unseen root with nothing created (row count, no broadcast,
  no index job); REST and socket both; history excludes replies (with a root and a reply in the
  same page window, so a "returns nothing" build fails); unread excludes replies by someone else;
  `mark_read` on a reply refused *and the marker unmoved*, with a positive control; search
  hydration drops a reply but keeps a root matching the same words; count excludes deleted
  replies and `lastReplyAt` falls back when the newest is deleted; the summary on every DTO path
  (history, get, send, edit, delete of the root, reactions, search, socket acks); thread route
  paging over > 1 page, oldest/newest order, tombstones included, 404 on a reply, 404 on an
  unseen channel; room broadcast of reply and summary; reply to a deleted root accepted.
- SPA: menu action present on a top-level, absent on reply, pending, deleted and the panel root;
  summary "1 reply"/"N replies"/nothing; panel order, tombstones, paging with position kept;
  bad `?thread=` (reply, unknown, other channel); a reply event never in history; reaction on a
  reply reaching the panel; response/echo in both orders; count set not added (event below the
  local count); cached return + refetch; join-ack refetch of the thread; scroll rules both sides
  of 80px; per-root draft (and a failed reply's text returned to the *thread* draft); channel /
  workspace switch closes; Back/push vs close/replace.
- BDD: Ada replies; Grace (already in #general) sees "1 reply" without reload, opens the thread
  and sees the reply — opening it reads the server.

### Risks

- R-a. Two concurrent replies: each transaction counts before the other commits, so both
  broadcast `replyCount: 1` — the last-set value is wrong. Count after commit, or a stored
  counter updated with a row lock? And two summary events delivered out of order.
- R-b. Every `_as_message` site must carry the summary: a root's `message_edited` or
  `message_deleted` built with a zero count would overwrite the channel's summary via
  `upsertMessage` (and the reaction routes too).
- R-c. `upsertMessage` prepends an unknown id to `pages[0]`: a root summary/edit event for a root
  not in the loaded history would be inserted at the head of history. A summary event per reply
  makes this frequent.
- R-d. Every SPA mutation writes `messageKeys.list` (`useEditMessage`, `useDeleteMessage`,
  `useToggleReaction`, `useSendMessage`'s optimistic row with `threadRootId: null`) — each needs
  a thread-aware key for replies, and the panel's root must update both caches.
- R-e. `reapplyAfterFetch` only watches the history key: a reply event during a thread fetch is
  lost unless it covers the thread key too.
- R-f. Switching thread mid-fetch: response lands in its own key (query keyed by rootId) — test.
- R-g. Losing access / archive: the thread query 404s; cached thread must not render.
- R-h. CH009 (select on a soft-delete table) for the count and the thread queries; OpenAPI and
  generated types regenerated; every TS `Message` literal and `aMessage()` gain the fields.
- R-i. The SPA read rule and divider read history only — unchanged; `MessageList` changes kept
  small.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 start a thread (menu on non-deleted, non-pending top-level; none on reply or panel root; summary opens, deleted root too) | Tasks 3, 7; `MessageItem.thread.test`, `ThreadPanel.test` | covered — but see finding 2 (guards pass at red) |
| R2 send a reply: optional `threadRootId` on both transports, optimistic, reply→root, refusals with nothing created | decisions 11, 21; Tasks 1, 2, 4, 5, 6 | covered — minor 10 on "nothing is created" |
| R3 never in history: server, cache, socket | decision 20; `history_page` filter; socket routing tests | covered |
| R4 `replyCount`/`lastReplyAt` on every message, non-deleted only; "N replies" / nothing | Tasks 2, 5, 7 | **misread in part** — "every message" untested on edit/reaction/socket paths (finding 3) |
| R5 panel: root with actions, no summary; oldest-first; tombstones; cursor paging; keep position | decision 14; `ThreadPanel.test`, `useThread.test` | covered |
| R6 URL param, replaces `MemberPanel`, close, push/replace, switch closes | decisions 5, 24; `ChannelView.thread.test` | covered (finding 2 on two of its guards) |
| R7 bad thread notice; route 404 on a reply | decisions 12, 19, 23 | covered — finding 6 on "any error" |
| R8 live via the channel room, once; summary set not added | decisions 9, 10, 22; Tasks 2, 3, 6 | covered — finding 5 on what value is set |
| R9 reply actions under D8d/D39 | `test_a_reply_is_edited_and_reacted_to_under_its_root`; `useThreadActions` tests | covered |
| R10 deleted root keeps summary, readable, takes replies | Tasks 1, 2, 3 | covered |
| R11 unread excludes replies; `mark_read` on reply refused, marker unmoved; reading a thread moves nothing | decision 13; Task 2; `ThreadPanel.test` | covered |
| R12 search drops replies, keeps roots | Task 2 `test_search` | covered |
| R13 scroll rules, 80px, channel scroll and read rule untouched | `ThreadPanel.test` 79/80px pair; `ChannelView.thread.test` | covered |
| R14 per-root draft | decision 18; `ThreadComposer.test`, `chat.test` | covered |
| *Where the rules meet* (7 rows) | Self-review maps each | covered |
| *Paths* (10 rows) | each has a Vitest test or a stated reason | covered |
| Decided already 1–7 | decisions 1–7 | covered |
| Tests (pytest, Vitest, one BDD journey) | Tasks 1–3 | covered — the last step opens the thread from the server |
| Record (doc 02, doc 06, D8a 🟢, ADR) | Task 8 | covered |
| Not in this issue | plan's own section | covered |
| E1 stored vs aggregated | decision 8 | settled |
| E2 summary event | decision 9 | settled |
| E3 refusal status codes | decisions 11–13 | settled |
| E4 thread key | decision 15 (verified) | settled |
| E5 thread route shape and guard | decision 14, Corrections (visibility) | settled |
| E6 fields on a reply | Task 2 interface: 0/null, required | settled |
| E7 `lastReplyAt` meaning | Task 2: `max(created_at)` of non-deleted | settled |
| E8 own-reply scroll timing | "own reply always" | settled enough — left to the code |
| E9 migration | decision 16 | settled |
| E10 reaction on a reply | decision 10 | settled — minor 8 on reactions on the root |
| E11 bad `?thread=` detection | decisions 12, 19 | settled |
| E12 width, own components | decision 17; `features/threads/` | settled |
| E13 Back across a channel switch | not discussed | settled by R6's wording — not a finding |
| C1 send vs doc 02 §3.1.3/§3.2.4 | Task 8 | settled (record) |
| C2 route auth "member" vs visibility | Corrections | settled |
| C3 tombstone keeps summary vs delete DTO | Task 5 `summary_for` on delete | settled |
| C4 `mark_read` vs §3.1.7 | Task 8 | settled (record) |
| C5 menu vs deleted-root replies | Tasks 1, 7 | settled |
| R-a concurrent replies | decision 22 (ordering only) | **missing** — finding 5 |
| R-b summary on every DTO site | Task 5 lists callers | **untested** — finding 3 |
| R-c unknown root prepended to history | — | **missing** — finding 4 |
| R-d mutations' keys | `useThreadActions`, decision 20 | settled |
| R-e reapply during thread fetch | Task 6 + test | settled |
| R-f switch mid-fetch | `useThread.test` | settled |
| R-g lost access | `ChannelView.thread.test` | settled (finding 2 on its red) |
| R-h CH009, OpenAPI, TS literals | Tasks 4, 5 | settled — minor 7 on `optimistic()` |
| R-i read rule untouched | constraints, tests | settled |

## Findings

### 1. The one-summary-query test passes at red and fails a correct build — major
**Where:** Task 2, `test_a_page_of_history_costs_one_summary_query` · **Checked:** the listener
it copies (`test_reactions.py:245-247` filters on a substring of the SQL); `history_page`
(`messages.py:183-188`) is `select(Message)`, which names every mapped column, and
`thread_root_id` is one (`models.py:179`).
Counting statements that name `thread_root_id` counts the history `SELECT` itself. At red that is
one statement, so `assert len == 1` **passes** and the stated red (`assert 0 == 1`) is wrong. Once
built, the history query (with its new `thread_root_id IS NULL`) plus the aggregate make two, so a
correct build **fails**. Settle it with a filter that only the aggregate matches (for example
`GROUP BY` and `thread_root_id` together, or `count(` over `messages` with `thread_root_id IN`),
and give the red the runtime would actually report.

### 2. Guard tests with no positive, which are green before the code exists — major
**Where:** Task 3, `MessageItem.thread.test.tsx` — `none on a pending message`, `…a deleted one`,
`…a reply`, `without onOpenThread: no summary, no action`; `ChannelView.thread.test.tsx` — `a
channel that 404s shows no panel, though its thread is cached`, `a new workspace shows no thread
from the old one`. · **Checked:** today `MessageItem` has no such button and `ChannelView` has no
panel (`ChannelView.tsx:85-107`).
Each asserts that something is absent, and nothing that is absent at red. They pass at the gate,
and the expected reds given for their files ("Unable to find role button 'Reply in thread'",
"…'complementary' 'Thread'") are not what they would report. Per *Tests that prove something*,
each needs its positive in the same test: the pending, deleted and reply cases beside a confirmed
top-level message that does offer the action; the 404 and workspace cases showing the panel
open first (before the 404 or the switch), then gone. Then the stated red is right for every test
in the file.

### 3. "Every message carries `replyCount`" is pinned only on history, get and delete — major
**Where:** Task 2 summary tests; Task 5 `_as_message(…, thread=)` bullet · **Checked:** the DTO
sites (`routers/messages.py:130,183,222,343`, `routers/reactions.py:82`, `routers/search.py:75`,
`realtime_writes.py:201,253,287`); `useEditMessage`/`useToggleReaction` write the response
through `upsertMessage` (`useMessages.ts:276,430`), and `message_edited` replaces the cached row
for everyone (`useChannelSocket.ts:150-157`).
Task 5 says get, edit and delete use `summary_for` on a root, but leaves `reactions._respond`,
search and the three socket sites as "pass `thread=`" without saying which value. A build that
passes `NO_REPLIES` from the edit route or `_respond` passes every Task 2 test, and then an edit of
a root broadcasts `replyCount: 0`, so "2 replies" vanishes from every window, and a reaction on a
root does the same in the reactor's own window. Reactions guarded the same hole with
`test_an_edit_keeps_the_reactions` ("Breaks if the edit route passes `reactions=[]` for
convenience"). Settle it with the value for every site, and tests that an edited root (REST
response and `message_edited` payload) and a reacted-to root keep their count. Search results
carry the summary too, or a decision row says they don't.

### 4. The panel's root writes would put an old root at the head of history — major
**Where:** Task 6, `useThreadActions` ("a root's result also goes through `upsertMessage` on the
history key") and `useChannelSocket` ("a top-level event goes to history **and** to
`threadKeys.detail`") · **Checked:** `upsertMessage` prepends any unknown id to `pages[0]`
(`useMessages.ts:126-130`).
The issue requires the panel to work for "a root not in the loaded channel history (old, or from
the URL)". Edit, delete or react to that root in the panel, and the plan's history write, and the
echo `message_edited`, insert it as the newest message in the channel. Today that happens only
when someone edits a message you haven't loaded. This change makes it the normal result of using
the panel. It needs an answer: for example, history takes an unknown id only from
`message_received`, while edits, deletes and responses replace a row already there and add nothing.
It also needs a test: open a thread whose root isn't in the loaded history, edit or react to it,
and check that history is unchanged.

### 5. The summary is read before commit, so concurrent replies broadcast a stale count — major
**Where:** Task 5, send ("compute `summary_for(root)` after the flush, commit, publish"); decision
22 · **Checked:** the send paths commit after building the response (`routers/messages.py:222-225`,
`realtime_writes.py:201-207`); Postgres defaults to READ COMMITTED.
Decision 22 answers the order in which events are delivered. It doesn't answer this. Replies A and
B in flight together each count their own uncommitted row and not the other's, so both broadcast
`replyCount: 1`. In whatever order they arrive, every window shows "1 reply" with 2 in the
database, until a refetch. Delete-plus-reply has the same problem. Settle it by reading the summary after
commit (a fresh read, so the last writer to commit broadcasts a count that includes everyone
committed before it), or by extending decision 22 to name this case and accept it. If you
accept it, say what the user sees.

### 6. "Any error shows the notice" also fires on a failed background refetch — major
**Where:** decision 23; Task 7 `ThreadPanel` ("notice … on any error") · **Checked:**
`main.tsx:15-27` retries a 5xx once and then errors; TanStack keeps `data` alongside `error`; the
plan refetches the open thread on every join ack and reconnect (decision 15).
The plan adds background refetches of the thread, and the panel's error branch replaces
the whole thread. A 5xx on a reconnect refetch would swap a loaded, readable thread for
"This thread isn't available.". This is the checklist's "an error branch that replaces a whole view". Decide
what an error over cached data shows. Keeping the thread fits the issue's "the channel is unaffected". A 404 on a
lost channel is already handled by `ChannelView`'s own error. Add a Vitest test for the case.

### 7. `optimistic()` is a `Message` literal the new required fields break — minor
**Where:** file map, `useMessages.ts` row · **Checked:** `useMessages.ts:175-190`.
Once `replyCount`/`lastReplyAt` are required in the generated type, `tsc` fails here until it sets
`0`/`null`. Add it to the row: `tsc` would catch it, but this is the ripple the map is for.

### 8. A reaction on the root while the panel is open — minor
**Where:** Task 6, "reactions likewise by `threadRootId`" · **Checked:** the plan's tests.
The panel's root shows reactions (R5). Say whether a `reaction_changed` with `threadRootId: null`
is also applied to `threadKeys.detail(ws, channelId, messageId)`, as top-level message events
are, and add a test of another user's reaction reaching the panel's root.

### 9. Unstated summary paths — minor
**Where:** Task 5 · **Checked:** `realtime_writes.py:260-298`.
The plan doesn't say whether the socket `delete_message` of a reply publishes the summary (the SPA
deletes over REST, so nothing user-visible depends on it today), or what summary the thread
route's `root` carries. One line each.

### 10. "Nothing is created" is checked through history, which never shows a reply — minor
**Where:** Task 2, refusal tests.
At red the message lands in history, so the test goes red. Once built, though, a refusal that had already
inserted a reply row would be invisible to "history length unchanged". Count `messages` rows, or
read the target thread, and check no `message_received` reaches the room.

## Left for later stages

- Findings 7–10, if the writer leaves any as minor.
- Decisions 21–25 are **assumed** and defensible; the human should read them, especially decision
  22 (counts can be wrong until the next refetch) and decision 23 (a 5xx shows as "not
  available").
- Task 9's merge with issue 2: `?message=` removed with `replace` must keep `thread`.

## Checked and sound

- Base commit `950e66a` = `git log -1`; baseline counts match `docs/test-report.md` at `d4be439c4307`.
- Decision 15: `partialMatchKey` (`utils.ts:248-266`) and `invalidateQueries` defaulting to
  `type: 'active'` (`queryClient.ts:291-311`) in installed 5.101.4. No global `staleTime`
  (`main.tsx`), so a reopen refetches.
- Ingress `/api/v1/messages` at `ingress.yaml:57`; no env, chart or compose change needed.
- `TABLES` truncation (`conftest.py:39`) and BDD truncation reach replies; `MessageIndexPayload`
  keeps new DTO fields out of the strict mapping.
- `_as_message` ripple: every caller, `test_indexing.py` lines included; `publish_reaction_changed`
  has one caller; `test_reactions.py:301-308` exact payload and `test_schema.py:142-152` named.
- Step phrases at `steps/conftest.py:37,44,54,119` verbatim; the journey's last step reads the
  thread from the server; `data-testid`s confined to the page object.
- `holdHistoryFetch` (`useChannelSocket.test.tsx:65`), `giveLayout`, `MessageComposer.tsx:18-22`
  exist as cited. `scripts/test.sh` accepts several layers.
- Workspace switch doesn't navigate (decision 24's premise holds); `ChannelView` shows its error
  and no panel on a 404.
- Expected reds in Task 1, and in Task 2 apart from finding 1, are what the runtime would report;
  the unrouted thread path 404s without the plan's detail.
- Shape: header, decisions split agreed/taken, corrections, file map with sweep, RED 1–3 before
  GREEN 4–7 with the test-reviewer gate, record task, verification naming lint/unit/integration/e2e,
  *Found while building* empty, no committing task, 484 lines, no 🔴 built on.
