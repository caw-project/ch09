# Test review — issue 5, round 3: approved

Rework pass after the code-writer's send-back. Every item of the send-back is fixed in the tests, nothing was loosened, and the touched files pass against the built code. No findings.

## Responses checked
| Send-back item | Writer's response | Outcome |
|---|---|---|
| 1 Ripple edits (`channelName` → `channelTitle`; `CreateChannelDialog` stub) | `MessageComposer*.test.tsx` pass `channelTitle`; `CreateChannelDialog.test.tsx` stubs `auth.members` and counts `/c/` links | Resolved — diff read; typecheck clean. The link filter still pins one conversation link with the DM section empty, so the count assertion keeps its meaning |
| 2 `test_both_members_can_use_every_message_route` history before send | history fetched after Grace's send | Resolved — assertion `["from grace","root"]` unchanged, now reachable |
| 3 `test_a_reply_does_not_announce_a_dm` | receives `thread_summary_changed`, then `hears_nothing` | Resolved — still fails for `channel_added` on a reply, and the positive half (`channel_added` after the first message) sits earlier in the test |
| 4 `ux_channels_dm_pair` rendering | asserts UNIQUE, `(workspace_id, name)`, `WHERE`, `'dm'` | Resolved — each part still catches a non-unique, non-partial or wrong-column index |
| 5 Docstrings | reworded in `test_channel_rules.py`, `test_channels.py` | Resolved; assertions untouched |

## What ran
- `npm --prefix src/frontend run typecheck` → clean.
- `npm --prefix src/frontend test` → 487 passed (50 files).
- `uv run pytest` over `test_dms.py`, `test_dm_realtime.py`, `test_schema.py`, `test_channels.py`, `unit/test_channel_rules.py` → 125 passed.
- `git diff` of the changed existing tests: only the edits above; no existing assertion removed or weakened.
- No sketch was needed: code exists and the tests run green against it, and the changes can't reach earlier sketch results.

## Findings
None.

## Left for later stages
- Carried from round 2: report counts (7 + 7, not 8 + 8); "later message announces nothing" proven on REST only; workspace-switch test doesn't pin the new workspace's list untouched; sender's own connection hearing `channel_added` unpinned.
- Report says Vitest "50 files / 487 passed" — matches what I saw.

## Checked and sound
- Rounds 1–2 *Checked and sound* stand.
- The adjusted `CreateChannelDialog` count and the `thread_summary_changed` receive are anchored to positive events, so the negatives cannot pass vacuously.
