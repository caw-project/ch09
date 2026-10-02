# Message threads — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Anyone who can see a channel can reply to a message in a single-level thread, shown in a
panel beside the channel, with each root's reply count and last-reply time kept live for everyone.

**Architecture:** Replies are `messages` rows with `thread_root_id` set, kept out of history, unread
and search by one predicate each. `replyCount`/`lastReplyAt` are aggregated per page in one grouped
query over a new partial index, exactly as reactions are. A new `GET /messages/{id}/thread` returns
the root and a cursor page of replies. A new `thread_summary_changed` event carries a root's
authoritative count to the channel room. The SPA keeps each thread in its own infinite query nested
under the channel's history key, routes every message event by `threadRootId`, and renders the
panel from `?thread=<rootId>` in place of `MemberPanel`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, python-socketio, pytest +
testcontainers · React 19, React Router 7, TanStack Query 5.101.4, Zustand, Vitest + MSW ·
pytest-bdd + Playwright.

**Issue:** `docs/plans/issue-3/00-issue.md` — read it first. This plan argues from it and does not
repeat it. R*n* below is the issue's requirement *n*.

**Worktree:** `../caw-issue-3`, branch `feature/issue-3`, from `main` at `950e66a`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R14; *Not in this issue* stays out |
| 2 | Depth | Single-level (D8a → 🟢 in this slice); a reply to a reply is filed under the root |
| 3 | Where replies are not | Channel history, unread, search results |
| 4 | A deleted root | Keeps its summary and its thread, and still takes replies; reply actions follow D8d/D39 |
| 5 | Where the panel lives | URL param `?thread=`, in place of `MemberPanel` |
| 6 | Broadcasts | The existing `channel:{id}` room; no new room or join |
| 7 | 🔴 entries | None blocks this (see below) |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 8 | Stored or aggregated counts | **Aggregated**: one grouped query per page (`threads.summaries_for`), like `reactions.summaries_for` | A stored counter needs `lastReplyAt` recomputed on every reply delete anyway, and two writers to keep in step. The reactions template (`c02dcd7`) is the house pattern. Alternative: `reply_count`/`last_reply_at` columns on the root |
| 9 | The summary event | `thread_summary_changed` → `{channelId, rootId, replyCount, lastReplyAt}` to `channel:{channelId}`, published on every reply create and every reply delete that tombstoned, **REST and socket alike**, with the summary **read after the commit** in a fresh transaction (READ COMMITTED), so the last writer to commit counts everyone committed before it | An idempotent set, safe from the ack, the echo and out of order (D39's reasoning). Alternative: re-broadcast the root `Message` — its `reactions[].reacted` is per caller, and a stale copy would revert a concurrent edit (`realtime.py:387-393`) |
| 10 | Reactions on a reply | `reaction_changed` gains `threadRootId` (`null` on a top-level message) | The client routes by it, as it does message events. Alternative: apply every reaction to every cached thread in the channel — a scan per event, and a cache writer that guesses |
| 11 | Refused root on send | **404 `"No such thread."`** for an unknown id or a root in any other channel; an invisible *path* channel stays 404 `"No such channel."` | A root in another channel answers exactly as an unknown id, so ids can't be probed (CH004). Alternative: 400 under `errors.threadRootId` — a client can't fix it by editing a field |
| 12 | `GET /messages/{id}/thread` on a reply | **404 `"No such thread."`**; unknown or invisible id → 404 `"No such channel."` as every message route | The caller can see the reply, so naming it leaks nothing; the distinct detail also lets the red tests tell "no route yet" from "refused". Alternative: one wording for all |
| 13 | `mark_read` naming a reply | **404 `"No such channel."`** (REST) / 404 ack (socket), marker unmoved | The same answer as a message from another channel: it isn't in this channel's history. Alternative: 409 |
| 14 | Thread response shape | `ThreadResponse = {root: Message, items: [Message], nextCursor}` | The panel needs the root even when it isn't in loaded history (*Paths*: old root, root from the URL), and one request is one loading state. Alternative: a second query on `GET /messages/{id}` |
| 15 | Thread query key | `['messages', ws, channelId, 'thread', rootId]` | Both join-ack invalidations use prefix `['messages', ws, channelId]`, which matches the nested key (`partialMatchKey`, `@tanstack/query-core/src/utils.ts:248-266`) and refetches it only while a panel observes it (`type: 'active'`, `queryClient.ts:300-308`). Checked in the installed 5.101.4 |
| 16 | `ix_messages_thread` migration | `0005_thread_index`: plain `CREATE INDEX … (thread_root_id, id) WHERE thread_root_id IS NOT NULL` | Every environment is pre-production and small. Alternative: `CONCURRENTLY` in an `autocommit_block` — worth it only once a table is big enough to lock writes noticeably |
| 17 | Panel width | `w-80` (20rem), `shrink-0`, `border-l` — wider than `MemberPanel`'s `w-64` | Replies carry reactions and an editor. Alternative: `w-64`, the same as the members |
| 18 | Thread drafts | A separate `threadDrafts: Record<rootId, string>` in `stores/chat.ts` | Keyed apart from `drafts[channelId]`, so R14 holds by construction. Alternative: `drafts['thread:'+rootId]` — one map, a prefix convention to remember |
| 19 | A root outside the channel (R7) | The panel checks `root.channelId !== channelId` and shows the notice | The thread route knows nothing of the URL's channel. Alternative: a `channelId` query parameter on the route — a second way to say a fact the row already holds |
| 20 | `upsertMessage` and replies | `upsertMessage` no-ops on any message with a `threadRootId` | R3's "not in the cache": the panel's edit, delete and reaction responses can't leak a reply into history either, whichever path writes. Alternative: the socket router alone guards |
| 21 | Normalising a deleted reply — **assumed** | A `threadRootId` naming a tombstoned reply files the new reply under that reply's root | The issue says "naming a reply" without exception, and R10 keeps deleted roots open. Changing it is one branch in `threads.root_for` and one test |
| 22 | Concurrent summaries out of order — **assumed** | Last arrival wins until the next refetch (join ack, reconnect, reopen) | Decision 9's after-commit read means every broadcast count is true when read, and the last to commit includes all before it. What remains: A reads 1 before B commits, B reads 2, and the pods deliver B's 2 before A's 1 — every window shows "1 reply" with 2 stored until a refetch. Needs two replies within the same few milliseconds on two pods; `reaction_changed` has the same window today (D39). Fixing it means a per-root sequence on the event and a client compare — an event field and one writer branch |
| 23 | A failed thread fetch — **assumed** | With **no data** (the first load: a 404, a 422 for a malformed id, a 5xx alike) the panel shows "This thread isn't available."; with data already loaded (a failed background refetch on reconnect or join ack) it **keeps showing the thread** and no notice | R7 names three causes, all first loads; the issue's "the channel is unaffected" argues against replacing a readable thread over a transient failure, and a channel lost meanwhile is `ChannelView`'s own 404, which drops the panel (decision 24). Separating a first-load 5xx into a retryable error later is one branch in `ThreadPanel` |
| 24 | Switching workspace — **assumed** | The panel closes because the old channel is a 404 under the new token, so `ChannelView` renders its error and no panel; the workspace leads the thread key, so no old thread is ever read | The SPA doesn't strip the URL on a switch today, and no other param is stripped either. Stripping `?thread` explicitly is a line in the switch handler |
| 25 | The panel composer offline — **assumed** | Disabled with the same "Not connected" notice the channel composer shows | The nearest case (`MessageComposer.tsx:18-22`). Changing it is a prop |
| 26 | The register | D8a → 🟢 with the date and the ADR; no new entry | D8a is the entry this work settles |
| 27 | The summary on every DTO | **A root's real summary wherever a `Message` is built from a stored row**: history and search (`summaries_for` over the page), get, edit, delete, reactions `_respond`, socket edit and delete, the thread route's `root` (`summary_for`); a reply anywhere, and any freshly sent message → `NO_REPLIES` | R4's "every message". A zero from an edit or a reaction would overwrite "2 replies" in every window through `message_edited`, as `test_an_edit_keeps_the_reactions` guards for reactions. Alternative: search results without a summary — a second rule for one DTO |
| 28 | History and an unknown id | History takes a new row **only from `message_received`** and its own sends. `message_edited`, `message_deleted`, `thread_summary_changed`, and the panel's edit, delete and reaction results go through a new **`replaceMessage`**, which replaces a row already cached and adds nothing | The panel works on a root not in loaded history (*Paths*); `upsertMessage` (`useMessages.ts:126-130`) would insert it as the newest message on every edit or echo. Also stops today's case of someone editing a message you haven't loaded. Alternative: an "is it loaded" check at each caller — five callers to keep honest. Existing tests keep passing: the edit-during-refetch test (`useChannelSocket.test.tsx:233`) edits a row that is cached |

Nothing here touches a 🔴 entry. Nearest: **D16** (tombstone retention) — a deleted root or reply is
a tombstone like any other and nothing here hard-deletes; **D29** (reindex) — replies stay in the
index, only hydration filters them, so no reindex is needed; **D28** (preferences) — nothing
per-user is stored; **D18** (notifications) — no thread notifications.

## Corrections to the issue

- **Doc 02 §3.1 marks `GET /messages/{id}/thread` "channel member".** The rule is visibility
  (§3.1.1), as on every message route — Task 8 corrects the row.
- **The issue's `reaction_changed` "has no `threadRootId`"** stays true of today's code; decision 10
  adds it, so *Where the rules meet* row 3 is met on the server rather than worked around.

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** A new capability a user sees, and only two browsers prove a
reply made in one shows its count live in the other and opens from the server. Everything under the
journey goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Ada replies; Grace, already watching, sees "1 reply" without reloading, opens the thread and sees the reply | **BDD** | `tests/bdd/features/threads.feature` |
| Root normalisation and refusal; what counts as a reply | unit | `messaging/tests/unit/test_threads.py` |
| Send with a root (REST and socket); refusals; history, unread, `mark_read` exclude replies; summaries count non-deleted replies, ride on every DTO path (decision 27) and are read after commit (decision 9); the thread route's paging and 404s; reply and summary broadcasts to the room only | integration | `messaging/tests/integration/test_threads.py` |
| Reactions carry `threadRootId` | integration | `test_reactions.py` (modify) |
| Search drops replies, keeps roots with their summary | integration | `test_search.py` (modify) |
| The partial index exists | integration | `test_schema.py` (modify) |
| Cache writers; event routing; send, ack and echo; paging; refetch; scroll; drafts; the menu action and summary; the URL; the bad thread | Vitest | see Task 3 |

**What no test covers:** that `ix_messages_thread` is *used* by the summary query (proven by
reading the migration and `EXPLAIN` in the first real run, not by a timing test); the cross-pod
ordering of decision 22; two replies' transactions really interleaving — the commit-order tests pin
the read after commit, which is what makes the interleaving harmless, without staging the race.

**Baseline**, from `docs/test-report.md` at `d4be439c4307`: Messaging unit 94 passed, integration
211 passed; frontend Vitest 243 passed; end-to-end 20 passed; lint passed. Expected counts are "N or
more", because issue 2 may land first.

## Global constraints

- Workspace from `wsp` only (CH001). A channel or message the caller can't see is a 404 with the
  wording in decisions 11–13, never a 403 (CH004).
- Plain `require_user` everywhere: nothing here is in Conventions §5.2's fail-closed set. Socket
  writes keep `principal_of` + `check_revoked` (`realtime_writes.py:132-159`).
- **Commit, then publish, then enqueue** (`indexing.py:3-5`). Publishers no-op when `sio is None`.
- Reply rows filter nothing on `deleted_at` in the thread route (tombstones are shown, R5); the
  summary counts `deleted_at IS NULL` only (R4).
- No new environment variable, compose or chart change. `/api/v1/messages` is already in
  `charts/collabhub/templates/ingress.yaml:57` (checked).
- Keep `MessageList.tsx`, `MessageItem.tsx`, `ChannelView.tsx` and `useChannelSocket.ts` diffs small
  (issue 2 overlaps them); the panel and its logic live in `src/frontend/src/features/threads/`.
- Vitest queries by role, label or text; `data-testid`s are for the BDD page object only.

## File map

Paths shortened: Python under `src/services/messaging/`, TypeScript under `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `tests/unit/test_threads.py` | create | the rules | 1 |
| `tests/integration/test_threads.py` | create | send, refusals, history, unread, summary, route, broadcasts | 2 |
| `tests/integration/test_reactions.py` | modify | `threadRootId` on the event — **its exact-payload test changes** (`:301-308`) | 2 |
| `tests/integration/test_search.py` · `test_schema.py` | modify · modify | replies out of search; the index **flips** `test_the_thread_index_is_deliberately_absent` (`:142-152`) | 2 |
| `tests/bdd/features/threads.feature` · `steps/test_thread_steps.py` · `pages/chat_page.py` | create · create · modify | the journey | 3 |
| `features/threads/*.test.ts(x)` · `lib/realtime/useChannelSocket.threads.test.tsx` · `features/channels/MessageItem.thread.test.tsx` · `ChannelView.thread.test.tsx` | create | the SPA's red | 3 |
| `features/channels/useMessages.test.ts` · `stores/chat.test.ts` · `test/factories.ts` | modify | reply guard, `replaceMessage`; thread drafts; `replyCount: 0, lastReplyAt: null` in `aMessage()` | 3 |
| `messaging/models.py` · `alembic/versions/0005_thread_index.py` | modify · create | `ix_messages_thread` | 4 |
| `messaging/threads.py` | create | rules, summaries, replies page | 4 |
| `messaging/messages.py` | modify | `create(…, thread_root_id=)`; `history_page` excludes replies | 4 |
| `messaging/schemas.py` | modify | `replyCount`, `lastReplyAt`, `ThreadResponse`, `SendMessageRequest.threadRootId`, `ThreadSummaryChanged` | 5 |
| `messaging/routers/messages.py` | modify | `_as_message(…, thread=)`; send with a root; the thread route; summaries on every DTO; summary publish on reply delete | 5 |
| `messaging/routers/reactions.py` · `routers/search.py` | modify | pass `thread=`; reaction event's `threadRootId` | 5 |
| `messaging/realtime.py` · `realtime_writes.py` | modify | `publish_thread_summary_changed`; `reaction_changed` field; socket send with a root; `_as_message` callers | 5 |
| `messaging/channels.py` · `read_state.py` · `search.py` | modify | unread, `mark_read`, hydration exclude replies | 5 |
| `tests/unit/test_indexing.py` | modify | `_as_message(…, reactions=[], thread=threads.NO_REPLIES)` at `:38,49,66,86,109,128` — **a signature ripple** | 5 |
| `src/frontend/openapi/messaging.json` · `types/messaging.ts` | regenerate | the contract | 5 |
| `lib/api/messaging.ts` | modify | `ThreadPage`, `getThread` | 6 |
| `features/threads/threadCache.ts` · `useThread.ts` | create | keys, writers, query, send, actions | 6 |
| `features/channels/useMessages.ts` | modify | `upsertMessage` ignores replies; new `replaceMessage` (decision 28); `ReactionEvent.threadRootId`; `optimistic()` (`:175-190`) sets `replyCount: 0, lastReplyAt: null` — a `Message` literal `tsc` rejects once the fields are required | 6 |
| `lib/realtime/useChannelSocket.ts` | modify | route by `threadRootId`; `thread_summary_changed` | 6 |
| `stores/chat.ts` | modify | `threadDrafts` | 7 |
| `features/threads/ThreadPanel.tsx` · `ThreadComposer.tsx` · `ThreadSummary.tsx` · `useThreadParam.ts` | create | the panel, composer, "N replies", the URL | 7 |
| `features/channels/MessageItem.tsx` · `MessageList.tsx` · `ChannelView.tsx` | modify | menu action + summary; pass `onOpenThread`; panel in the right column; export `STICK_THRESHOLD` | 7 |
| `docs/design/02-…` · `06-…` · `07-…` · `docs/adr/261002-single-level-threads.md` · `messaging/README.md` | modify · modify · modify · create · modify | the record | 8 |

Deliberately unchanged: `tests/bdd/conftest.py` and `tests/integration/conftest.py`'s `TABLES` —
replies are `messages` rows, already truncated. `indexing.py` — `MessageIndexPayload` picks its
fields (`indexing.py:59-67`), so the new DTO fields never reach the strict mapping. The Worker.

**Sweep results:** `git branch --no-merged main` — `feature/issue-2` is at `950e66a`, no code yet.
Stale "threads unbuilt" text: `models.py:150-170`, `schemas.py:235-241`, `realtime_writes.py:60-75`,
`0002_messages.py:22` (history, leave), `README.md:120-123`, `tests/integration/test_messages.py:58`
(comment), doc 02 `:52`, `:55`, `:253`, `:287-290`, `:404-419`, `:509`, `:639-643`, `:794-797`, doc 06
`:80-82`.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–3 | test-writer | failing unit, integration, BDD and Vitest tests, each failing for the reason given — **test-reviewer gate** |
| GREEN — backend | 4–5 | code-writer | Tasks 1–2 pass; the contract regenerated |
| GREEN — SPA | 6–7 | code-writer | Task 3's Vitest passes; `tsc` clean |
| Finish | 8–9 | code-writer | the record, then verification |

The SPA's red is written before the backend exists: its stubs follow Task 2's wire contract. Until
Task 5 regenerates `types/messaging.ts`, `tsc` is red for the same reason (`replyCount` unknown on
`aMessage()`, the thread path unknown to `messaging.get`) — expected, and not a test failure.

---

## Task 1: The rules (RED)

**Files:** `src/services/messaging/tests/unit/test_threads.py` (create)

**Interfaces** — produced for Task 4, in `messaging.threads`:
- `class NoSuchThreadError(Exception)`
- `@dataclass(frozen=True) class Summary: reply_count: int; last_reply_at: datetime | None`;
  `NO_REPLIES = Summary(0, None)`
- `is_reply(message: Message) -> bool` — `thread_root_id is not None`
- `root_for(candidate: Message | None, *, channel_id: uuid.UUID) -> uuid.UUID` — `None` or another
  channel raises `NoSuchThreadError`; a reply gives its `thread_root_id`; a root gives its `id`

| Test | Proves | Expected red |
|---|---|---|
| `test_a_root_is_its_own_thread` | root → own id | `ModuleNotFoundError: No module named 'messaging.threads'` (collection error for the file) |
| `test_a_reply_is_filed_under_its_root` | normalisation (R2) | same |
| `test_a_deleted_reply_still_names_its_root` | decision 21 | same |
| `test_a_deleted_root_still_takes_replies` | R10 | same |
| `test_an_unknown_root_is_refused` | `None` raises | same |
| `test_a_root_in_another_channel_is_refused` | channel mismatch raises; the same row with the matching `channel_id` is accepted in the same test | same |
| `test_is_reply` | both values | same |

Build rows with the unit conftest's `a_message` fixture; the reply's root is a *different* id from
the reply's own, so "returns `id`" and "returns `thread_root_id`" can't coincide. House docstring:
one line naming what breaks. Leave uncommitted.

## Task 2: The server's routes, SQL and broadcasts (RED)

**Files:** `tests/integration/test_threads.py` (create); `test_reactions.py`, `test_search.py`,
`test_schema.py` (modify)

**Interfaces** — the wire contract Tasks 3, 5 and 6 depend on:

```
POST /api/v1/channels/{channelId}/messages   body {body, threadRootId?: uuid|null}  → 201 Message
send_message                                 {channelId, body, threadRootId?}       → ack {ok, data: Message}
  refusals: path channel invisible → 404 "No such channel."; root unknown / other channel → 404 "No such thread."
GET  /api/v1/messages/{messageId}/thread?limit=&cursor=  → 200 ThreadResponse
  ThreadResponse = { root: Message, items: [Message] (replies, newest first, tombstones included), nextCursor }
  unknown or invisible → 404 "No such channel."; a reply → 404 "No such thread."
Message += { replyCount: int, lastReplyAt: datetime|null }   (both required; replies carry 0/null)
thread_summary_changed → { channelId, rootId, replyCount, lastReplyAt }   to channel:{channelId}
reaction_changed       += { threadRootId: uuid|null }
POST /api/v1/channels/{id}/read naming a reply → 404 "No such channel.", marker unmoved; mark_read ack likewise
```

Helpers follow `test_reactions.py:22-57` (`make_channel`, `send`, `connected`), plus a
`reply(client, headers, channel_id, root_id, body)` that posts `threadRootId`. Spread replies over
time (`created_at` differs per request) so first and last can't coincide.

| Test | Expected red |
|---|---|
| `test_a_reply_is_created_under_its_root` | `assert None == '<root id>'` — the field is ignored today |
| `test_a_reply_to_a_reply_is_filed_under_the_root` | same |
| `test_a_deleted_root_still_takes_replies` | same |
| `test_an_unknown_root_is_a_404_and_nothing_is_created` — detail `"No such thread."`; `SELECT count(*) FROM messages WHERE channel_id = :c` through the `engine` fixture is the same before and after (history never shows a reply, so it can't prove this) | `assert 201 == 404` |
| `test_a_refused_reply_reaches_no_one` — Grace joined; Ada's reply to an unknown root, then Ada's top-level `"anchor"`; Grace's **first** `message_received` is `"anchor"` | `assert '<reply body>' == 'anchor'` — today the reply is created and broadcast first |
| `test_a_root_in_another_channel_is_refused` | `assert 201 == 404` |
| `test_a_root_in_a_private_channel_you_cannot_see_answers_as_an_unknown_one` — Grace, public `#general` path, Ada's private root; body equals the unknown-root body | `assert 201 == 404` |
| `test_a_socket_send_takes_a_thread_root` · `test_a_socket_send_refuses_an_unknown_root` (ack `ok: False`, status 404, detail) | `None == root` · `assert True is False` |
| `test_a_reply_is_not_in_channel_history` — the root is, in the same response | reply body found in history |
| `test_a_reply_is_edited_and_reacted_to_under_its_root` (R9) — Ada's edit and Grace's reaction answer 200 with `threadRootId` = root; Grace's edit of it is 403 | `assert None == '<root id>'` |
| `test_a_root_reports_its_reply_count_and_last_reply_time` — 2 replies; `lastReplyAt` is the **second**'s `createdAt` | `KeyError: 'replyCount'` |
| `test_a_deleted_reply_is_not_counted` — delete the newer of 2; count 1, `lastReplyAt` the older's | `KeyError` |
| `test_a_message_with_no_replies_reports_zero_and_null` · `test_a_reply_reports_zero_and_null` | `KeyError` |
| `test_a_deleted_root_keeps_its_summary` — in history and in the delete response | `KeyError` |
| `test_an_edited_root_keeps_its_summary` (decision 27) — root with 2 replies, Grace joined; Ada's REST edit: response **and** Grace's `message_edited` payload both `replyCount: 2`, `lastReplyAt` the newer reply's | `KeyError: 'replyCount'` |
| `test_a_reaction_on_a_root_keeps_its_summary` — root with 1 reply; Grace's `POST …/reactions` response `replyCount: 1` | `KeyError` |
| `test_a_socket_edit_and_delete_of_a_root_keep_its_summary` — `edit_message` ack, then `delete_message` ack: both `replyCount: 1` | `KeyError` |
| `test_a_page_of_history_costs_one_summary_query` — 5 roots, each with a reply; the class-level `before_cursor_execute` listener `test_reactions.py:243-253` uses, recording only statements containing **`GROUP BY messages.thread_root_id`** (the history `SELECT` names `thread_root_id` too, so a bare-column filter would count it) | `assert 0 == 1` — nothing groups by it today |
| `test_a_reply_reads_its_summary_after_it_commits` (decision 9) — class-level listeners on `Engine` for `commit` (fires at `sqlalchemy/engine/base.py:1134-1136`, 2.0.51) and `before_cursor_execute` (the `GROUP BY` filter above) append `"commit"` / `"summary"` to one list, reset just before Ada's reply POST; assert `"summary" in events` and `events.index("summary") > events.index("commit")`. A build that counts before committing records `["summary", "commit"]` and fails | `AssertionError: assert 'summary' in ['commit']` |
| `test_a_socket_reply_reads_its_summary_after_it_commits` — the same over `send_message` (`serve` runs uvicorn on the test's own loop, `testkit/apps.py:44-50`, so the listener sees it) | same |
| `test_the_thread_returns_its_root_and_replies_newest_first` — `root.replyCount` is the reply count (decision 27) | `assert 404 == 200` |
| `test_the_thread_pages_by_cursor` (3 replies, `limit=2`) · `test_the_thread_shows_reply_tombstones` | `assert 404 == 200` |
| `test_a_reply_id_is_not_a_thread` — detail `"No such thread."` | detail mismatch: the unrouted 404 lacks it |
| `test_a_thread_you_cannot_see_is_a_404` (private channel, Grace) · `test_an_unknown_thread_is_a_404` — detail `"No such channel."` | detail mismatch, same reason |
| `test_replies_never_count_as_unread` — Grace: Ada's root + 2 Ada replies → `unreadCount` 1 | `assert 3 == 1` |
| `test_marking_a_reply_read_is_a_404_and_the_marker_stays` — mark root (204), then the newer reply | `assert 204 == 404` |
| `test_a_socket_mark_read_of_a_reply_acks_a_404` | `assert True is False` |
| `test_a_reply_and_its_summary_reach_the_room` — Grace joined; collect two events in either order: `message_received` (`threadRootId` = root) and `thread_summary_changed` `{channelId, rootId, replyCount: 1, lastReplyAt: <reply createdAt>}` | `socketio.exceptions.TimeoutError` waiting for the second event |
| `test_deleting_a_reply_broadcasts_the_lower_count` — `replyCount: 0, lastReplyAt: None` | `TimeoutError` |
| `test_a_socket_reply_broadcasts_the_summary` | `TimeoutError` |
| `test_a_socket_delete_of_a_reply_broadcasts_the_lower_count` — over `delete_message`; the same rule as REST (decision 9) | `TimeoutError` |
| `test_a_client_in_another_room_hears_neither` — after a positive receipt in the right room | `TimeoutError` on the positive half |
| `test_reactions.py::test_a_reaction_reaches_a_joined_client` — payload gains `"threadRootId": None` | dict mismatch |
| `test_reactions.py::test_a_reaction_on_a_reply_carries_its_thread_root` | dict mismatch (no key) |
| `test_search.py::test_a_reply_is_not_a_result_but_its_root_is` — index both via `index.index`; reply words → `[]`, root words → `[root]` | reply body found |
| `test_search.py::test_a_search_result_carries_its_summary` — a root with 2 replies found by its words: `replyCount: 2` (decision 27) | `KeyError` |
| `test_schema.py::test_the_thread_index_is_partial_on_thread_root_id` (replaces `…_deliberately_absent`) — definition holds `thread_root_id`, `id`, `WHERE (thread_root_id IS NOT NULL)` | `assert 0 == 1` rows |

Leave uncommitted.

## Task 3: The journey and the SPA's red (RED)

**Files:** BDD and Vitest files as the file map lists.

```gherkin
@bdd
Feature: Threads

  A reply that answers one message shouldn't push the rest of the channel out of
  view. Anyone who can see a channel can reply to a message in a thread: the
  replies sit in a panel beside the channel, and the message they answer shows
  how many there are and when the last one came, for everyone, as it happens.

  Background:
    Given Ada is signed in

  Scenario: Grace sees Ada's reply in a thread without reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "who is on call tonight?" in "general"
    And Grace is looking at the "general" channel
    When Ada replies "I am" in the thread on "who is on call tonight?"
    Then Grace sees 1 reply on "who is on call tonight?" without reloading
    When Grace opens the thread on "who is on call tonight?"
    Then Grace sees "I am" in the thread
```

- Shared phrases verbatim from `steps/conftest.py:37,44,54,119`. The three new ones live in
  `test_thread_steps.py`; the count step is `parsers.re(r'Grace sees (?P<count>\d+) repl(?:y|ies) on
  "(?P<body>[^"]*)" without reloading')`.
- Page object (`ChatPage`), new methods: `reply_in_thread(body, reply)` (hover the channel item, click
  `thread-open`, fill `thread-composer-input`, click `thread-composer-send`, wait for a confirmed
  `message-item[data-pending='false']` with that text **inside `thread-panel`**); `has_reply_count(body,
  n)` (`thread-summary` inside the `message-list` item, `to_have_attribute("data-reply-count", n)`);
  `open_thread(body)` (click that `thread-summary`); `thread_has_message(text)` (scoped to
  `thread-panel`). Channel lookups for these go through `message-list`, because the panel's root
  shares the root's text.
- New `data-testid`s, set in Task 7: `thread-open`, `thread-summary` (+ `data-reply-count`),
  `thread-panel`, `thread-close`, `thread-unavailable`, `thread-composer-input`,
  `thread-composer-send`. Panel rows reuse `MessageItem`'s.
- Expected red: the steps bind (`--generate-missing` prints nothing); the scenario fails at
  `reply_in_thread` waiting for `thread-open`. It runs only in Task 9.

**Vitest.** MSW thread stub: `messaging.get('/api/v1/messages/{message_id}/thread', …)` returning
`{root, items, nextCursor}`. Hand-typed event: `ThreadSummaryEvent {channelId, rootId, replyCount,
lastReplyAt: string | null}`. Exports Task 6/7 provide: `threadKeys.detail(ws, channelId, rootId)`,
`upsertThreadMessage(qc, key, m)`, `removeThreadMessage(qc, key, id)`, `applyThreadReaction(qc, key,
event, myUserId)`, `applyThreadSummary(qc, ws, event)` in `features/threads/threadCache.ts`;
`replaceMessage(qc, key, m)` in `features/channels/useMessages.ts`;
`useThread(token, ws, channelId, rootId)` → infinite query whose `data` is `{root, replies}` (replies
oldest first), `useSendReply(socket, ws, channelId, rootId, userId)`,
`useThreadActions(token, ws, channelId, rootId, userId)` → `{edit, remove, toggleReaction}` in
`useThread.ts`; `ThreadPanel` props `{accessToken, workspaceId, channelId, rootId, userId, myRole,
onClose}`; `ThreadComposer` props `{workspaceId, channelId, rootId, userId}`; `MessageItem` gains
optional `onOpenThread?: () => void`; `useChatStore` gains `threadDrafts`, `setThreadDraft(rootId,
text)`, `clearThreadDraft(rootId)`. Accessible names: menu button **"Reply in thread"**; summary
button text **"1 reply"** / **"N replies"** then a `<time dateTime={lastReplyAt}>`; panel
`<aside aria-label="Thread">`; close button **"Close thread"**; replies scroller `role="log"
aria-label="Replies"`; textarea label **"Reply"**, button **"Send reply"**; notice text **"This thread
isn't available."** (straight apostrophe).

| File · test | Proves | Expected red |
|---|---|---|
| `threads/threadCache.test.ts` · `adds an unknown reply to the newest page once, applied twice` · `replaces the root on every page` · `does nothing when the thread is not cached` · `sets a summary in history and the open thread — root at 5, event 2, reads 2` · `a summary for a root not in history leaves history unchanged` (history holds another message, which is all it holds after; the open thread's root **is** updated in the same test) | writers (R8, decision 28) | `Failed to resolve import "./threadCache"` |
| `threads/threadCache.test.ts` · `applies a reply's reaction, lit for the actor only` | R9 | same |
| `lib/realtime/useChannelSocket.threads.test.tsx` · `a reply event goes to its thread and never into history` (history holds its top-level message unchanged) · `a reply for an uncached thread creates no entry and leaves history alone` · `edits and deletes of a reply reach the open thread` · `an edit of a root reaches history and the panel's root` · `an edit of a root not in loaded history reaches the panel and leaves history unchanged` (history holds one other message; after `message_edited` for the root, history is exactly that one, the panel's root has the new body) · `a reaction on a reply reaches the open thread` · `another user's reaction on the root reaches history and the panel's root` (`reaction_changed` with `threadRootId: null`, Grace's userId; both show the count, `reacted` false for Ada) · `thread_summary_changed sets, never adds` · `a reply arriving during a thread refetch survives it` (held fetch, as `holdHistoryFetch` `:65-87`) · `the join ack refetches the open thread` (render `useThread` beside the socket hook; count thread GETs: 2) | routing (R3, R8, *Paths* reconnect, decision 28) | `Failed to resolve import "../../features/threads/threadCache"` — every test needs it |
| `features/channels/useMessages.test.ts` · `upsertMessage ignores a reply` — a top-level message upserted in the same test is added · `replaceMessage replaces a cached row` · `replaceMessage adds nothing for an id not cached` (the same call with a cached id, in the same test, replaces it) | decisions 20, 28 | assertion: the reply is in `pages[0].items` · `TypeError: replaceMessage is not a function` ×2 |
| `threads/useThread.test.ts` · `root apart, replies oldest first` · `loads older replies with the cursor` · `a send shows at once as temp:, root count unchanged` · `ack first, then echo: once` · `echo first, then ack: once` (ack held with a promise responder) · `a refused send rolls back` · `send_message carries channelId, body and threadRootId` · `a fetch for thread A that lands after switching to B stays in A` · `a cached thread shows at once on reopen and is refetched; a reply made meanwhile appears` · `useThreadActions: deleting a reply tombstones it in the thread and leaves history alone` · `…reacting on the root writes the thread's root and the history's` · `…editing a root not in loaded history leaves history unchanged` (history holds one other message; the thread's root takes the new body) | R2, R5, R9, *Timing*, *Paths*, decision 28 | `Failed to resolve import "./useThread"` |
| `threads/ThreadPanel.test.tsx` · `root, then replies oldest first, then the composer` · `the panel's root has reactions, edit and delete, no summary, no Reply in thread` · `replies offer no Reply in thread` · `a deleted reply is a tombstone` · `scrolling to the top loads older replies and keeps the position` (`giveLayout`; `scrollTop` grows by the height added) · `your own reply scrolls to the bottom from far up` · `someone else's reply scrolls at a 79px gap` · `…and not at 80px` · `a reply leaves the channel's read state alone` (`readingChannelId` unchanged, no `mark_read` emitted, after the reply renders) · `a 404 shows the notice` · `a reply id (404) shows the notice` · `a root from another channel shows the notice` · `a failed refetch keeps the loaded thread` (decision 23: load, then `server.use` a 500 for the thread and `invalidateQueries`; wait until the query's `status` is `'error'`, **then** the reply is still shown and no notice — the test client has `retry: false`, `test/render.tsx:31`) · `the root deleted while open: tombstone shown, composer still sends` · `Close thread calls onClose` | R5, R7, R10, R13 | `Failed to resolve import "./ThreadPanel"` |
| `threads/ThreadComposer.test.tsx` · `a draft per root, apart from the channel's` (A typed, rerender on B, back to A; `drafts[channel]` untouched) · `Enter sends and clears; a refusal puts the text back` · `disabled while offline` | R14 | `Failed to resolve import "./ThreadComposer"` |
| `stores/chat.test.ts` · `thread drafts are per root and clearing one keeps the other` | R14 | `TypeError: setThreadDraft is not a function` |
| `channels/MessageItem.thread.test.tsx` · `a top-level message offers Reply in thread, which opens it` · `none on a pending message` · `…a deleted one` · `…a reply` · `"1 reply" and "2 replies" with the last time; nothing at 0` · `a deleted root shows its summary and it opens the thread` · `without onOpenThread: no summary, no action` | R1, R4 | `Unable to find role "button" and name "Reply in thread"` (the prop is ignored) — **every** test in the file asserts its positive first (below), so this is each test's red |
| `channels/ChannelView.thread.test.tsx` · `?thread= on load opens the panel in place of the members, for a root not in the loaded history` · `a reply arriving in the panel leaves the channel list's scrollTop where it was` (both scrollers given layout) · `opening A then B pushes: Back shows A, Back again closes` (a test-only `Back` button calling `navigate(-1)`) · `closing keeps other params (?message=) and Back does not reopen it` · `switching channel closes the panel` · `a bad thread leaves the history showing` · `a channel that 404s shows no panel, though its thread is cached` · `a new workspace shows no thread from the old one` | R6, R7, *Paths* | `Unable to find role "complementary" and name "Thread"` — each test first finds the panel open (below) |

**Guards carry their positive.** In `MessageItem.thread.test.tsx`, each "none on …" test renders
two items in one tree, both with `onOpenThread`: a confirmed top-level message, then the case
(pending, deleted, reply). It asserts the confirmed one's `within(...)` has **"Reply in thread"**
first, then that the case's has none. `without onOpenThread` renders a root with 2 replies twice,
once with the prop and once without, and asserts "2 replies" and the action in the first before
their absence in the second. In `ChannelView.thread.test.tsx`, `a channel that 404s…` opens
`?thread=<root>` with the channel answering, finds `complementary` "Thread", then switches the
channel stub to a 404 and invalidates, and asserts the panel gone and the channel error shown;
`a new workspace…` finds the panel open under workspace A before switching to B; `switching
channel` finds it open before the switch. `a bad thread` asserts the notice before the history.

Leave uncommitted.

## Task 4: The index and the rules (GREEN)

**Files:** `models.py`, `alembic/versions/0005_thread_index.py`, `threads.py`, `messages.py`

```python
# 0005_thread_index.py — revision "0005", down_revision "0004". Partial: top-level rows,
# almost all of the table, never enter it; (thread_root_id, id) serves the summary
# aggregate and the replies page's keyset alike.
op.create_index("ix_messages_thread", "messages", ["thread_root_id", "id"],
                postgresql_where=sa.text("thread_root_id IS NOT NULL"))
```

- [ ] The same `Index(...)` in `Message.__table_args__`; rewrite the comment at `models.py:163-170`.
- [ ] `threads.py` to Task 1's interface, plus `summaries_for(session, *, root_ids) -> dict[uuid,
  Summary]` (one `GROUP BY thread_root_id` with `count(*)`, `max(created_at)`, `deleted_at IS NULL`,
  `thread_root_id IN …`), `summary_for(session, *, root_id) -> Summary`, `replies_page(session, *,
  root_id, page) -> Page[Message]` (newest first, keyset on `id`, cursor `messages.HISTORY_CURSOR`,
  no `deleted_at` filter — a CH009 finding takes the waiver `messages.py` uses, naming the reason),
  and `resolve_root(session, *, channel_id, candidate_id) -> uuid` (`messages.get` + `root_for`).
- [ ] `messages.create(…, thread_root_id: uuid.UUID | None)` — required keyword, so both send paths
  say what they mean. `history_page` adds `Message.thread_root_id.is_(None)`.
- [ ] Task 1: 7 passed; `test_schema.py`'s index test passes. Leave uncommitted.

## Task 5: The routes, the filters and the broadcasts (GREEN)

- [ ] `schemas.py`: `MessageResponse.reply_count: int`, `last_reply_at: datetime | None` (no
  defaults — a default drops them from OpenAPI `required`, `schemas.py:62-65`);
  `ThreadResponse(CamelModel)`; `SendMessageRequest.thread_root_id: uuid.UUID | None = None`;
  `ThreadSummaryChanged(CamelModel)` {`channel_id`, `root_id`, `reply_count`, `last_reply_at`},
  dumped `mode="json", by_alias=True` so `lastReplyAt` is formatted exactly as on the DTO.
- [ ] `_as_message(row, *, reactions, thread: threads.Summary)` — required, for the reason
  `reactions` is (`routers/messages.py:97-100`). The value at every caller (decision 27):

  | Caller | `thread=` |
  |---|---|
  | `routers/messages.py` list (`:183`) | `summaries_for` over the page's ids, `.get(id, NO_REPLIES)` |
  | `routers/messages.py` `_one_with_reactions` (`:130` — get and edit) · delete (`:343`) | `summary_for(row.id)` unless `is_reply(row)` → `NO_REPLIES` |
  | `routers/messages.py` send (`:222`) · `realtime_writes.py:201` send | `NO_REPLIES` — nothing can reply to a row not yet committed |
  | `routers/reactions.py:_respond` (`:82`) | `summary_for(message.id)` unless a reply |
  | `routers/search.py:75` | `summaries_for` over the hydrated page (roots only after R12) |
  | `realtime_writes.py:253` edit · `:287` delete | as REST edit and delete |
  | the thread route | `root`: `summary_for(root.id)`; `items`: `NO_REPLIES` |
  | `tests/unit/test_indexing.py:38,49,66,86,109,128` | `threads.NO_REPLIES` |

- [ ] Send (REST and socket): after the channel guard, `threads.resolve_root` when `threadRootId` is
  set; `NoSuchThreadError` → `ProblemException.not_found("No such thread.")`. Build the reply's DTO
  before commit as today (`NO_REPLIES`), keep `root_id` as a local, **commit**, then — still in the
  same session, which begins a new transaction and so sees every reply committed so far —
  `summary_for(root_id)` (decision 9). Then publish `message_received`, then
  `publish_thread_summary_changed`, then enqueue. Reading after commit is the point: read before,
  two concurrent replies each count only themselves and both broadcast 1.
- [ ] Delete (REST **and** socket `delete_message`): when `deleted_now` and the row is a reply,
  the same after-commit `summary_for(thread_root_id)` and publish (decision 9).
- [ ] `GET /messages/{message_id}/thread` in `routers/messages.py`: `_visible_message`, then
  `is_reply` → 404 `"No such thread."`, then root DTO + `replies_page` with one reactions query.
- [ ] `channels._with_read_state`: `Message.thread_root_id.is_(None)` in the count.
  `read_state.mark_read`: a reply returns `None`. `search._hydrate`: `Message.thread_root_id.is_(None)`.
- [ ] `realtime.publish_thread_summary_changed(sio, *, channel_id, root_id, summary)`;
  `publish_reaction_changed(…, thread_root_id)` called with `message.thread_root_id`.
- [ ] Docstrings that said "no `threadRootId`" (`schemas.py:235-241`, `realtime_writes.py:60-75`).
- [ ] Regenerate: `uv run python -m messaging.openapi > src/frontend/openapi/messaging.json`, then
  `npm --prefix src/frontend run generate:api`. Task 2 passes (39 new tests); Messaging integration
  250 or more, unit 101 or more. Leave uncommitted.

## Task 6: The SPA's data layer (GREEN)

- [ ] `lib/api/messaging.ts`: `ThreadPage = components['schemas']['ThreadResponse']`,
  `getThread(token, messageId, cursor?)` in the file's `{data, error}` → throw shape.
- [ ] `threadCache.ts` to Task 3's exports. The cache is the raw `InfiniteData<ThreadPage>`; root
  lives on every page and is replaced on all of them; unknown replies prepend to `pages[0].items`;
  every writer no-ops on an absent entry (`useMessages.ts:102-105`'s rule).
  `applyThreadSummary` writes `replyCount`/`lastReplyAt` onto the root in
  `messageKeys.list(ws, channelId)` — **replace only**, never adding the root (decision 28) — and
  in the thread's own entry.
- [ ] `useThread.ts`: `useInfiniteQuery` on `threadKeys.detail`, `select` copies and reverses as
  `useMessages.ts:87` does. `useSendReply` mirrors `useSendMessage` (`useMessages.ts:212-253`):
  `temp:` row with `threadRootId: rootId`, 5 s timeout, remove-then-upsert, **no count bump**.
  `useThreadActions`: edit, delete and reaction write the thread entry; a root's result also goes
  through **`replaceMessage`** on the history key (decision 28).
- [ ] `useMessages.ts`: `upsertMessage` returns `cached` untouched for `message.threadRootId !==
  null`; `replaceMessage(qc, key, m)` — `upsertMessage`'s replace branch alone, `cached` untouched
  when the id isn't there; `optimistic()` sets `replyCount: 0, lastReplyAt: null`;
  `ReactionEvent.threadRootId: string | null`. `useEditMessage`/`useDeleteMessage`/`useToggleReaction`
  stay on `upsertMessage` — their row is in history by construction.
- [ ] `useChannelSocket.ts`: message events with `threadRootId` go to the thread key only (with
  `reapplyAfterFetch` on that key). A top-level event goes to history — `message_received` through
  `upsertMessage`, **`message_edited` and `message_deleted` through `replaceMessage`** (split
  `onMessage` in two) — **and** replaces the root in `threadKeys.detail(ws, channelId,
  message.id)`. Reactions route the same way: `threadRootId` set → that thread only; `null` →
  history and the root's own thread entry (finding 8). `live.on('thread_summary_changed', …)` →
  `applyThreadSummary`. Join-ack invalidations are unchanged — the prefix reaches the thread
  (decision 15).
- [ ] Task 3's cache, socket and hook tests pass. Leave uncommitted.

## Task 7: The panel (GREEN)

- [ ] `stores/chat.ts`: `threadDrafts`, `setThreadDraft`, `clearThreadDraft`.
- [ ] `useThreadParam()` → `{threadId, openThread(id), closeThread()}` over `useSearchParams`: open
  sets `thread` and pushes; close deletes `thread` only and passes `{replace: true}`.
- [ ] `ThreadSummary`: `<button data-testid="thread-summary" data-reply-count={n}>` "1 reply" / "N
  replies" + `<time>`; renders nothing at 0.
- [ ] `MessageItem`: with `onOpenThread`, a "Reply in thread" button (`thread-open`) in the hover menu
  when not deleted, not pending, `threadRootId === null`; `ThreadSummary` under the body — **also on
  a tombstone** (R1, R10).
- [ ] `MessageList`: optional `onOpenThread?: (rootId: string) => void`, passed per row; `export`
  `STICK_THRESHOLD`. No other change.
- [ ] `ThreadPanel` (`<aside aria-label="Thread" data-testid="thread-panel" className="w-80 …">`):
  header, close (`thread-close`); notice (`thread-unavailable`) when the query has errored **and
  holds no data**, or the root is foreign — an error over loaded data keeps the thread (decision 23); root
  `MessageItem` without `onOpenThread`; replies scroller (`role="log"`) with its own anchoring on
  prepend and stick rule — own reply always, others' when `< STICK_THRESHOLD` measured before the
  render; then `ThreadComposer`. It never calls `setReadingChannel` or `useMarkRead`.
- [ ] `ThreadComposer` mirrors `MessageComposer` over `threadDrafts[rootId]` and `useSendReply`
  (`thread-composer-input`, `thread-composer-send`).
- [ ] `ChannelView`: `useThreadParam()`; right column is `ThreadPanel` (keyed by `rootId`) when
  `threadId` is set, else `MemberPanel`; `MessageList` gets `onOpenThread={openThread}`.
- [ ] Task 3's Vitest passes (65 new tests): frontend 308 or more. `npm --prefix src/frontend run typecheck`
  clean. Leave uncommitted.

## Task 8: The record

- [ ] Register: D8a → 🟢 *Single-level, built 2026-10-02*, with the ADR link; the "Built against it"
  text replaced.
- [ ] ADR with the `adr-writer` skill: *single-level threads, kept out of channel history, unread and
  search* — alternatives "also send to channel", replies counted as unread, replies searchable now.
- [ ] Doc 02: §3.1 rows (`:52`, `:55` visibility, send takes `threadRootId`); §3.1.3 DTO with
  `replyCount`/`lastReplyAt` and `ThreadResponse`, `SendMessageRequest`; §3.1.5 drop the thread row;
  §3.1.6 hydration drops replies; §3.1.7 unread excludes replies, `mark_read` refuses one; §3.2
  `send_message` row, `thread_summary_changed`, `reaction_changed.threadRootId`; §3.2.4 the
  paragraph at `:639-643`; §4 the index comment at `:794-797` and the threading paragraph.
- [ ] Doc 06: §3 `/features/threads` exists; §5.2 a *Threads — added 2026-10-02* block: the panel,
  `?thread=` push/replace, the key, event routing, scroll rules, drafts.
- [ ] `messaging/README.md:120-123`; `test_messages.py:58` comment. Sweep `grep -rn "D8a\|unbuilt\|
  ix_messages_thread" docs/design src/services/messaging` for anything still saying threads don't
  exist. Leave uncommitted.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each once; green, counts
  at or above baseline. `-- -k threads` only to iterate on a failure.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; a waiver names every checker that fires on its line.
- [ ] **First real run** on Compose (`docker compose up -d --build`), the issue's *Acceptance* list,
  plus `EXPLAIN` of the summary query showing `ix_messages_thread`. Expect it to find something the
  tests didn't; fix it with a test and record it below.
- [ ] If `feature/issue-2` merged meanwhile: merge `main`, keep `?message=` and `?thread=` both on
  `/c/:channelId` (issue 2's `replace` must not drop `thread`), rerun all of the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Round 1, code-writer:

1. **`_as_message(…, thread=)` defaults to `NO_REPLIES`** instead of being required (Task 5). The
   approved `tests/unit/test_indexing.py` still calls `_as_message(…, reactions=[])` and the test
   pair did not update it; a required keyword fails six existing tests. Every stored-row caller
   passes `thread=` explicitly (list, get/edit, delete, reactions, search, socket edit/delete). No
   test pins "forgotten `thread=`"; making it required is a one-word change once those six calls
   say `thread=threads.NO_REPLIES`.
2. **`ReactionEvent.threadRootId` is optional** in the SPA (Task 6 said `string | null`). Two
   existing tests (`useMessages.test.ts` `event()` helper, `useChannelSocket.test.tsx`) build and
   emit reaction events without it; an event without it is read as top-level. Pinned by those tests.
3. **`useThreadActions` returns mutations** `{edit, remove, toggleReaction}` as the red report read
   it, and the reaction is optimistic with rollback (it uses `userId`, which the tests pass).
4. **Helpers exported from `useMessages.ts`** so the thread layer does not copy them:
   `optimistic` (gained a `threadRootId` argument), `emitSend` (the socket send, shared by both
   composers), `mergeReaction`, `predictReaction`; and `LOAD_THRESHOLD` beside `STICK_THRESHOLD`
   from `MessageList.tsx`. `threadCache.ts` adds `setThreadReactions` for the rollback.
5. **`publish_reply_summary` / `summary_of`** live in `routers/messages.py`, shared by the REST
   routes and `realtime_writes.py`, rather than inline in each.
6. **`openapi/messaging.json` was edited by hand to the generator's output**, because this session
   could not redirect `python -m messaging.openapi` into a file. The edits are the schema and path
   additions only; **re-run `uv run python -m messaging.openapi > src/frontend/openapi/messaging.json`
   and confirm no diff** (listed for the human).
7. **Send-back** to the test-writer: `threadCache.test.ts:152` types the history cache with a
   required `nextCursor`, which the generated `MessagePage` doesn't have, so `tsc` and `npm run
   build` fail on a test file (see `reviews/code-writer-sendback-3.md`). No production change fixes it.
8. **Not done**: the comment at `tests/integration/test_messages.py:58` (a test file), and the first
   real run on Compose with `EXPLAIN` — nothing ran while the build is blocked by 7.

## Not in this issue

- Opening a reply from search; following threads, a threads view, thread unread or notifications
  (D18); "also send to channel"; nested replies; typing in threads.

## Self-review

- **Issue coverage:** R1 → Tasks 3, 7 · R2 → 1, 2, 3, 4, 5, 6 · R3 → 2, 3, 4, 6 · R4 → 2, 3, 5, 7 ·
  R5 → 2, 3, 5, 6, 7 · R6 → 3, 7 · R7 → 2, 3, 5, 7 · R8 → 2, 3, 5, 6 · R9 → 2, 3, 6 · R10 → 1, 2, 3,
  7 · R11 → 2, 5 · R12 → 2, 5 · R13 → 3, 7 · R14 → 3, 7. *Where the rules meet*: response/echo →
  `useThread.test` both orders; socket vs history → `useChannelSocket.threads.test`; reaction on a
  reply → decision 10, Task 2 and 3; reply deleted → Task 2 broadcast, Task 3 tombstone; root
  edited/deleted while open → `ThreadPanel.test`, `useChannelSocket.threads.test`; unread → Task 2;
  search → Task 2; `?message=` beside `?thread=` → `ChannelView.thread.test` and Task 9. *Paths*:
  each row has a named Vitest test in Task 3, except "a second tab" (the room reaches every
  connection — Task 2's room test) and reload (`?thread= on load`).
- **Names:** `thread_summary_changed` everywhere; `ThreadResponse.items`; `threadKeys.detail`;
  `"No such thread."` vs `"No such channel."` as decisions 11–13 say.
- **Known ripple:** `_as_message`'s new keyword (`test_indexing.py`, three routers, the socket
  writes); `test_reactions.py`'s exact payload; `test_schema.py`'s absent-index test; `tsc` red
  between Task 3 and Task 5; `optimistic()`'s literal; `onMessage` split so edits and deletes
  only replace (decision 28).

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** The listener records only statements containing `GROUP BY messages.thread_root_id`,
   which the history `SELECT` never has; 5 roots each with a reply, so an N+1 reads 5. Red is
   `assert 0 == 1`, because nothing groups by that column today.
2. **Fixed.** A *Guards carry their positive* paragraph under Task 3's table. Every `MessageItem`
   "none on …" test renders a confirmed top-level message beside its case and finds its action
   first. `without onOpenThread` renders with and without the prop. The 404, workspace and
   channel-switch tests find the panel open before the change. So each file's stated red is now
   every test's red.
3. **Fixed.** Decision 27, and Task 5 has a table giving the `thread=` value for every
   `_as_message` caller, search and the thread root included. New tests:
   `test_an_edited_root_keeps_its_summary` (REST response and `message_edited` payload),
   `test_a_reaction_on_a_root_keeps_its_summary`,
   `test_a_socket_edit_and_delete_of_a_root_keep_its_summary`,
   `test_search.py::test_a_search_result_carries_its_summary`.
4. **Fixed.** Decision 28: a new `replaceMessage` replaces an existing row and adds nothing.
   History takes new rows only from `message_received` and its own sends. Socket
   `message_edited`/`message_deleted`, `applyThreadSummary`'s history write and the panel's results
   go through `replaceMessage`. Tests: two in `useMessages.test.ts`; `an edit of a root not in loaded
   history…` in the socket file; `…editing a root not in loaded history leaves history unchanged`
   in `useThread.test`; `a summary for a root not in history…` in `threadCache.test`.
5. **Fixed.** Decision 9: the summary is read after commit, in the same session's next
   transaction. Task 5 gives the order. Two tests pin it by recording `commit` and the aggregate in
   sequence (REST and socket), with the SQLAlchemy event source cited. Decision 22 now names what is
   left, delivery order across pods, and what the user sees.
6. **Fixed.** Decision 23 is rewritten: the notice shows only for an error with no data, and a
   failed refetch over a loaded thread keeps it. Task 7 says the same. New test: `ThreadPanel.test`
   `a failed refetch keeps the loaded thread`.
7. **Fixed.** `optimistic()` is in the file-map row and in Task 6.
8. **Fixed.** A `reaction_changed` with `threadRootId: null` goes to history and to the root's own
   thread entry (Task 6). Test: `another user's reaction on the root reaches history and the panel's
   root`.
9. **Fixed.** Socket `delete_message` of a reply publishes the summary (decision 9, Task 5); test
   `test_a_socket_delete_of_a_reply_broadcasts_the_lower_count`. The thread route's `root` carries
   `summary_for` (Task 5's table), and `test_the_thread_returns_its_root_and_replies_newest_first`
   asserts it.
10. **Fixed.** The unknown-root test counts `messages` rows through the `engine` fixture. New
    `test_a_refused_reply_reaches_no_one` checks the room's first event is a later top-level
    anchor.
