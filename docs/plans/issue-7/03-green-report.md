# Green — issue 7, round 1

Built the directory tracker, the hook changes and the reconnect refetch; recorded it in doc 06 §5.2.
All 15 new tests pass, the full Vitest suite (503), typecheck, lint, build and the whole e2e layer (24) are green.

## Baseline
Red set as the report says: three files, 15 new tests red, 25 existing in the two modified files passing.
Typecheck clean. No difference observed.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 3 | `features/channels/directoryRefresh.ts` (new), `useWorkspaceMembers.ts` | hook file 11/11, MessageList 8/8 | tracker per `QueryClient` (WeakMap), state per workspace, logical clock; hook reads `fetchStatus`, effect with no deps |
| 4 | `lib/realtime/useChannelSocket.ts` | socket file 21/21 | `otherReason` then `invalidateQueries(…, { cancelRefetch: false })`; header paragraph |
| 5 | `docs/design/06-frontend-spa.md` | — | §5.2 *Names* paragraph; DM *Naming* bullet |

## What ran
- `npm --prefix src/frontend test` (whole suite): 51 files, 503 passed.
- `typecheck`: clean. `lint`: clean. `build`: built.
- `scripts/test.sh lint unit`: passed (Vitest 503; coverage lines 96.13%).
- `scripts/test.sh e2e` (whole layer): passed, 24/24.
- `conventions.py` over the three production files, and `security.sh`: clean.

## Beyond the tests
- Hook header comment (short id is also the in-flight label; refetch rules): `useWorkspaceMembers.ts`.
- `fetchStatus` read with a "do not remove" comment, decision 13: same file.
- No-dependency-array effect comment: same file.
- `otherMarked` outliving a fetch that never lands: documented on `otherReason` (test-reviewer-2 note).
- Socket header *Read state* paragraph: `useChannelSocket.ts`.
- Doc 06 sweep: only the DM *Naming* bullet and the hook header mentioned the short id as "left"; no other comments needed a change.

## Departures from the plan
- `if (workspaceId)` guard instead of a cast around `otherReason`. Nothing else.

## Picked up from earlier reviews
- test-reviewer-2: `otherMarked` comment added. `isInvalidated` pin: no action.
- Plan-reviewer notes (StrictMode wording, later-mounted consumer): test-side, already taken.

## Left for the human
- The plan's Task 6 first real run: two browsers (second a never-signed-in user), post in #general,
  expect the name without reload and the DM list naming them; restart messaging and watch that no
  name reverts to a short id; count `…/members` requests (one per unknown id, none repeating for a departed one).
- Merge `main` if a sibling branch landed.
