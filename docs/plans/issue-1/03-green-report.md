# Green — issue 1, round 1

Unread counts, read markers and the "New messages" divider are built to the plan's interfaces. Every
Vitest test passes (241), typecheck, lint and build are clean, and `scripts/test.sh lint unit` and
`scripts/test.sh e2e` pass — the new journey went green on its first run (20 of 20).

## Baseline
Typecheck before any change failed only as the red report says: `TS2307` for the five missing modules,
`TS2322` for the two new `MessageList` props, `TS2339`/`TS2353` for `readingChannelId` — no other
errors. The red report's Vitest counts (146 passing, 38 failing, 5 files not loading) were not rerun
file by file; the first test runs of each task below were the red-to-green check.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `readState.ts`, `readThrottle.ts` | `readState` 18, `readThrottle` 9 — pass | throttle is a `Map<channel,{timer,held}>`; a window reopens only if `send` returned true |
| 6 | `readCache.ts`, `useMarkRead.ts`, `usePageAttention.ts`, `stores/chat.ts` | `readCache` 14, `useMarkRead` 12, `usePageAttention` 4 — pass | flush effect declared before the throttle effect; `send` reads `snapshot()` live |
| 7 | `useChannels.ts`, `ChannelList.tsx`, `MessageList.tsx`, `ChannelView.tsx`, `useChannelSocket.ts` | `src/features/channels` + `useChannelSocket`: 21 files, 196 tests — pass | `MessageList` keyed per channel |
| 8 | `docs/design/06-frontend-spa.md`, new ADR `261002-unread-state-polls-rather-than-pushes.md`, `260915-…` | — | record |
| 9 | `docs/test-report.md` (by the script), plan *Found while building* | — | verification |

## What ran
- `npm --prefix src/frontend test` (whole suite): 27 files, **241 passed** (baseline 145 + new).
- `npm --prefix src/frontend run typecheck`: clean. `run lint` (`eslint .`): clean. `run build`: built.
- `scripts/test.sh lint unit`: passed — ruff, conventions, frontend lint, helm; pytest 322 passed;
  Vitest 241 passed.
- `scripts/test.sh e2e`: **20 passed** (baseline 19 + `read_state.feature`).
- `python3 .claude/hooks/checks/conventions.py` over the four changed `tests/bdd` Python files: no findings.
- `.claude/hooks/security.sh`: one semgrep finding, `src/services/testkit/testkit/report.py:96`
  (native `xml` parse) — a file this branch does not touch; it was there before.
- `docs/test-report.md` is the one the e2e run wrote last.

## Beyond the tests
- Doc-comments for the hold line, throttle semantics, the keyed remount and why `refetchOnWindowFocus`
  is off: `readCache.ts`, `readThrottle.ts`, `useMarkRead.ts`, `useChannels.ts`, `ChannelView.tsx`.
- `useChannelSocket.ts` header comment gains the receipt and connect-refetch (plan Task 7).
- Bold name only while the badge shows (one condition in `ChannelList.tsx`) — no test pins the bold half.
- `ChannelList` shows the error only while `channels === undefined` (decision 21).
- Record: doc 06 §5.2 (`throttle mark_read` bullet replaced by *Read state — added 2026-10-02*), the new
  ADR with the issue's three alternatives and revisit condition, and the corrected note in the
  read-state ADR. Sweep: no remaining "throttle `mark_read`" or "ignored receipt" text in `docs/design`
  or `src/frontend/src` (the remaining `mark_read` mentions describe the server contract).

## Round 2 — Review responses
Code-reviewer-1 finding 1 (major) — **fixed.** `useMarkRead.ts`'s throttle cleanup no longer releases
holds (it also runs on unmount); a comment says why. Each hold ends by its ack, error ack or timeout;
on a socket change socket.io-client errors pending acks. Doc 06 §5.2 and plan Task 2 corrected; round
recorded in *Found while building*. The new tests (`useMarkRead.test.ts`) pass: Vitest now **243**.
Re-run after the change: whole Vitest 243 passed, typecheck, lint and build clean,
`scripts/test.sh lint unit` passed, `scripts/test.sh e2e` passed (whole layer), conventions check clean.
The Round 1 results above are superseded by these.

## Departures from the plan
None in interfaces, markup or decisions. Details in the plan's *Found while building*: module-level
`measure`/`NO_MESSAGES` in `MessageList.tsx` (to satisfy the hooks lint rule without suppression), and
`isPending` as a layout-effect dependency so an empty channel is measured when its scroller appears.

## Picked up from earlier reviews
- test-reviewer-2 #2 (run the fixed cached-return test first): it passed in both orders on the first run.
- test-reviewer-2 #1 / the red report's stale wording on the cached-return test: noted; the test itself
  is what counts, and it is green.
- plan-reviewer-2 (code pair): `loading` counts as live in `isLiveWorkspace` — built as written, with
  the reason in its doc-comment.
- "Refetches once, not twice" on focus (test-reviewer-1 #2): no test separates a double fire; the
  `cancelRefetch: false` is built as decision 18 says. The first real run should check the network tab.

## Left for the human
- **The plan's first real run by hand**: `docker compose up -d --build`, two browsers (or a normal and a
  private window), and walk the issue's *Acceptance* list. Look at: the badge on a background channel
  appearing within ~30 s; one list request on tab return, not two; the divider staying put as you read;
  a second tab clearing its badge on a read. Close devtools before reading the network tab (it steals focus).
- **Assumed decisions to read:** 15 (ceiling), 16 (boundary loaded), 22 (no window without a send),
  23 (another user's receipt ignored), 28 (A→B→A within a second sends twice).
- The journey does not wait for the `mark_read` ack before reloading; a flake would show as a badge after reload.
- The pre-existing semgrep finding in `testkit/report.py`.
