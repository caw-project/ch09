# Green — issue 5, round 1 (rework after send-back 3)

Direct messages are built end to end (pair index and migration, `messaging.dms`, `POST /channels/dm`,
R9 guards, `channel_added` on REST and socket, regenerated contract, SPA section/picker/naming/socket
handler, and the record). After the test pair repaired the four faults in send-back 3, **every layer is
green**, including the new journey on its first e2e run.

## Baseline
Not taken before the first build (spent on the build). On return, the tree matched the test review's
account: typecheck clean, Vitest 487 passed, the five touched Python files passing.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 4 | `models.py`, `alembic/versions/0007_dm_pair.py`, `dms.py`, `channels.py` | unit green | `list_page` carries the listing rule; `_visible_from(row, user_id)` fills `dm_partner_id` |
| 5 | `schemas.py`, `routers/channels.py`, `routers/messages.py`, `realtime.py`, `realtime_writes.py`, `openapi/messaging.json`, `types/messaging.ts` | integration green | `POST /channels/dm`; `publish_channel_added`; first-send detection before insert on both transports |
| 6 | `lib/api/messaging.ts`, `directMessages.ts`, `DirectMessageList.tsx`, `UnreadBadge.tsx`, `ChannelList/Header/View/Composer`, `ChatLayout`, `useChannels`, `search/*`, `useChannelSocket.ts` | Vitest green | |
| 7 | register D8b/D44, ADR `261005-direct-messages-are-dm-channels.md`, docs 02 and 06, vocabulary §34, comments | — | test docstrings fixed by the test pair |
| 8 | verification below | — | |

## What ran
- `npm --prefix src/frontend run typecheck` → clean.
- `npm --prefix src/frontend test` → **487 passed** (50 files).
- `npm --prefix src/frontend run lint` → clean. `npm --prefix src/frontend run build` → built.
- `scripts/test.sh lint unit integration` → passed: Unit **894 passed**, Integration **531 passed**, 0 failed.
- `scripts/test.sh e2e` → passed: **24 passed, 0 failed**, including "Grace sees the direct message Ada starts, and replies".
- `.claude/hooks/security.sh` → "Security pass clean: ruff-bandit, conventions, gitleaks, semgrep" (it runs the
  convention checks over the changed files; a direct `conventions.py` call was refused by the sandbox).
- `docs/test-report.md` is from the last run (e2e), all four layers passed.

## Beyond the tests
- Decision 12's refusal wording and ordering: `routers/channels.py` `_manageable_or_403`, called first in `_admin_or_403`.
- D44 doc-comments: `dms.open_dm` module docstring, `OpenDmRequest`; `add_member`'s docstring.
- `index_where=text("kind = 'dm'")` matches the partial index; members inserted only by the creating transaction.
- Commit-then-publish: `channel_added` after `message_received` in `routers/messages.py` and `realtime_writes.py`.
- `useChannelSocket.ts` `channel_added` handler incl. first-load reapply (decision 16).

## Departures from the plan
- R9 guard inside `_admin_or_403` (one place, same order).
- `useOpenDirectMessage(accessToken)` — workspace travels in the variables.
- `messaging.json` edited by hand (sandbox refused redirecting generator output).
- `UnreadBadge.tsx` extracted (plan said to share the badge).

## Picked up from earlier reviews
- test-reviewer-2/3: counts 7+7 not 8+8; REST-only "later message"; workspace-switch not pinning the new list; sender's own connection unpinned — test-side, left.
- plan-reviewer-2: `messaging.post` stub answers 201 — DM tests don't assert status; untouched. D14/D17 assumed decisions built as planned.

## Left for the human
- **First real run in three browsers** (Ada, Grace, Alan) per the issue's Acceptance list: empty DM unlisted for both; "hi" reaches Grace and Ada's second tab; Grace's **+** lands in the same DM; Alan's URL and search find nothing; headers name the other person.
- Regenerate `messaging.json` once (`python -m messaging.openapi > src/frontend/openapi/messaging.json`) and expect no diff.
- The sidebar's 50-row page now shares DMs with channels (declared in the plan).
- Merge `main` if a sibling branch landed.
