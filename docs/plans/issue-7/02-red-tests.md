# Red tests — issue 7, round 1

TDD, Vitest only. 15 new tests across three files (11 hook, 1 consumer, 3 socket); all 15 fail as the
plan expects, each at its first assertion that a second directory `GET` was made (or the name arrived).
Every existing test in the two modified files still passes. No production file was touched.

## Baseline
| File | Before | After |
|---|---|---|
| `features/channels/MessageList.test.tsx` | 7 passed | 7 passed + 1 new (red) |
| `lib/realtime/useChannelSocket.test.tsx` | 18 passed | 18 passed + 3 new (red) |
| `features/channels/useWorkspaceMembers.test.tsx` | — (new) | 11 new (red) |

(The two existing files together: 25 passed before, 25 passed after.)

## Tests
| File · test | Layer | Plan task | Proves | Expected red (plan) | Observed red (verbatim first line) | Match |
|---|---|---|---|---|---|---|
| hook · shows the short id while the refetch is in flight, then the name it brings | Vitest | 1 | R1, R4 | `expected 1 to be 2` | `expected [ { method: 'GET', …(3) } ] to have a length of 2 but got 1` | yes |
| hook · asks once for several unknown ids in one render, and once for an id two consumers ask for | Vitest | 1 | R2, Paths 3 | `expected 1 to be 2` | `expected '01a13ec0' to be 'Grace Hopper'` (waiting for the name; no 2nd request) | yes |
| hook · starts nothing during the first load, then one refetch… | Vitest | 1 | Paths 1, decided 6 | same | `…length of 2 but got 1` | yes |
| hook · an id first seen during a refetch gets one more… | Vitest | 1 | R2, R3 | same | `…length of 2 but got 1` | yes |
| hook · a departed id starts no further refetch… | Vitest | 1 | R3, dec. 3 | same | `…length of 2 but got 1` | yes |
| hook · an unknown id seen while a refetch for another reason is in flight joins it | Vitest | 1 | R1+staleness | `expected 2 to be 3` | `…length of 3 but got 2` | yes |
| hook · a fetch for another reason clears the departed set… | Vitest | 1 | R3, dec. 7 | same as row 1 | `…length of 2 but got 1` | yes |
| hook · a departed member who rejoins is named at the next fetch for another reason, not before | Vitest | 1 | R3+rejoin | same | `…length of 2 but got 1` | yes |
| hook · a refetch that fails leaves the ids it was for quiet | Vitest | 1 | dec. 15 | same | `…length of 2 but got 1` | yes |
| hook · a refetch for one workspace lands in that workspace's cache, after a switch | Vitest | 1 | R6 | same | `…length of 2 but got 1` | yes |
| hook · each workspace keeps its own departed set | Vitest | 1 | R6 | same | `…length of 2 but got 1` | yes |
| MessageList · shows a newcomer's name on their message once the directory catches up | Vitest | 2 | Paths 2 | `Unable to find an element with the text: Grace Hopper` | same | yes |
| socket · refetches the workspace directory on every connect | Vitest | 2 | R5 | `expected false to be true` | `expected false to be true` | yes |
| socket · a connect while a refetch for an unknown author is in flight joins it, and still clears the departed set | Vitest | 2 | R1+R5, dec. 20 | `expected 1 to be 2` | `…length of 2 but got 1` | yes |
| socket · an unknown author arriving during a reconnect's refetch joins it | Vitest | 2 | R1+R5 | `expected 1 to be 2` | `…length of 2 but got 1` | yes |

Wrong builds each also fails are as in the plan's tables (per-id/per-consumer refetch → settled count 3–4;
no `departed` → `quiet` sees `before + 2`; default `cancelRefetch` → a 3rd/4th request while held; no
`fetchStatus` read → row 4 never reaches #3 because the test does not `rerender()`; no `otherReason` → no #4
in the socket test).

## Review responses (round 2)
1. **Fixed.** `each workspace keeps its own departed set` now loads A and B first (both fresh for 5 min, so no
   first-load fetch clears anything), departs Alan in A, then asks him in B and requires exactly one request there
   (a shared set stays quiet and fails), invalidates B (a fetch for another reason), returns to A and asserts via
   `quiet` that Alan is still departed (a B fetch un-departing A's ids fails) and a new id still fetches.
   Observed red: `expected [ { method: 'GET', …(3) } ] to have a length of 2 but got 1` at the "Alan departs in A"
   step (all 11 hook tests red; preconditions before it hold). Not sketched green here — no production code exists.
2. Minor, accepted as noted.

## Types
`npm --prefix src/frontend run typecheck`: clean. No new production symbol is imported, so no load failure.

## BDD
None — no journey (plan).

## Departures from the plan
- **Row 8 (rejoin).** The plan's `quiet(Alan)` with the directory already answering `[ada, alan]` can't hold:
  the anchor's own fetch would bring Alan into the cache and name him through `nameFor`. `quiet` takes an
  `anchorAnswer`, so the anchor's call answers `[ada]`; the directory answers `[ada, alan]` only for later calls.
  A build that refetches for Alan on a render still shows `before + 2`.
- **Row 10 (switch).** B is allowed to finish loading before A's held response is released (the plan left the
  order open); A's cache gets Grace, B's must not, B's consumer shows her short.
- **`scriptDirectory` (new shared helper, `test/directory.ts`)** beside `settleDirectory`: answers per workspace
  and call number (`now`, `answer`, `hold`, `requests`). Used by all three files instead of three copies of
  the same bookkeeping; `quiet` stays local to the hook test (the socket test inlines the one check it needs).
- `auth.membersBy` answers whatever `reply` returns; "last list repeats" is `scriptDirectory`'s `now`.
- Socket test 2 asserts `quiet` inline: counts 4 then 5 after a new id, Alan still short.

## Picked up from earlier reviews
- `settleDirectory` takes two idle readings, each after its own macrotask (plan-reviewer-2).
- Later-mounted consumer is a second `renderHookWithProviders` with the same `queryClient`; row 4 does not
  `rerender()` between releasing #2 and expecting #3; the MessageList test counts after `settleDirectory`.

## For the code-writer
- Tests read only `useWorkspaceMembers`, `directoryKeys`, `shortId` and `onConnect`'s effect; the tracker's names
  are yours so long as the plan's rules hold.
- Row 4 needs the hook to read `fetchStatus` (equal data lands; nothing else re-renders).
- Existing consumer tests may make one extra directory request (plan's ripple).
