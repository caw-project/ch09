# Test review — issue 5, round 2: approved

The one critical finding of round 1 (the `ChannelView` direct-message test that no correct build could pass) is fixed, and the fix
goes green against a correct sketch and red against the wrong build it targets. Nothing else changed in the tree beside that file.
This is a rework pass: expectations stay as written in round 1, and untouched work was not re-reviewed.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 (critical) `ChannelView` DM test: placeholder reads `Reconnecting…`; `/members` check also matched the workspace directory call | Block-level `beforeEach` sets `connectionStatus` to `'connected'`; the request check now matches `/channels/${dm.id}/members` | **Resolved** — both defects gone (below) |
| Minor: counts 7+7 not 8+8, REST-only "later message", switch test not pinning the new list, sender's own connection | Acknowledged, left for later stages | Let go, listed below |

## What ran
- `git diff src/frontend/src/features/channels/ChannelView.test.tsx`: the `beforeEach` with `setConnectionStatus('connected')` and the
  `/channels/${dm.id}/members` match are there; no pre-existing assertion touched.
- `npm --prefix src/frontend test -- src/features/channels/ChannelView.test.tsx` → 12 passed, 2 failed. The two failures are the DM
  cases, at `Unable to find role="textbox" and name "Message Grace Hopper"` (the thread case's `getByRole` at line 551) — the missing
  feature, the plan's reason.
- **Sketch, correct** (`sketch.sh frontend`; a DM label in header and composer, no `MemberPanel` for a DM; hard-coded to the fixture,
  as a probe) → `ChannelView.test.tsx`: **14 passed** — the repaired test and the thread case are green; both defects of round 1 are gone.
- **Sketch, wrong: member panel still rendered for a DM** → the DM test **red**, 13 passed.
- `sketch.sh clean` run; no sketch left in `build/sketch`.

## Findings
None.

## Left for later stages
- Report counts: `directMessages.test.ts` and `DirectMessageList.test.tsx` have 7 tests each (14, not 16).
- Socket "later message announces nothing" is proven on REST only; a build that skips the first-message check on the socket path alone
  would pass. The shared helper is the plan's design, so low risk.
- The workspace-switch test doesn't pin that the new workspace's list is left alone.
- The sender's own connection hearing `channel_added` is unpinned (plan is silent; reported departure, accepted).
- The Python integration tests were reasoned, not sketched against a correct route (round 1); the code-writer's run is the check.

## Checked and sound
- Everything in round 1's *Checked and sound* stands: red for the plan's reason, existing tests unchanged, report matches the tree,
  guards have positive halves, races proven in both orders, BDD binds.
- The repaired test proves its negative after the view has rendered (composer found first), so "no panel" cannot pass for a view that never mounted.
