# Test review — issue 7, round 1: changes_requested

14 of the 15 new tests fail for the right reason and a correct sketch turns all 15 green; every
wrong build I tried but one is caught. The exception is R6's departed-set test: a build with
**one departed set shared by all workspaces passes it**. One major finding; the rest is minor.

## Expectations

Written before the red report or any test file was opened.

Today's code: `useWorkspaceMembers` is one `useQuery`, `nameFor` falls back to `shortId`, and
nothing refetches or invalidates the directory; `onConnect` invalidates only the channel list.
Every new test should therefore fail at the first assertion that a *second* `GET …/members`
happened (or `isInvalidated` false for R5) — not at an import. No new production symbol is
imported by a test, so no load failure is expected; `auth.membersBy` and `settleDirectory` are
test support, and a typo in either would fail every test for the wrong reason.

| Behaviour | Fails today with | Vacuous version | Clause that must be pinned | Wrong build to catch |
|---|---|---|---|---|
| R1/R4 unknown id refetches; short id meanwhile | request count 1, not 2 | asserts the name appears after the *test* invalidates; or never holds the response so the short-id state isn't observed | "in flight → short id", "every place" | placeholder; fetch on every render |
| R2 one request at a time | same | counting requests before the fetch has landed (absorbs a late one); one consumer only | several ids / several consumers → **one**; ids seen *during* a fetch get **one** more, after it lands | refetch per id or per consumer; default `cancelRefetch` (cancel + restart = 2 requests) |
| First load | same | asserting no request while loading without a positive afterwards | none while loading; one when it lands without them; departed if that lacks them | fetch during first load; depart on first load |
| R3 departed quiet | same | "no further request" asserted by an anchor that absorbs the request (the plan's `quiet`) | "started *after* first seen"; id seen *during* the fetch is not departed; clearing on another-reason fetch | departed set per hook instance; depart every missing id; never clear |
| R3 vs R2 contrast | same | an equal-data refetch re-renders nothing, so the test passes only because the test itself re-renders | no test-side `rerender()` between release and the follow-up | hook reading only `data` |
| R5 reconnect | `isInvalidated` false | invalidating after seeding but not checking "every" connect, only first | "as it refetches the channel list" — every connect | invalidate once only; cancel in-flight fetch |
| R1+R5 both orders | request count | only one order | one request either way; the reconnect clears the departed set even when it joins | default `cancelRefetch`; no `otherReason` |
| R6 per workspace | A's count 1 | one workspace only | response lands in its own cache; B's departed set independent | key/tracker ignoring workspace |
| Failed refetch (assumed 15) | same | passes because 500 → no render | no retry per render | loop |

Plausible wrong builds the code-writer might make: a `useEffect` keyed on `[unknown.size]`
(misses a second distinct id of the same count); a departed set in `useRef`/`useState` per hook;
`invalidateQueries` with default cancel; a `Set` built in `useMemo` so the effect sees stale ids;
workspace taken from the closure in `queryFn`.

## What ran

- `npm --prefix src/frontend test -- useWorkspaceMembers.test.tsx MessageList.test.tsx useChannelSocket.test.tsx`:
  15 failed, 25 passed. Each failure's first line matches the red report's *Observed red*: `length of 2
  but got 1` (or 3/2), `expected false to be true` (R5), `Unable to find … Grace Hopper`, and
  `expected '01a13ec0' to be 'Grace Hopper'` (hook test 2, the name never arrives). No import or
  setup failure; no new production symbol is imported.
- `npm --prefix src/frontend run typecheck`: clean.
- `git status`: only the three test files, `test/api.ts`, `test/directory.ts` and the plan dir. No production file.
- **Sketches** (`build/sketch/frontend`, cleaned):

| Build | Files | Result |
|---|---|---|
| Correct, to the plan's tracker + hook + `onConnect` | all three | 40/40 green |
| Hook reads `data` only (no `fetchStatus`) | hook, socket | 3 red (rows 4, 6, 7) |
| `refetchQueries` with default `cancelRefetch`, no in-flight check | hook, socket | 13 red |
| No `otherReason` on connect | socket | 1 red (R1+R5, row 2) |
| Connect's `invalidateQueries` with default cancel | socket | 1 red (R1+R5, row 2) |
| Depart every missing id (drop `seenAt < startedAt`) | hook | 2 red (rows 4, 6) |
| **One departed set shared across workspaces** | hook | **11/11 green — finding 1** |
| Failed refetch leaves ids pending | hook | 1 red (row 9) |
| Clear departed on every fetch, own included | hook | 7 red |

## Coverage

| Plan test / expectation | As written | Outcome |
|---|---|---|
| Task 1 rows 1–11 | the eleven hook tests, same names | present |
| Row 8 `quiet` with directory already `[ada, alan]` | `anchorAnswer` so the anchor's call answers `[ada]` | departed, reason sound (plan's version can't hold) |
| Row 10 order of release vs B load | B loads first, then A's held response is released | departed, harmless |
| MessageList consumer test | present, counts 2 settled | present |
| Socket rows 1–3 | present | present |
| `scriptDirectory` helper | extra helper in `test/directory.ts` (file the plan names) | departed, in report |
| R6 "own departed set" | present but does not pin it | **see finding 1** |

## Findings

### 1. `each workspace keeps its own departed set` passes with one set for all workspaces — major
**Where:** `useWorkspaceMembers.test.tsx`, last test · **Checked:** sketched; 11/11 green with a
single `Set` shared by every workspace's state (plan's tracker otherwise).
The test makes Alan depart in A, switches to B, and expects B's **second** request. But B's first
load is a fetch for another reason: it clears the departed set (R3), so the shared set is empty
before Alan is asked, and the second request is simply B's own first-load follow-up (R2). The
assertion would be true with no departed set at all. It also asserts nothing after the request
(no count, no short id). R6 says "its own departed set" — the leak it exists for is one
workspace's departed id silencing another, or B's fetch un-departing A's.
**Fix:** load B *before* A's id departs (render B once, switch back to A, depart Alan in A), then
switch to B — now cached and fresh, so no fetch clears anything — and ask Alan there: B must make
exactly one request for him. Add the converse: after that, A's Alan is still quiet (`quiet`), so a
B fetch cannot un-depart A's ids. Assert the settled count.

### 2. `refetches the workspace directory on every connect` pins `isInvalidated` — minor
Mirrors the channel-list test and the plan names `invalidateQueries`, so a correct build passes;
a `refetchQueries` build would fail. Acceptable, noted only.

## Left for later stages
- Plan-reviewer's note: `otherMarked` outlives a fetch that never lands — code pair keeps the behaviour, with a comment.
- Test 10 (`a refetch for one workspace lands…`) passes only if both workspaces' tracker keys use the
  key's workspace; a "current workspace variable" build would also be caught only via the cache assertion — adequate.

## Checked and sound
- Red is for the right reason on all 15; none a load failure; typecheck clean; existing 25 tests still pass.
- `quiet` settles before the anchor, and asserts `before` exactly after the ask — a refetch for a quiet id is caught (sketched via rows 4, 6, 7).
- Row 4 does not `rerender()` between release and #3, and fails the `data`-only hook (sketched).
- R1+R5 in both orders; the joined reconnect clears the departed set (sketched without `otherReason` and with default cancel).
- First-load no-fetch half has its positive (the follow-up request); failed refetch has its positive (the anchor).
- No fake timers; waits are on requests/renders; no `data-testid`; no assertion in an existing test altered.

