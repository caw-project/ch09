# Test review — issue 3, round 2: approved

All three round-1 findings are fixed in the test files, and nothing beside them changed. The red is still real: `ThreadPanel.test.tsx` fails at load, as every test in it needs `./threadCache`, and the 8 `ChannelView.thread` tests fail for the missing panel. No critical or major finding is open.

## Responses checked

The red report was not updated this round. It has no *Review responses* section and still says "round 1". I checked each fix in the test files instead.

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. `scrolling to the top loads older replies` counted the members request (critical) | None written. `ThreadPanel.test.tsx` lines 167-172 now filter `requests()` to paths ending `/thread`, with the comment "the panel also fetches member names". | resolved |
| 2. `opening A then B pushes` raced a fresh reply id on refetch (critical) | None written. `ChannelView.thread.test.tsx` lines 73-86: `replyTo` memoises one reply per (root, body) in a `Map`, and the thread handler (lines 104-109) uses it. Ids are stable across the Back refetch. | resolved |
| 3. `a failed refetch keeps the loaded thread` passed the wrong build (major) | None written. `ThreadPanel.test.tsx` lines 276-284: after the `waitFor` on `error` there is an `act` with a 100 ms timer, then the positive assertion (reply still shown) and the no-notice assertion. | resolved |

## What ran

- `npm --prefix src/frontend test -- src/features/threads/ThreadPanel.test.tsx src/features/channels/ChannelView.thread.test.tsx`:
  - `ThreadPanel.test.tsx` failed to load: `Failed to resolve import "./threadCache"`. Every test in the file needs that module, so this is the right kind of load failure.
  - `ChannelView.thread.test.tsx` failed 8 of 8 on `Unable to find role="complementary" and name "Thread"` and similar (the panel is missing). Round 1 had the same 8 red.
- No sketch this round. The edits are confined to those two test files. In round 1 I ran the exact sketch for finding 3: the 100 ms flush makes the wrong build (`unavailable = q.isError`) fail. Finding 2's fix is the stable-id change I tested in round 1. Finding 1's fix is the path filter that `ChannelView.thread.test.tsx:268` already uses.
- `git status --short` lists only the writer's test and doc files, with no production code or config.

## Findings

### 1. The red report carries no Review responses — minor
**Where:** `docs/plans/issue-3/02-red-tests.md` · **Checked:** read it; the section is absent.
The fixes are in the tests, so nothing hinges on it. The code-writer should read this review's table, not the report, for what changed in round 2. The report's *Observed red* rows for `ThreadPanel` and `ChannelView.thread` are unchanged and still correct.

## Left for later stages

Carried from round 1, for the code pair:
- `ThreadPanel.test › a reply leaves the channel's read state alone` can't tell a panel that sets `readingChannelId` to the same channel from one that doesn't. The `mark_read` half does catch a `useMarkRead` in the panel.
- `ChannelView.thread › switching channel closes the panel` is satisfied by any build. It pins the behaviour but proves nothing about the code.
- `test_a_socket_mark_read_of_a_reply_acks_a_404` doesn't re-read the marker as its REST twin does.
- No test pins the 5 s ack timeout for `useSendReply` (plan Task 6 asks for it), or a non-author deleting a reply (R9).
- The `thread_summary_changed` payload is compared with `createdAt` as strings, so emit the same formatting.
- `useThreadActions` returns mutations, not functions. If the code-writer builds functions, send back.
- Keep the summary aggregate unaliased and grouped by `messages.thread_root_id`, as the report's *For the code-writer* says.

## Checked and sound

- Round 1's verdicts on the backend red (41 of 41), the Vitest red (30 of 30), the BDD bind check, the coverage table and the wrong builds sketched all stand. No test files outside the two above changed, as far as I could see from the finding fixes.
- A correct build, with stable reply ids, passed `ChannelView.thread` 8 of 8 in the round-1 sketch.
