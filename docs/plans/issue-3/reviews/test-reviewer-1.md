# Test review — issue 3, round 1: changes_requested

The red is real almost everywhere: 41 of 41 backend tests and 30 of 30 Vitest tests fail for the reasons the report
gives, and the one green test is green by design. Two Vitest tests, though, cannot pass against a correct build
(I sketched one and ran it), and one passes a plausible wrong build. Each fix is a few lines in a test file.

## Expectations

Written from the issue, the plan and plan-reviewer-2, before opening any test.

**Rules (unit, `test_threads.py`).** Today: `ModuleNotFoundError: messaging.threads`, collection error.
Vacuous: `root_for` returning `candidate.id` always (passes if the reply fixture's root id equals its own id) or
never checking channel; the channel-mismatch test passing because `None` is also refused. Wrong build: a
deleted reply refused (decision 21); a deleted root refused (R10). Must pin: reply ≠ root ids, mismatch refused
and the same row accepted with the matching channel.

**Send with a root (integration).** Today `threadRootId` ignored → 201 with `threadRootId` null. Vacuous: "nothing
created" checked via history; refusal test that passes on a 404 for the wrong reason (missing route/channel) — must
assert detail `"No such thread."`; private-root test passing because Grace can't see the *path* channel. Wrong build:
create then check; refuse unknown but not other-channel; reply-to-reply stored with the reply as root.

**History/unread/mark_read/search exclusion.** Vacuous: unread test where Grace's own replies are excluded anyway
(the existing "written by someone else" guard) — replies must be Ada's; history test without the root present as a
positive; mark_read test that doesn't show the marker unmoved after a successful root mark. Wrong build: filter only
in history not in unread; filter on `deleted_at`.

**Summary.** Vacuous: one reply (first == last), counting deleted, summary only on history not on edit/delete/
reaction/search/get/thread-root DTOs (decision 27) — the paths where a zero would overwrite "2 replies". Per page
one grouped query (N+1 wrong build) and read after commit (read-before-commit wrong build).

**Broadcast.** Vacuous: negative half ("reaches no one", "other room hears neither") without a positive; summary
event on create only, not on delete or socket delete; `reaction_changed` missing `threadRootId`.

**Index.** Flip of the absent-index test: must check partial predicate, not mere existence.

**SPA.** Cache writers: summary *set* not added (root at 5, event 2); replace-only for a root not in history; reply
never in history via the socket router *and* `upsertMessage`; response/echo in both orders (held ack); reaction on a
reply reaching the panel; join-ack refetch of thread (counting GETs); held-fetch race. Panel: order, tombstones,
paging keeping position (needs `giveLayout`), stick threshold at 79/80 px, own reply always; failed refetch keeps
thread; notice for 404/reply/foreign. URL: push on open, replace on close, other params kept, switching channel
closes. Menu: guards need their positive. Drafts per root. Fake socket / timers: 5 s ack timeout if tested.

**Journey.** Phrases verbatim, steps bind, last Then after Grace's reload-free count then the thread opened from the
server.

Wrong builds to sketch (frontend): upsert reply into history; add to count rather than set; stick on every
reply / never; own reply not scrolling; thread key outside the `['messages', ws, channelId]` prefix; drafts shared.

## What ran

- `uv run pytest …/unit/test_threads.py` → collection error, `ImportError: cannot import name 'threads' from 'messaging'`,
  as the report says (all 8 tests need it).
- `uv run pytest …/integration/{test_threads,test_reactions,test_schema,test_search}.py` → **41 failed, 42 passed**.
  The 41 are the 36 new in `test_threads.py`, 2 in `test_reactions.py`, 1 in `test_schema.py`, 2 in `test_search.py`;
  the 42 are existing tests. Matches the report. I did not re-read each first line; the failing set matches the report's table.
  Backend red-for-the-right-reason is reasoned from the code, not sketched (a service sketch needs containers).
- `npm --prefix src/frontend test` → **30 failed, 244 passed**, 9 files failed (4 at load: `threadCache`, `useThread`,
  `ThreadPanel`, `ThreadComposer` — every test in each needs the module). Matches the report. The one green new test is
  `a top-level event still goes to history`.
- `uv run pytest tests/bdd --collect-only -q` → 21 collected, including the thread scenario;
  `--generate-missing` → no stub: every step binds. Page-object helpers `_holds`, `_settle_messages` exist.
- **Sketch, frontend, correct** (`threadCache`, `useThread`, panel, composer, summary, socket routing, `ChannelView`
  param, `MessageItem`/`MessageList` props): 99 of 101 of the new and changed tests green; the two reds are findings 1
  and 2. Finding 2 goes green when the stub's reply ids are stable (sketch-only edit); finding 1 fails with the extra request
  shown below.
- **Sketch, wrong builds** (each run over the files that should catch it):
  no re-apply of a reply after a thread refetch → `useChannelSocket.threads` red (caught);
  summary added instead of set → red in `useChannelSocket.threads` and `threadCache` (caught);
  `message_edited` through `upsertMessage` (inserts an unloaded root) → red (caught);
  panel always sticks / sticks only for own / never for others → red at 80px / 79px / own (all caught);
  **error replaces a loaded thread → green (finding 3)**;
  thread composer on the channel's draft → red (caught);
  "Reply in thread" on pending, deleted and reply rows → red (caught);
  no channel check on the panel's root → red (caught);
  ack without removing the `temp:` row → red, both orders (caught);
  reaction on a reply routed by `threadRootId` ignored → red (caught);
  open with `replace` → red; close with `push` → red (caught; the first is also hit by finding 2).
- `.claude/delivery/sketch.sh clean` run. `git status --short` shows only the writer's files.

## Coverage

| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| Task 1 rules, 7 | `tests/unit/test_threads.py`, 7 + `NO_REPLIES` | present |
| Task 2 send, refusals, history, unread, mark_read, summary, route, broadcasts, reactions, search, schema | all named tests | present; reds match |
| Summary on every DTO (decision 27) | history, delete, edit (+ event), reaction, socket edit/delete, search, thread root, reply zero | present |
| Commit-then-summary (REST + socket), one grouped query | `recorded_events`, `GROUP_BY` listeners | present |
| Task 3 `threadCache`, socket routing, `useMessages`, `useThread`, `ThreadPanel`, `ThreadComposer`, store, `MessageItem`, `ChannelView` | all named | present — see findings 1–3 |
| BDD journey | `threads.feature` + steps + page object | present; steps bind; runs only in Task 9 |
| Departures | tests that avoid a load failure in the socket and `ChannelView` files; `aThreadPage`; mutation-shaped `useThreadActions` | accepted: each has a stated reason and is sound |

## Findings

### 1. `scrolling to the top loads older replies` counts a request a correct panel makes — critical
**Where:** `features/threads/ThreadPanel.test.tsx` line 167 · **Checked:** ran it in the correct sketch; printed the paths.
`renderPanel` stubs `auth.members(...)`, and that stub records its request in `requests()`. A panel that names its
authors through `useWorkspaceMembers` (it must: `MessageItem` takes `authorName`, and the test's own stub exists for
that) makes a members GET, so the assertion sees `[members, thread, thread]` →
`expected [ null, null, 'older' ] to deeply equal [ null, 'older' ]`. A correct build can't pass it. Filter to the thread
path, e.g. `requests().filter((r) => r.url.pathname.endsWith('/thread'))`, as `ChannelView.thread.test.tsx:268` does.

### 2. `opening A then B pushes: Back shows A…` races the plan's own refetch — critical
**Where:** `ChannelView.thread.test.tsx`, `replyTo` (line 73) used inside the thread handler (lines 92-97) ·
**Checked:** ran it. The correct sketch fails at line 197 (`element could not be found in the document`). With a
sketch-only change that makes `replyTo` return the same row for the same body, the file passes 8 of 8.
The handler builds `aMessage(...)` — a fresh id — on every request. On Back, thread A is cached and refetched (the
plan's *Paths* row 2 requires both), so the refetch swaps the reply for one with a new id; the row re-keys and the node the
test just found is detached. Any build that follows the plan fails or flakes here. Make the stub's replies stable
(create each reply once, outside the handler).

### 3. `a failed refetch keeps the loaded thread` passes the build it exists to catch — major
**Where:** `ThreadPanel.test.tsx` lines 264-277 · **Checked:** ran a wrong build, `unavailable = q.isError` (the notice
replaces a loaded thread). The test **passed**. With a 100 ms `act` flush added after the `vi.waitFor` (sketch only) it
fails, as it should.
The `waitFor` resolves the moment the query cache reads `error`, before React has re-rendered, so the "no notice"
assertion is read before the notice could appear. It is the shared list's *wait on the last effect*. After the status wait,
flush the render (a short timer inside `act`, or wait for something only a re-render shows) and keep the positive
assertion that the reply is still on screen.

## Left for later stages

Minor, for the code pair:
- `ThreadPanel.test › a reply leaves the channel's read state alone` can't tell a panel that sets `readingChannelId` to the
  same channel from one that doesn't (the report says so). The `mark_read` half does catch a `useMarkRead` in the panel.
- `ChannelView.thread › switching channel closes the panel` is satisfied by any build: the sidebar link carries no params,
  so the URL closes the panel. Fine as a pin of the behaviour; it proves nothing about the code.
- `test_a_socket_mark_read_of_a_reply_acks_a_404` doesn't re-read the marker as its REST twin does.
- No test pins the 5 s ack timeout for `useSendReply` (plan Task 6 asks for it), nor a non-author deleting a reply (R9).
- The `thread_summary_changed` payload is compared against `createdAt` as strings. The code-writer should emit the same
  formatting (the report already says so).
- `useThreadActions` returns mutations, not functions: if the code-writer builds functions, send back (the report's departure).

## Checked and sound

- Every backend test is red for the missing behaviour, with the first line the report gives; the refusal tests assert
  the `detail`, so a missing route can't pass them.
- Guards carry their positive: unread (root counted, replies Ada's), history (root present), search (root found), mark_read
  (root marked 204 first), unknown-root (row count) and "refused reaches no one" (anchor), other-room (positive receipt).
- Summary: two replies at different times; last is the second; delete the newer; the page's single grouped query; after-commit.
- Existing tests: no existing assertion was removed or loosened; the two the plan changes (`test_a_reaction_reaches_a_joined_client`,
  the index test) are changed as the plan says. 244 frontend tests pass: the baseline 243 plus the one green by design.
- The report matches the tree: every changed file is listed or in the plan's file map; no code, config or docs written.
