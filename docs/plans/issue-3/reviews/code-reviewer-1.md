# Code review — issue 3, round 1: send_back

**Verdict: send_back.** The build matches the plan almost line for line, and every check I could
run is green. One major bug isn't covered by any approved test:
- `thread_summary_changed` is the only live event that isn't re-applied after a history fetch in
  flight.
- A probe shows a root's new count being overwritten by a stale refetch.

That goes to the test pair first (D32), in `code-reviewer-sendback-4.md`. Two more majors are the
code-writer's to fix when the work comes back:
- Doc 02 §3.1.6 and §3.1.7 still describe search and unread without the reply exclusions.
- The committed test report has no integration layer.

## Expectations                 (round 1 — written before the code was opened)

**Task 4 — index and rules.**
- Not pinned: the model's `Index(...)` mirrors the migration (only the migration is tested by
  `test_schema`); `0005` downgrade drops the index; `models.py` comment rewritten. `replies_page`
  carries a CH009 waiver *with a reason*. `messages.create` takes `thread_root_id` as a required
  keyword.
- Takes for granted: `messages.get` returns tombstoned rows (else a deleted root/reply can't be
  resolved — R10 and decision 21). The integration test for a deleted root catches the root half;
  nothing catches a deleted *reply* used as `threadRootId` beyond the unit test of `root_for`.
- Could go wrong: `summaries_for` aliasing/labelling the group-by (fails tests, not a bug);
  forgetting `deleted_at IS NULL` in the count (pinned); `max(created_at)` vs `max(id)` (both fine).
  `replies_page` keyset direction and cursor reuse of `HISTORY_CURSOR` (pinned by paging test).
- Wrong build: `resolve_root` called *after* `messages.create` → row created then refused; pinned
  by the row-count test (REST and socket).

**Task 5 — routes, filters, broadcasts.**
- Not pinned: `ThreadSummaryChanged` dumped `mode="json", by_alias=True` (string compare pins format
  on REST; socket less so); `publish_reaction_changed` passing `message.thread_root_id` (pinned);
  docstrings at `schemas.py`/`realtime_writes.py` updated; `_as_message(thread=)` required — the
  writer recorded it defaulted (departure 1), so a forgotten `thread=` at any caller silently gives
  `NO_REPLIES`. I must check every caller in the decision-27 table passes it, including the socket
  edit/delete and search.
- Takes for granted: `expire_on_commit=False` so the reply DTO built pre-commit doesn't lazy-load;
  the session's next statement after `commit()` opens a new transaction (READ COMMITTED). The
  summary publish happens on *every* path that tombstones a reply: REST delete, socket delete — and
  only when `deleted_now` (else a re-delete re-broadcasts, harmless). A channel admin deleting
  someone else's reply takes the same path.
- Could go wrong: socket send resolving the root before the channel visibility check (leaks
  existence with "No such thread." vs "No such channel."); the summary published before
  `message_received` or before commit; an exception in the summary read after commit making the
  request 500 though the reply is committed; `mark_read` refusing a reply only on REST but not on
  socket (both pinned); unread filter added but another count over `messages` left (only
  `_with_read_state` counts at HEAD — fine). Search hydration filtering replies but the search
  router's summary lookup still run over the pre-filter ids (harmless). Thread route on a *deleted
  root* must still answer 200 (R10) — `_visible_message` does not filter tombstones at HEAD.
- Wrong build: summary read inside the send transaction (pinned by commit-order tests); summary on
  edit/delete of root zeroed (pinned for REST edit, socket edit/delete, reaction, delete).
  Unpinned: REST **get** of a root carrying its summary? (`test_a_reply_reports_zero_and_null` only
  checks a reply) — read `_one_with_reactions`.

**Task 6 — SPA data layer.**
- Not pinned: `useSendReply`'s 5 s timeout (test-reviewer-2 noted); `reapplyAfterFetch` on the
  thread key for reply events (one test, `a reply arriving during a thread refetch`); top-level
  `message_received` also replacing the root in its thread entry; `ReactionEvent.threadRootId`.
- Takes for granted: the join-ack invalidation of `['messages', ws, channelId]` reaches the nested
  thread key (decision 15; pinned by `the join ack refetches`). The thread `select` copies before
  reversing. `isFetching({queryKey, exact: true})` on the thread key.
- Could go wrong: a top-level `message_edited`/`message_deleted` for a root routed via
  `upsertMessage` instead of `replaceMessage` (pinned); `applyThreadSummary` adding the root to
  history (pinned); the panel's own reply-row edit/delete going through the channel hooks
  (`upsertMessage` ignores replies → the panel would not update until the echo). The reaction
  rollback on a reply. `upsertMessage` guard written as `threadRootId != null` vs `!== null` with
  `undefined` from old fixtures. A `thread_summary_changed` for another channel written to the open
  channel's history (handler must key on `event.channelId`).
- Wrong build: `useSendReply` bumping `replyCount` optimistically (pinned).

**Task 7 — the panel.**
- Not pinned: panel `w-80 shrink-0 border-l`; `data-testid`s for the BDD page object (only the
  journey checks them); `useThreadParam` close deleting only `thread` with `replace`; the panel
  keyed by `rootId` in `ChannelView` (state from thread A leaking to B: scroll anchors, the
  "measured before render" ref); load-older guard `hasNextPage && !isFetchingNextPage`; composer
  disabled offline (pinned); drafts cleared on send and restored on refusal (pinned).
- Takes for granted: the panel's root reaches it even when not in history (thread route returns
  it); `MessageItem` renders the summary only with `onOpenThread` (so the panel root shows none).
- Could go wrong: the stick rule measured *after* the new row renders (would always read the gap
  as > 80); own-reply detection on the `temp:` row vs the confirmed one; the scroll anchor applied
  on a refetch that replaces pages (not a prepend) jumping the view; the panel calling
  `setReadingChannel`/`useMarkRead`; foreign root check missing on a cached thread under a new
  channel. Opening the already-open thread pushes a duplicate history entry (Back does nothing).
  Switching workspace with `?thread=` still in the URL — decision 24 relies on the channel 404.
- Wrong build: summary hidden on a tombstoned root (pinned); "Reply in thread" on a reply (pinned).

**Task 8 — the record.** Register D8a 🟢 dated 2026-10-02 linking the ADR; ADR with the three
alternatives; doc 02 rows (thread route visibility, `threadRootId` on send, DTO fields,
`ThreadResponse`, `thread_summary_changed`, `reaction_changed.threadRootId`, index created,
exclusions from history/unread/search, `mark_read` refusal); doc 06 `/features/threads` and §5.2
block; README. Stale "unbuilt" text gone from `models.py`, `schemas.py`, `realtime_writes.py`.

**Task 9 — verification.** `docs/test-report.md` at this tree's revision `-dirty` showing lint, unit,
integration and **e2e** with the `threads` journey passed; `openapi/messaging.json` equal to the
generator's output (it was hand-edited — departure 6).

## What ran

**Checks**

| Check | Result |
|---|---|
| `npm --prefix src/frontend test` | 34 files, **316 passed** |
| `npm --prefix src/frontend run typecheck` | clean |
| `npm --prefix src/frontend run lint` | clean |
| `npm --prefix src/frontend run build` | built (376.62 kB JS) |
| `uv run pytest src/services/messaging/tests/unit` | **102 passed** |
| `uv run pytest src/services/messaging/tests/integration` | **250 passed** in 80.7 s; no flake this time |
| `uv run ruff check src/services/messaging` | all checks passed |
| `conventions.py` over every changed or new messaging and BDD Python file | no findings |

**Evidence from `scripts/test.sh`**
- `docs/test-report.md` is at `950e66a2d292-dirty`. Lint passed; unit 646 (messaging 102,
  frontend 316). End-to-end 21 of 21 passed, *Threads: Grace sees Ada's reply in a thread without
  reloading* among them.
- `build/test-results/e2e.xml` names the thread scenario.
- Integration shows **⚪ not run** (finding 3).

**Mutants** (sketch; each reverted before the next)

| File | Change | Tests run | Outcome |
|---|---|---|---|
| `ThreadPanel.tsx` | drop `!thread.isFetchingNextPage` from the load-older guard | `ThreadPanel.test` | **survived** |
| `ThreadPanel.tsx` | drop the own-reply clause from the stick rule | `ThreadPanel.test` | caught (`your own reply scrolls…`) |
| `useThreadParam.ts` | close with `replace: false` | `ChannelView.thread.test` | caught (`closing keeps other params…`) |
| `ChannelView.tsx` | `ThreadPanel` not keyed by `threadId` | `ChannelView.thread`, `ThreadPanel` | **survived** |
| `useChannelSocket.ts` | reply events applied without the re-apply after a thread fetch | `useChannelSocket.threads.test` | caught (`a reply arriving during a thread refetch…`) |
| `threads.py` | `root_for` without the channel check | unit `test_threads.py` | caught (`…another_channel_is_refused`) |

**Probes**
- `useChannelSocket.ts`, real code: hold a history fetch, emit `thread_summary_changed`
  (count 1), then land the fetch read before the reply (count 0). **Failed**:
  `expected +0 to be 1`. The control (no fetch in flight) passed. This is finding 1.
- `openapi/messaging.json` against `messaging.openapi.document()`: the parsed JSON is **equal**.
  The text differs in two characters: a raw `—` (line 320) and a raw `§` (line 1449), where the
  generator writes `—` and `§`.
- `sketch.sh clean` was run, and `build/sketch` is gone.

I skipped Python integration mutants. Every backend wrong build in my *Expectations* is pinned by
an integration test I read, and all 250 pass.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T4 index (migration + model), `downgrade` | `0005_thread_index.py`, `models.py:167-176` | as planned |
| T4 `threads.py` interface, `summaries_for` unaliased `GROUP BY`, `replies_page` keyset, waiver with reason | `threads.py` | as planned |
| T4 `create(thread_root_id=)` required; `history_page` excludes replies | `messages.py` | as planned |
| T5 schemas: required `replyCount`/`lastReplyAt`, `ThreadResponse`, `SendMessageRequest.threadRootId`, `ThreadSummaryChanged` | `schemas.py` | as planned |
| T5 `_as_message(thread=)` required | defaulted to `NO_REPLIES` | departed (Found 1; the reason holds, and every stored-row caller passes it — grep of all 11 call sites) |
| T5 decision 27 table, every caller | list, get/edit (`_one_with_reactions`), delete, reactions, search, socket edit/delete, thread root | as planned |
| T5 send: channel guard, then `resolve_root`, then create, commit, publish received, then summary, then enqueue (REST and socket) | `routers/messages.py:253-285`, `realtime_writes.py:180-218` | as planned |
| T5 delete of a reply: after-commit summary on `deleted_now` (REST and socket) | both | as planned |
| T5 thread route: visibility, then `is_reply` 404, then one reactions query | `get_thread` | as planned |
| T5 unread, `mark_read`, search hydration filters | `channels.py`, `read_state.py`, `search.py` | as planned |
| T5 `reaction_changed.threadRootId` | `realtime.py:408` | as planned |
| T5 regenerate OpenAPI and types | JSON hand-edited, content equal | departed (Found 6; two characters escaped differently) |
| T6 `getThread`, `ThreadPage` | `lib/api/messaging.ts` | as planned |
| T6 `threadCache` writers no-op on absent; summary to history via `replaceMessage` | `threadCache.ts` | as planned |
| T6 `useThread` select copies, then reverses; `useSendReply` 5 s timeout, no count bump | `useThread.ts`; timeout through the shared `emitSend` | as planned (Found 4) |
| T6 `upsertMessage` ignores replies; `replaceMessage`; `optimistic()` fields | `useMessages.ts` | as planned |
| T6 routing by `threadRootId`, split `onMessage`, reactions to history and the root's thread | `useChannelSocket.ts` | as planned |
| T6 `thread_summary_changed` → `applyThreadSummary` | no re-apply after a fetch | as planned, **but wrong** (finding 1) |
| T7 drafts, `useThreadParam` (push / replace + delete only `thread`), `ThreadSummary`, `MessageItem` guards, `MessageList` export, `ThreadPanel` (`w-80`, notice rule, scroll, no read state), `ThreadComposer`, `ChannelView` keyed panel | all present | as planned |
| T8 register, ADR, doc 06, README | present and accurate | as planned |
| T8 doc 02 §3.1.6, §3.1.7 | unchanged | **missing** (finding 2) |
| T9 `scripts/test.sh lint unit integration` and e2e; conventions; first real run | lint, unit and e2e in the report; integration run directly, not through the script; no first real run | departed (finding 3; the real run is under *Left for the human*) |

## Findings

### 1. A reply's summary is lost when it lands during a history refetch — major
**Where:** `src/frontend/src/lib/realtime/useChannelSocket.ts`, the `thread_summary_changed`
handler · **Checked:** a probe against the real code fails (*What ran*).

Every other live event goes through `applyAndReapply`, for the reason the file's header gives. The
summary is set and then overwritten by a refetch that read the root before the reply. The
join-ack refetch on every channel open, and every reconnect, open that window. Grace then sees
Ada's reply in a thread but no "1 reply" on its root until something refetches, against R8.

No approved test covers it, so it goes back to the test pair (`code-reviewer-sendback-4.md`).
The fix is one handler: re-apply over the history key and the root's thread key.

### 2. Doc 02 still describes search and unread without the reply exclusions — major
**Where:** `docs/design/02-messaging-service.md` §3.1.6 (lines 448-454) and §3.1.7 (lines
476-488) · **Checked:** read against `search._hydrate`, `channels._with_read_state` and
`read_state.mark_read`.

Plan Task 8 names both sections, and the code now does something they don't say:
- **§3.1.6** says hits are hydrated with "`deleted_at IS NULL` and the visible channel filter". It
  should also say that replies are dropped (R12), and that this is one more reason a page can be
  short.
- **§3.1.7** defines unread as every message after the marker that someone else wrote and that
  isn't deleted. Replies are now excluded from that.
- **§3.1.7** says "the message must be in that channel". A reply in that channel is now a 404
  "No such channel." too.

Today the reply rules are stated only in §3.2.4 and §4. That is where the next person editing
search or unread won't look.

**Fix:** a sentence in each bullet.

### 3. The committed test report has no integration layer — major
**Where:** `docs/test-report.md` · **Checked:** read the report; ran the layer myself.

Plan Task 9 asks for `scripts/test.sh lint unit integration`. The report shows Integration
"⚪ not run", and the green report's 250 come from a direct `uv run pytest`. I reran it: 250 pass,
so the claim holds. But CLAUDE.md makes this report the feedback until CI exists, and for this
branch it shows nothing for the layer that proves every SQL and broadcast rule here.

**Fix:** rerun `scripts/test.sh integration` once the code is final, so the report shows it at
this revision.

## Unpinned

These are behaviours no test holds, so only reading protects them:
- **The load-older guard `!thread.isFetchingNextPage`** (mutant survived). It is present in the
  code. Without it, TanStack's `fetchNextPage` cancels and restarts an in-flight page, and
  `heightBeforePrepend` is re-recorded. So it's wasteful, but the anchor stays right.
- **`key={threadId}` on `ThreadPanel`** (mutant survived). It is present. Without it, switching
  from A to B would carry A's `previousCount` and stick state into B, and B could open without
  scrolling to its newest reply.
- **The 5 s ack timeout for replies** sits in the shared `emitSend`, which `useMessages.test.ts`
  pins (4999 ms / 1 ms) for the channel send. The thread send uses the same function.
- **`deleted_now` gating the reply-summary broadcast.** Without it, a repeat delete would re-send
  the same count, which is harmless. The code has it on both transports.
- **The socket `mark_read` of a reply** doesn't re-read the marker. `read_state.mark_read`
  returns `None` before the upsert for both transports.

## Left for the human

- **Minor: the OpenAPI escaping.** Run `uv run python -m messaging.openapi >
  src/frontend/openapi/messaging.json`. The content is already equal; the diff will be the two
  escaped characters.
- **Minor: a stale *Found while building* item.** Item 8 in the plan says nothing ran "while the
  build is blocked by 7". It has run since, so the item should say what is still not done: the
  first real run and `EXPLAIN`.
- **Minor: opening the thread that is already open pushes a second history entry**, so the first
  Back appears to do nothing. One `if (params.get('thread') === rootId) return` would fix it.
- **Minor: a failed `fetchNextPage` leaves `heightBeforePrepend` set.** The next reply to arrive
  is then treated as a prepend, which shifts the scroll by its height. To fix it, clear the ref
  when the fetch errors.
- **Minor: the REST reply's summary is read after the commit.** If that read fails, the request
  answers 500 for a reply that is stored, and a client retry would post it twice. This is the
  plan's design, decision 9, and nothing tests it.
- **The first real run** on Compose: the issue's *Acceptance* list, plus `EXPLAIN` of the summary
  query showing `ix_messages_thread`.
- **Issue 2's merge:** keep `?message=` and `?thread=` together.
- **The assumed decisions 21 to 25** are for you to read, as the plan-reviewer listed them.

## Checked and sound

- The SQL and data rules:
  - Tenancy comes from `wsp` throughout. No 403 for a hidden root; the 404 wording follows
    decisions 11 to 13.
  - The send path refuses before it creates anything, on REST and on the socket.
  - There is no `OFFSET`: `replies_page` is a keyset on `id`.
  - The CH009 waiver gives its reason.
- The commit, publish and enqueue order is right on all four write paths. The summary is read
  after the commit, inside the same session (socket) or request session (REST).
- Decision 27: every one of the 11 `_as_message` call sites passes the right summary. The REST
  get of a root carries its summary through `_one_with_reactions`.
- Decision 20 and 28: `upsertMessage` ignores replies. Edits and deletes from the socket, and the
  panel's results for a root, go through `replaceMessage`. The routing covers the reaction on a
  root as well as on a reply.
- `MessageItem`:
  - "Reply in thread" shows only on confirmed, live, top-level rows.
  - The summary shows on tombstones too, and only with `onOpenThread`, so the panel's root has
    none.
- `ThreadPanel` never touches `setReadingChannel` or `useMarkRead`. It shows the notice only with
  no data, or for a foreign root.
- The register (D8a 🟢 with the ADR), the ADR's three alternatives plus the stored-columns
  option, doc 06 §3 and §5.2, and the README all match the code.
- Nothing changed outside the file map. The test files that changed are the test pair's, as the
  red report lists.
