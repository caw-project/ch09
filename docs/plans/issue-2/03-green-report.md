# Green — issue 2, round 1

Every GREEN task (5, 6, 7), the e2e harness change (8) and the record (9) are built. Everything this stage can run is green: lint, typecheck, build, Vitest (296), Python unit (322) and the whole e2e layer (21 of 21, the new search journey included). The earlier 503 in the journey was the host's full disk (human's answer); on a healthy disk it passes unchanged.

## Baseline
Over the nine red-report files: 24 failed, 57 passed, with `jump.test.ts`, `SearchBox.test.tsx`, `SearchPage.test.tsx` not loading — as the red report says. No difference.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `lib/api/messaging.ts`, `features/channels/jump.ts`, `useMessages.ts` (`loadedPageCount`, `refetchHistory`), `lib/realtime/useChannelSocket.ts` | all green | both join-ack sites use `refetchHistory` |
| 6 | `useMessageJump.ts` (new), `MessageList.tsx`, `useMarkRead.ts` (`flush`), `MessageItem.tsx` (`highlighted`) | `features/channels` green | `loadOlder`, R7 guards, R8 `olderWanted`, notice, third docstring paragraph |
| 7 | `features/search/{useSearch,useChannelNames,SearchResult,SearchPage,SearchBox}`, `ChatLayout.tsx`, `App.tsx` | green | box first in the `<aside>`; `/search` protected |
| 8 | `scripts/test.sh`, `README.md`, `docker-compose.test.yml` | — | `E2E_SCALE` gone; per-worktree Compose project and clean start (human's answer); failed runs print the log tail of the Worker and Messaging |
| 9 | doc 06 §4/§5.2/new §5.4, register D8c, ADR `261002-…` | — | |

## What ran
- `scripts/test.sh lint unit`: passed. Python unit **322 passed**; Vitest 31 files, **296 passed** (baseline frontend 243 + 53); ruff, conventions, frontend lint and helm lint clean.
- `npm --prefix src/frontend run typecheck`: clean. `npm --prefix src/frontend run build`: built.
- `scripts/test.sh e2e` (whole layer, run last, after the diagnostic log was removed): **21 passed, 0 failed** (baseline 20 + the search journey). `docs/test-report.md` is from that run.
- `python3 .claude/hooks/checks/conventions.py` over the changed Python and TypeScript files I touched: no findings.
- `.claude/hooks/security.sh`: one semgrep finding, `testkit/report.py:96` (native `xml` parse) — a file this work did not touch; it was there before.
- No `integration` run: the plan names none, and no service code changed.

## Beyond the tests
- Doc-comments: `MessageList.tsx` header (who may cancel whom), `useMessageJump.ts`, `useSearch.ts`, `useChannelNames.ts`, `SearchBox.tsx`, `SearchResult.tsx`.
- `transition-colors duration-700` always on, `bg-accent/15` while highlighted: `MessageItem.tsx`.
- Search options (`enabled`, no focus/reconnect refetch): `useSearch.ts`. Blank-`q` prompt, "Searching…", Retry only with no data: `SearchPage.tsx`.
- Resubmit invalidates and navigates only if the URL differs: `SearchBox.tsx`.
- `cancelRefetch: false` on every product page fetch: `loadOlder` is the only caller of `fetchNextPage` in `MessageList`.

## Departures from the plan
- No in-flight ref in the jump hook (`loadOlder`'s idle-now guard does the job); `onScrolled` also updates `wasAtBottom`; `historyKey` memoised; doc 06 §5.4 sits above §5.3 in the file.
- `scripts/test.sh`: per-worktree project, clean start (human's answer), and a failure log tail (mine; small, kept as the human allowed).
- The diagnostic warning log in `messaging/search.py` was added and then removed; Messaging is unchanged (`git diff` empty there).

## Picked up from earlier reviews
- plan-reviewer-2 B: the sweep leaves `docs/issues/002.md` and the accepted ADR `260815-…` (dated records of what was true). plan-reviewer-2 C: covered by `loadOlder`'s guard. test-reviewer-2 minor 7: `cancelRefetch: false` is pinned through `loadOlder`'s guard.

## Left for the human
1. **`CLAUDE.md:229-230`** still says the test stack scales Elasticsearch and the Worker to zero. Replace with: the test stack runs Elasticsearch and the Worker (the search journey needs both), and its Compose project name is per worktree. (No stage may edit it.)
2. Old `collabhub-test_*` volumes from before the per-worktree project name can be removed.
3. **The plan's Task 10 first real run** (six checks, on the dev Compose stack in a real browser): centring and the highlight fade have never been seen outside jsdom, and neither has an older page loading after a target centred near the top.
4. Doc 06's §5.4 is above §5.3; swap if you mind.
5. The semgrep XML finding in `testkit/report.py` is pre-existing and not this work's.
6. If `main` or issue 3 lands first, merge it and rerun `scripts/test.sh e2e`.
