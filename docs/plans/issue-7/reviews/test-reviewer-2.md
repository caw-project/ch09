# Test review — issue 7, round 2: approved

Round 1's one major finding is fixed: the rewritten `each workspace keeps its own departed set` fails a
build with one departed set shared by all workspaces, and passes a correct build. Nothing else changed,
and no new finding.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. R6 test passes with a shared departed set | Load A and B first (both fresh), depart Alan in A, ask in B and require exactly one request there, invalidate B, return to A and `quiet` Alan | **Resolved** — sketched, below |
| 2. `isInvalidated` pin (minor) | Accepted | Let go |

## What ran

- `npm --prefix src/frontend test -- useWorkspaceMembers.test.tsx`: 11 failed / 11. The R6 test fails at
  its first new-behaviour assertion (`expected … length of 2 but got 1`, line 323, "Alan departs in A"),
  after the two preconditions (one request per workspace) held. Matches the report.
- `git status`: same six test/helper files plus the plan dir; no production file.
- Sketch (`build/sketch/frontend`, cleaned), to the plan's tracker and hook:

| Build | Files | Result |
|---|---|---|
| Correct | `useWorkspaceMembers.test.tsx` | 11/11 green |
| One departed set shared by every workspace | same | 10 green, **only the R6 test red** |

The other tests' results for the earlier sketches (round 1) are unaffected: the only file change since is
that one test.

## Findings

None.

## Left for later stages

- `otherMarked` outlives a fetch that never lands (plan-reviewer's note): keep the behaviour, with a comment.
- Round-1 minor 2 (`isInvalidated` pinned in the reconnect test): matches the plan's `invalidateQueries`; no action.
- The converse half of R6 (a fetch in B must not un-depart A's ids) is asserted by the closing `quiet` in A;
  I did not sketch that build separately — by walk-through a clear applied to every workspace would make
  Alan refetch in A and fail `before` — so it is reasoned, not run.

## Checked and sound

- Every round-1 "checked and sound" item stands; the diff since round 1 is the one test.
- The new test's preconditions hold (both loaded and fresh, so no first-load fetch clears a set between steps),
  and its closing `quiet` has its positive (a fresh anchor still fetches).
