# Green — issue 3, round 2 (after send-back 3)

The backend (Tasks 4–5), the SPA (Tasks 6–7) and the record (Task 8) are built, and the whole branch is
now verified green: Python unit and integration, Vitest, typecheck, lint, build, and all 21 e2e
scenarios including the thread journey. The test-writer fixed the one typing fault
(`threadCache.test.ts`) that blocked typecheck, build and e2e.

## Baseline
No separate pre-change baseline was run; the red report's counts were the starting point and the
previously-red tests went green with nothing else moving (red report: 244 passed, 30 failed, 4 files
failed to load → 316 of 316).

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 4 | `models.py`, `alembic/versions/0005_thread_index.py`, `threads.py` (new), `messages.py` | unit `test_threads.py` 8; `test_schema.py` index test | `summaries_for` unaliased, `GROUP BY messages.thread_root_id` |
| 5 | `schemas.py`, `routers/{messages,reactions,search}.py`, `realtime.py`, `realtime_writes.py`, `channels.py`, `read_state.py`, `search.py`, `openapi/messaging.json`, `types/messaging.ts` | integration 250 (39 new) | summary read after commit, REST and socket |
| 6 | `lib/api/messaging.ts`, `features/threads/{threadCache,useThread}.ts`, `features/channels/useMessages.ts`, `lib/realtime/useChannelSocket.ts` | cache, socket, hook tests | `replaceMessage`; routing by `threadRootId` |
| 7 | `stores/chat.ts`, `features/threads/{ThreadPanel,ThreadComposer,ThreadSummary}.tsx`, `useThreadParam.ts`, `MessageItem.tsx`, `MessageList.tsx`, `ChannelView.tsx` | panel, composer, item, view tests | |
| 8 | register D8a → 🟢, ADR `261002-single-level-threads.md`, docs 02 and 06, messaging README | — | |

## What ran
All after the last change.
- `npm --prefix src/frontend run typecheck` → clean.
- `npm --prefix src/frontend test` → 34 files, 316 passed.
- `npm --prefix src/frontend run lint` → clean. `npm --prefix src/frontend run build` → built.
- `scripts/test.sh lint unit` → passed: ruff, conventions, frontend, helm lint clean; pytest unit 330 passed;
  Vitest 316 passed (statements 92.6 %).
- `scripts/test.sh e2e` → 21 passed, including `test_thread_steps.py` (the thread journey went red→green here).
- Python integration (earlier this task, `uv run pytest src/services/messaging/tests/integration`) → 250 passed (80 s).
  One earlier `-x` run failed `test_realtime_writes.py::test_an_expired_principal_cannot_write` with a socket
  connection error and passed in the full run; flaky, not in code I changed directly.
- `python3 .claude/hooks/checks/conventions.py` over every changed messaging Python file → no findings.
- `.claude/hooks/security.sh` → one semgrep finding, `src/services/testkit/testkit/report.py:96` (native `xml`
  parse of the test harness's own JUnit files); pre-existing, not a file this branch touched.
- `docs/test-report.md` was rewritten by the last run (the e2e one).

## Beyond the tests
- Doc-comments for every decision: `threads.py` module docstring; `_as_message`'s `thread` paragraph;
  `useChannelSocket.ts` header (routing by `threadRootId`); `ThreadPanel.tsx` (decision 23, scroll rules,
  read-state rule); `ThreadComposer.tsx` (draft keyed by root); `useThreadParam.ts` (push/replace);
  migration `0005` (partial, plain `CREATE INDEX`).
- Decision 20: `upsertMessage` ignores replies (`useMessages.ts`). Decision 28: `replaceMessage`.
- Decision 17: `w-80 shrink-0 border-l` in `ThreadPanel`. Decision 25: offline notice in `ThreadComposer`.
- Stale text swept: `models.py`, `schemas.py`, `realtime_writes.py`, README, docs 02 and 06. Left:
  `0002_messages.py:22` (history) and `tests/integration/test_messages.py:58` (test file).

## Departures from the plan
See *Found while building* in the plan, items 1–8: `thread=` defaulted to `NO_REPLIES` rather than required;
`ReactionEvent.threadRootId` optional; mutations from `useThreadActions` with an optimistic reaction; helpers
exported from `useMessages.ts`; shared `publish_reply_summary`; hand-edited `messaging.json`. Send-back 3 round
trip: a test-file typing fault, fixed by the test pair; no production change.

## Picked up from earlier reviews
- test-reviewer-2 *Left*: `useThreadActions` is mutations (built so); `lastReplyAt` is the same
  `model_dump(mode="json")` string as the DTO; the summary aggregate is unaliased. The 5 s ack timeout is kept in
  `emitSend` (shared constant); no test pins it.
- plan-reviewer-2: decision 28 confirmed — no existing test relied on insert-on-edit.

## Left for the human
- Re-run `uv run python -m messaging.openapi > src/frontend/openapi/messaging.json` and confirm no diff (the file
  was hand-edited).
- The first real run on Compose with `EXPLAIN` of the summary query showing `ix_messages_thread`; the issue's
  *Acceptance* list in two browsers.
- If `feature/issue-2` merges first: keep `?message=` and `?thread=` together on `/c/:channelId`.
- Optional: make `thread=` a required keyword in `_as_message` (update six calls in `test_indexing.py`); and the
  stale "threads unbuilt" comment at `tests/integration/test_messages.py:58`.
- The pre-existing semgrep XXE note in `testkit/report.py`.

## Review responses
Round 2 here answers `code-writer-sendback-3`: the typing fault was fixed by the test pair (red report, *Review
responses (round 3)*); I reran typecheck, build, unit and e2e against it and they are green. The two minor items
for the test pair are unchanged (see *Left for the human*).

### Round 2, after code-reviewer-1 and send-back 4
1. **Fixed.** `thread_summary_changed` in `useChannelSocket.ts` now goes through `applyAndReapply` over the channel's history key and the root's thread key. The test pair's new tests (history and thread-key) pass. Doc 06 §5.2's routing bullet records it.
2. **Fixed.** Doc 02 §3.1.6 says replies are dropped from search hydration; §3.1.7 says replies are not unread and that `mark_read` of a reply is a 404.
3. **Fixed.** `scripts/test.sh lint unit integration` was run, then `scripts/test.sh e2e`, so the report shows every layer.
Minor items (OpenAPI escaping, duplicate history entry on re-opening a thread, `heightBeforePrepend` after a failed fetch, post-commit summary read) are left for a later stage.

What ran after the last change: Vitest 318 passed; typecheck, lint and build clean; `scripts/test.sh lint unit integration` passed (integration 420 passed across services); `scripts/test.sh e2e` passed; convention check on the changed files found nothing.
