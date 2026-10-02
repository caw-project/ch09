# Plan review — issue 3, round 2: approved

All ten round-1 findings are fixed in the plan, and none of the fixes breaks anything beside it.
I checked each fix against the code and against the installed SQLAlchemy 2.0.51 and TanStack
Query. The fixes raise no new critical or major finding. Two minor points about stated reds,
and the assumed decisions, go to the stages after.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. One-summary-query test passes at red | The listener filters on `GROUP BY messages.thread_root_id`; red is `assert 0 == 1` | **resolved**. The history `select(Message)` has no GROUP BY. The listener pattern matches `test_reactions.py:243-253`. A `.group_by(Message.thread_root_id)` renders exactly that string (see minor 2) |
| 2. Guard tests with no positive | The *Guards carry their positive* paragraph; each guard renders a confirmed top-level message beside the case, or finds the panel open first | **resolved**. Every guard named in round 1 now fails at red. The stated red for two of the non-guard tests is off (minor 1) |
| 3. Summary pinned only on history/get/delete | Decision 27; Task 5 table gives every `_as_message` caller's value; four new tests (REST edit response and `message_edited`, reaction, socket edit and delete, search) | **resolved**. The table covers every DTO site I listed in round 1: `:130`, `:183`, `:222`, `:343`, reactions `:82`, search `:75`, `realtime_writes` `:201`, `:253`, `:287`, the thread root and `test_indexing.py` |
| 4. Old root put at the head of history | Decision 28: `replaceMessage`. History adds rows only from `message_received` and its own sends. Four tests, each with history holding another message | **resolved**. Splitting `onMessage` (`useChannelSocket.ts:150-175`) keeps `reapplyAfterFetch` working, because each handler closes over its own `apply`. The existing test at `:233` edits a cached row, so it still passes. An edit that arrives during a first load is a no-op, and is then re-applied after the fetch, so nothing is lost |
| 5. Summary read before commit | Decision 9 reads it after commit, and Task 5 sets the order. Two tests record `commit` and the aggregate in sequence. Decision 22 is narrowed to cross-pod delivery order | **resolved**. Checked: `_commit_impl` dispatches `commit` at `base.py:1134-1136` in the installed 2.0.51. `db.py:27` sets `expire_on_commit=False`, and the plan builds the DTO before commit with `root_id` held as a local, so nothing lazy-loads after commit. The red `'summary' in ['commit']` is what a build that never aggregates reports |
| 6. Error branch replaces a loaded thread | Decision 23 is rewritten: the notice shows only for an error with no data. New test `a failed refetch keeps the loaded thread` | **resolved**. `test/render.tsx:31` has `retry: false`, so the 500 turns into `status: 'error'` at once and the test waits on that before asserting |
| 7. `optimistic()` literal | In the file map and Task 6 | **resolved** |
| 8. Reaction on the root while the panel is open | Task 6 routes `threadRootId: null` to history and the root's thread entry; new test | **resolved** |
| 9. Unstated summary paths | Socket delete of a reply publishes; the thread root carries `summary_for`; both are tested | **resolved** |
| 10. "Nothing is created" checked through history | Counts `messages` rows through the `engine` fixture (`conftest.py:48`); new anchor test | **resolved**. `SendMessageRequest`'s config (`schemas.py:37`) doesn't forbid extra fields, so today `threadRootId` is ignored and the reply goes out first. The anchor test's stated red holds |

## Findings

### 1. Two Vitest files state one red for tests whose first assertion is something else — minor
**Where:** Task 3 table, `MessageItem.thread.test.tsx` and `ChannelView.thread.test.tsx` rows ·
**Checked:** the plan's own *Guards carry their positive* paragraph.
`"1 reply" and "2 replies"…` and `a deleted root shows its summary…` assert a summary first, so
their red is `Unable to find … "1 reply"` (or "2 replies"), not "Reply in thread". `a bad thread
leaves the history showing` asserts the notice before the history, so its red is the notice text
not being found, not `complementary "Thread"`. Each still fails because the feature is missing,
which is the right reason. Only the wording of the stated red is off. The test-writer should give
the real failure in `02-red-tests.md`.

### 2. The query-count and commit-order tests depend on how the aggregate is rendered — minor
**Where:** Task 2, `test_a_page_of_history_costs_one_summary_query` and the two `…after_it_commits`
tests · **Checked:** reasoning only, from SQLAlchemy's compiler for an unaliased mapped column.
The filter `GROUP BY messages.thread_root_id` matches `.group_by(Message.thread_root_id)` on the
mapped table. If the code groups over an alias, or a label, the filter misses it, and the tests
fail a correct build. Task 4 already describes the query as `GROUP BY thread_root_id` over
`messages`, so the code-writer should keep it unaliased. If it doesn't, the code-reviewer should
take a test change rather than a rewrite.

## Left for later stages

- Minor findings 1 and 2 above.
- **Assumed** decisions for the human to read: 21 (a reply to a tombstoned reply is filed under its
  root), 22 (two near-simultaneous replies on two pods can leave a count one low until a refetch),
  23 (a first-load 5xx shows "not available"), 24 (a workspace switch closes the panel through
  `ChannelView`'s 404), 25 (the composer is disabled offline).
- Decision 28 changes today's behaviour: an edit or delete event for a message that isn't loaded
  no longer inserts it at the head of history. This is deliberate and tested. The code-reviewer
  should confirm that no existing test relied on the old insert.
- Task 9's merge with issue 2: when `?message=` is removed with `replace`, `thread` must survive.

## Checked and sound

- Base `950e66a` is still `git log -1`. The worktree has only `docs/plans/issue-3/` untracked.
- The plan is 573 lines, inside 250–600. *Found while building* is empty. No task commits. RED
  tasks 1–3 come before GREEN tasks 4–7, with the test-reviewer gate.
- The `engine` fixture exists (`tests/integration/conftest.py:48`), and the app's own engine is
  caught by class-level `Engine` listeners, as in `test_reactions.py:249`.
- The join-ack prefix invalidation (`useChannelSocket.ts:134`) is unchanged, and still reaches
  the nested thread key (decision 15, verified in round 1).
- The new tests are named consistently with decisions 9, 23, 27 and 28 and with the Task 5
  table. The self-review and the known-ripple list were updated for `replaceMessage` and the
  `onMessage` split.
