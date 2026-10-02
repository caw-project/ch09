# Red tests — issue 3, round 1

BDD outside-in, as the plan recommends: one journey (`threads.feature`) over unit, integration and
Vitest tests. 1 unit file, 1 new integration file plus 3 modified, 1 scenario, and 7 new Vitest files
plus 3 modified. **Every new test fails for the reason the plan gives, except one deliberate green**
(see *Departures*). The BDD scenario cannot run here; it parses and every step binds.

## Baseline
Run before changing anything.

| Files | Before | After |
|---|---|---|
| `test_reactions.py` + `test_schema.py` + `test_search.py` (integration) | 44 passed | 42 passed, 5 failed (the 2 new in `test_search.py`, 1 new + 1 changed in `test_reactions.py`, 1 replacing `…deliberately_absent` in `test_schema.py`) |
| `useMessages.test.ts` + `chat.test.ts` (Vitest) | 28 passed | 28 passed, 4 new failed |
| Full Vitest suite | 243 passed (docs/test-report) | 244 passed, 30 failed, 4 files fail to load |

Every existing test still passes. The two existing tests the plan said change: `test_a_reaction_reaches_a_joined_client`
(payload gains `"threadRootId": None`, now red) and `test_the_thread_index_is_deliberately_absent`
(replaced by `test_the_thread_index_is_partial_on_thread_root_id`).
Python totals now: `test_threads.py` 36 failed · `test_reactions.py` 2 failed · `test_schema.py` 1 failed ·
`test_search.py` 2 failed · unit `test_threads.py` collection error (8 tests).

## Tests
Observed red is the first line of the failure.

| File · test | Layer | Task | Proves | Observed red | Match |
|---|---|---|---|---|---|
| unit `test_threads.py` (8 tests: root own thread, reply to root, deleted reply, deleted root, unknown, other channel with the matching channel accepted in the same test, `is_reply`, `NO_REPLIES`) | unit | 1 | the rules | `ImportError: cannot import name 'threads' from 'messaging'` (collection error; every test needs it) | yes (ImportError, not `ModuleNotFoundError`, because `messaging` exists) |
| int `test_threads.py::test_a_reply_is_created_under_its_root`, `…reply_to_a_reply…`, `…deleted_root_still_takes_replies`, `test_a_socket_send_takes_a_thread_root` | int | 2 | send with a root, normalisation | `AssertionError: assert None == '<root id>'` | yes |
| `test_an_unknown_root_is_a_404_and_nothing_is_created`, `…root_in_another_channel…`, `…private_channel…answers_as_an_unknown_one` | int | 2 | refusals, CH004 | `assert 201 == 404` | yes |
| `test_a_refused_reply_reaches_no_one` | int | 2 | refused reply is never broadcast | `assert 'into the void' == 'anchor'` | yes (plan quoted the body generically) |
| `test_a_socket_send_refuses_an_unknown_root`, `test_a_socket_mark_read_of_a_reply_acks_a_404` | int | 2 | socket refusals | `assert True is False` | yes |
| `test_a_reply_is_not_in_channel_history` | int | 2 | R3 | `assert ['I am', 'who is on call tonight?'] == ['who is on call tonight?']` | yes |
| `test_a_reply_is_edited_and_reacted_to_under_its_root` | int | 2 | R9 | `assert None == '<root id>'` | yes |
| `test_replies_never_count_as_unread` | int | 2 | R11 | `assert 3 == 1` | yes |
| `test_marking_a_reply_read_is_a_404_and_the_marker_stays` | int | 2 | R11 | `assert 204 == 404` | yes |
| `test_a_root_reports_…`, `test_a_deleted_reply_is_not_counted`, `test_a_message_with_no_replies…`, `test_a_reply_reports_zero_and_null`, `test_a_deleted_root_keeps_its_summary`, `test_an_edited_root_keeps_its_summary`, `test_a_reaction_on_a_root_keeps_its_summary`, `test_a_socket_edit_and_delete_of_a_root_keep_its_summary` | int | 2 | R4, decision 27 | `KeyError: 'replyCount'` | yes |
| `test_a_page_of_history_costs_one_summary_query` | int | 2 | one grouped query per page | `AssertionError: []` (`assert len(statements) == 1, statements`) | same cause as the plan's `assert 0 == 1`; message differs |
| `test_a_reply_reads_its_summary_after_it_commits`, `test_a_socket_reply_…` | int | 2 | decision 9 | `AssertionError: ['commit']` (`'summary' in events`) | yes |
| `test_the_thread_returns_its_root_and_replies_newest_first`, `…pages_by_cursor`, `…shows_reply_tombstones` | int | 2 | the route | `AssertionError: {"type":…not-found…"/thread"…}` — the `assert response.status_code == 200, response.text` message; status is 404 | yes |
| `test_a_reply_id_is_not_a_thread`, `test_a_thread_you_cannot_see_is_a_404`, `test_an_unknown_thread_is_a_404` | int | 2 | the route's 404 wording | `KeyError: 'detail'` — the unrouted 404 has no `detail` | yes ("detail mismatch") |
| `test_a_reply_and_its_summary_reach_the_room`, `test_deleting_a_reply_broadcasts_the_lower_count`, `test_a_socket_reply_broadcasts_the_summary`, `test_a_socket_delete_of_a_reply_broadcasts_the_lower_count`, `test_a_client_in_another_room_hears_neither` | int | 2 | broadcasts | `socketio.exceptions.TimeoutError` waiting for the second event | yes |
| `test_reactions.py::test_a_reaction_reaches_a_joined_client`, `…on_a_reply_carries_its_thread_root` | int | 2 | decision 10 | dict mismatch / `KeyError: 'threadRootId'` | yes |
| `test_search.py::test_a_reply_is_not_a_result_but_its_root_is`, `…carries_its_summary` | int | 2 | R12, decision 27 | reply body found / `KeyError: 'replyCount'` | yes |
| `test_schema.py::test_the_thread_index_is_partial_on_thread_root_id` | int | 2 | the index | `assert 0 == 1` (no row) | yes |
| BDD `threads.feature` — 1 scenario | BDD | 3 | the journey | cannot run; see *BDD* | — |
| `threadCache.test.ts` (8 tests) · `ThreadPanel.test.tsx` (14) · `useThread.test.ts` (13) · `ThreadComposer.test.tsx` (5) | Vitest | 3 | writers, panel, data layer, composer | `Failed to resolve import "./threadCache"` / `"./ThreadComposer"` — every test in each needs it | yes |
| `useChannelSocket.threads.test.tsx` — 10 tests | Vitest | 3 | routing | `AssertionError: expected [] to deeply equal [ … ]` (reply not in thread) · `expected 'I am' to be 'I am, until nine'` · `expected +0 to be 2` (summary) · `Cannot find module '…/threads/useThread'` (join-ack test only) | **differs from the plan's load failure, deliberately** — see *Departures* |
| `useMessages.test.ts` — `upsertMessage ignores a reply` · `replaceMessage` ×2 | Vitest | 3 | decisions 20, 28 | `expected [ …3 items ] to deeply equal [ …2 ]` · `TypeError: replaceMessage is not a function` ×2 | yes |
| `chat.test.ts` — thread drafts | Vitest | 3 | R14 | `TypeError: setThreadDraft is not a function` | yes |
| `MessageItem.thread.test.tsx` — 8 tests | Vitest | 3 | R1, R4 | `Unable to find role "button" and name "Reply in thread"` for the action tests; `Unable to find … name /^1 reply/` (or `/^2 replies/`) for the summary tests | yes (plan-review minor 1: summary tests' red is the summary) |
| `ChannelView.thread.test.tsx` — 8 tests | Vitest | 3 | R6, R7 | `Unable to find role="complementary" and name "Thread"` · `Unable to find … name /^1 reply/` (the two tests that open a thread by its summary) · `Unable to find an element with the text: This thread isn't available.` (`a bad thread`) | yes (plan-review minor 1) |

## Types
`tsc` errors, all of the kinds the plan expects before Tasks 5–6: the missing modules
`./threadCache`, `./useThread`, `./ThreadPanel`, `./ThreadComposer`; `ThreadPage` not exported from
`lib/api/messaging`; `replyCount`/`lastReplyAt` unknown on `Message` (so `aMessage()` and every literal);
`'/api/v1/messages/{message_id}/thread'` not in the generated `paths`; `replaceMessage` not exported;
`threadDrafts`/`setThreadDraft`/`clearThreadDraft` not on `ChatState`; `threadRootId` not on `ReactionEvent`;
`onOpenThread` not a `MessageItem` prop. Five `TS7006 'm' implicitly any` in `useThread.test.ts` follow from
the missing `ThreadPage` type and disappear with it. Nothing else.

## BDD
`uv run pytest tests/bdd --collect-only -q` → 21 tests collected, including
`test_thread_steps.py::test_grace_sees_adas_reply_in_a_thread_without_reloading`.
`uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` → no stub printed: every step binds.

Expected red: the scenario passes its Background and Givens (shared steps), then fails at
`When Ada replies "I am" in the thread on "who is on call tonight?"` — `ChatPage.reply_in_thread` hovers the
root and waits for `thread-open`, which does not exist (Playwright timeout on the locator). Later steps would
stop at `thread-summary` (`data-reply-count`) and `thread-panel`. It runs only in Task 9.

## Departures from the plan
- **Added tests** (each needed by a requirement or to give a guard its positive): unit `test_no_replies_is_zero_and_never`;
  `threadCache.test.ts`: `replaces a reply where it sits…`, `removeThreadMessage drops…`, `goes down as well as up…`,
  `applies a reaction on the root to the root on every page`; `useChannelSocket.threads`: `a top-level event still goes to
  history` (see next); `MessageItem.thread`: `opens the thread when clicked`; `ThreadComposer`: `the Send reply button sends too`.
- **One test is green by design:** `useChannelSocket.threads.test.tsx › a top-level event still goes to history…`. It is
  the positive half for "a reply never goes into history" (a build that drops every message event would pass the others).
  This is why the suite is 244 passed, one above baseline.
- **`useChannelSocket.threads.test.tsx` and `ChannelView.thread.test.tsx` do not import `threadCache` / `useThread`.**
  The plan expects a whole-file load failure, but most tests there are about routing or the URL, so a load failure would
  hide the real red. They use the plan's key `['messages', ws, channelId, 'thread', rootId]` as a literal (decision 15) and write
  the thread cache by hand (`setQueryData`). The join-ack test imports `useThread` dynamically through a variable path, so
  only it fails with `Cannot find module`.
- **`aThreadPage(root, items, nextCursor)`** added to `src/test/factories.ts` beside `aMessagePage` (the plan names only the
  `replyCount: 0, lastReplyAt: null` change); it imports the type `ThreadPage` that Task 6 adds to `lib/api/messaging`.
- **The `useThreadActions` return shape** is under-specified (`{edit, remove, toggleReaction}`). The tests treat each as the
  mutation its sibling hook is: `edit.mutate({messageId, body, version})`, `remove.mutate(messageId)`,
  `toggleReaction.mutate({message, emoji})`, and read `.isSuccess`. If the code-writer builds functions, this is the one place
  to say so in a send-back.
- `ThreadPanel`'s "a reply leaves the channel's read state alone" test sets `readingChannelId` before rendering and asserts
  it is unchanged and no `mark_read` was emitted; it cannot distinguish a panel that sets it to the same value.
- `test_a_page_of_history_costs_one_summary_query` asserts the statement count before the `replyCount`s, so its red is the count.

## Picked up from earlier reviews
`plan-reviewer-2` *Left for later stages*:
- **Minor 1** (stated reds for `MessageItem.thread` / `ChannelView.thread`): the table above gives the real failures.
- **Minor 2** (the `GROUP BY messages.thread_root_id` filter depends on how the aggregate renders): see *For the code-writer*.
- **Decision 28 changes today's insert-on-edit:** `useMessages.test.ts` has no existing test that relied on it; the one
  edit-during-refetch test edits a cached row and still passes.
- Assumed decisions 21–25 are tested as written (21 in unit and integration; 23 `a failed refetch keeps the loaded thread`; 24 the workspace test; 25 `is disabled…`).

## For the code-writer
- **Keep the summary aggregate unaliased and grouped by `messages.thread_root_id`** (`.group_by(Message.thread_root_id)`). Three tests
  record statements containing exactly `GROUP BY messages.thread_root_id`; an alias or label fails a correct build.
- **`commit` then summary:** the two commit-order tests register class-level `Engine` listeners for `commit` and
  `before_cursor_execute`, reset around the reply request; the summary statement must come after the first `commit`.
- `lastReplyAt` on `thread_summary_changed` and on the DTO must be the **same string** as the reply's `createdAt`
  (the tests compare strings).
- The thread route's `items` carry `replyCount: 0` for replies; a reply's tombstone has `body == ""` and `deletedAt`.
- `thread_summary_changed` and `message_received` may arrive in either order; the tests take them by name.
- Frontend: tests use `getByRole` only — names `Reply in thread`, `1 reply`/`N replies` (button text begins with the count,
  then a `<time dateTime>`), `Thread` (aside), `Close thread`, `Replies` (`role="log"`), `Reply` (textarea), `Send reply`, the
  notice `This thread isn't available.`, and the offline text containing `Not connected`.
- `ThreadPanel` scroll tests: the stick rule reads geometry at the time of the new reply (after the last `scroll` event); older replies
  are loaded from a scroll event at `scrollTop < 120` as `MessageList` does, and `scrollTop += scrollHeight − before` after the prepend
  (the test's `scrollHeight` is 100 × the number of `article`s in the scroller).
- `ChannelView.thread` tests open a thread by clicking the root's summary in the channel list, so `MessageList` must pass `onOpenThread`
  and the summary must show for roots in history. They give the channel list's scroller its layout through the parent of a row outside the
  panel's `aside`.
- `ThreadPanel`'s root row must be a `MessageItem` (an `article`) before the replies, with the replies scroller `role="log"`.
- `ThreadComposer` takes no `accessToken` (plan props); its send is `send_message` with `{channelId, body, threadRootId}` exactly.

## Review responses (round 3 — code-writer-sendback-3)
- **Typing fault, `threadCache.test.ts` line 152:** fixed. The inline cache type is now `InfiniteData<MessagePage>` (imported from `lib/api/messaging`), and the assertion at line 160 uses it too. `npm run typecheck` is clean and `threadCache.test.ts` passes 10 of 10 against the built code. Types only; no assertion changed.
- **Minor, `test_indexing.py` `thread=` keyword:** left. The defaulted `NO_REPLIES` keeps the six calls valid; requiring it is optional.
- **Minor, "threads unbuilt" comment in `test_messages.py:58`:** left for a later stage; it is a comment only.
