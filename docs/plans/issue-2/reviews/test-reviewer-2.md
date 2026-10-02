# Test review — issue 2, round 2: approved

All four round-1 findings that blocked (1–4) are fixed in the tests, each as I asked, and the fixed tests still fail for the behaviour being missing. The three minors are fixed or accepted with a reason I agree with. Nothing new at major or above.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 (critical) mid-jump no-pull test unpassable | `layoutEveryElement(VIEWPORT)` first (`MessageList.jump.test.tsx:355`) | resolved — the same fix that took my sketch from 14/16 to 16/16; red now `expected 1200 to be 700` (the assertion) |
| 2 (critical) open-channel test ends on a read no build can send | message 26 upserted again after the highlight starts (`:438`), with the reason in a comment | resolved — matches the fix my sketch passed 16/16 with; the mid-jump "no read, no pull" halves kept (`:426-430`) |
| 3 (major) racy `location().search` | `vi.waitFor` at `:211` and `:293` | resolved |
| 4 (major) `:202` join path untested | one body, two runs: `on connect` (`:134`) and `on a live socket` (`:202`, channel null at connect then opened by `rerender`); each asserts the join was emitted, then the exact request sequence and 2 pages kept | resolved — the live-socket variant only reaches the `socket.connected` branch, so a build that reverts `:202` alone fails it. Both red today on `[null,'p2',null]` vs `[null,'p2',null,'p2']` |
| 5 (minor) report overstates | accepted | let go |
| 6 (minor) `q` shown on every route | test navigates to `/c/channel-general?q=zeppelin` (`SearchBox.test.tsx:74-82`) | resolved by reading — the file can't load until `SearchBox` exists |
| 7 (minor) `cancelRefetch: false` unpinned | left for the code-reviewer | carried below |

## What ran

- Vitest over `useChannelSocket`, `MessageList.jump`, `MessageList`, `SearchBox`: 19 failed, `SearchBox` not loaded (`Failed to resolve import "./SearchBox"`). Every first line matches the report's Observed red; the existing `MessageList` and `useChannelSocket` tests still pass.
- No new sketch. The fixes to 1–3 are the ones round 1's sketch already showed green (16/16). Finding 4's twin has the same body as the `:134` test that round 1 showed green against a correct build; the only difference is how the join is reached, which I read against `useChannelSocket.ts:130` and `:197-198`. **Unverified by running** for the live-socket variant and the `SearchBox` route test.

## Findings

None new.

## Left for later stages

- Minor 7 (above): `cancelRefetch: false` on the product's own page fetches is pinned only through `loadOlder`'s idle guard. For the code-reviewer.
- From plan-reviewer-2: B (the Task 9 sweep matches `docs/issues/002.md` and an accepted ADR) and C (the jump's in-flight ref when `loadOlder` declines).
- The BDD journey cannot run here; `search()`'s retry loop and the `highlighted` check are read, not exercised. The first e2e run is Task 10.
- The live-socket join-ack test and the `SearchBox` route test have only been read against a correct build. If either fails in green, check the fixture first.

## Checked and sound

- Round 1's checked-and-sound list stands: the red reasons, the `jump.test.ts` literals, the fake-clock discipline, and the SearchPage, SearchBox and BDD coverage.
- No production code, config or docs written in the rework; only test files changed.
