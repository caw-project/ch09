# Plan review — issue 1, round 2: approved

Both major findings from round 1 are fixed, and I checked each fix against the repo and the
installed libraries. All five minor findings are answered by a decision row or a test. The
fixes broke nothing beside them, and nothing new rises to major, so the plan goes to the test
pair.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The pause-and-return poll test passes before the code exists (major) | `setPageAttention` fires `visibilitychange` on `document` with `bubbles: true`. The test gains a third half: advance `30000` after the return and expect a third `GET`. Its expected red is now `expected 2 to be 3` | **resolved.** Checked:<br>• `focusManager.ts:23` listens on `window`.<br>• jsdom `Document-impl.js:297-303`: `_getTheParent` returns the default view, so a bubbling event reaches that listener.<br>• `test/render.tsx:29-34` sets only `retry` and `gcTime`, so TanStack's default `refetchOnWindowFocus` refetches the stale list once on the return (2 `GET`s). Today the list has no interval, so the third `GET` never comes, and the stated red is right.<br>• After GREEN, the tick at return + 30 s runs, because `queryObserver.ts:404-407` checks `isFocused()`. That holds whether or not the interval restarts on the return's fetch. |
| 2. A workspace switch flushes the pending read instead of dropping it (major) | Decision 30: at call time `send` checks the live session through a pure `isLiveWorkspace(snapshot(), workspaceId)`. New tests: `isLiveWorkspace` in Task 1, an unmount drop with a positive half that sends in Task 2, and a `ChannelView` switch-then-workspace test in Task 3 | **resolved.** Checked in `session.ts`:<br>• `snapshot` is at :72, `State` is exported at :53-56, and `activeWorkspaceId` is on `Session` at :32.<br>• `changeWorkspace` → `adopt` → `set()` writes the module state synchronously and only then notifies listeners. So the state names the new workspace before React renders the switch, whatever order the effect cleanups run in.<br>• A renewal keeps the same `activeWorkspaceId`, so a renewal never drops a read.<br>• The `vi.mock` of `snapshot` reaches only `useSession.ts`, and `ChannelView`, `ChannelList` and `MessageList` don't use it (grep). The mock's `loading` default can't change what those tests render.<br>• Both new tests keep the socket connected, so only decision 30 can stop the emit. Each has a positive half. |
| 3. The throttle window doesn't outlive a visit (minor) | Decision 11 notes it. Decision 28 (**assumed**) records the corner and what changing it would cost | resolved |
| 4. R7's "newest cached one" excludes pending sends without a decision row (minor) | Decision 29 | resolved |
| 5. Remounting per channel isn't flagged against the issue's "do not change" (minor) | Decision 14 names the departure, and *Corrections to the issue* records it | resolved |
| 6. Holds are released when the socket changes (minor) | Decision 12 says so and accepts it | resolved |
| 7. Smaller test details (minor) | The poll test uses the literal `30000`. A 79/80px test is added to `MessageList.reading`. New step: `Grace reloads CollabHub` | **resolved.** Checked:<br>• `giveLayout` (`MessageList.test.tsx:55-66`) defines `configurable` properties, so calling it again at 79 works.<br>• The new step copies `Ada reloads CollabHub` (`steps/conftest.py:116-118`, `ada.open()`). |

## Findings

None at critical or major.

## Left for later stages

- **For the test-writer, on the `ChannelView` workspace-switch test (Task 3):** the rerender with
  a new `workspaceId` fetches the channel detail and history again under new keys. MSW fails any
  request without a stub, so stub them, or hold them with a deferred response. Either way,
  `ChannelView` should be left in its pending state, so that `MessageList` unmounts as it does in
  the app.
- **For the code pair:** decision 30 makes `loading` count as live. That is safe because no
  `MessageList` exists before sign-in. If that ever changes, the rule needs another look.
- Carried over from round 1:
  - **(c) under *What no test covers*:** the journey doesn't wait for the `mark_read` ack before
    the reload. A flake would show as a badge after the reload.
  - **Assumed rows the human should see:** 15 (ceiling), 16 (boundary loaded), 22 (no window
    without a send), 23 (another user's receipt), 28 (A→B→A inside one second sends twice).
  - **Playwright focus:** Task 9 falls back to `bring_to_front`.

## Checked and sound

- **Changed lines:** the edits in decisions 11, 12, 14 and 28–30, *Corrections to the issue*,
  Tasks 1–3, Task 4's new step, Task 6's `send`, and *Self-review*'s workspace-switch row all agree
  with one another. The new `isLiveWorkspace` interface has its own named test.
- **Base commit:** `14d0a04` still matches the worktree's HEAD.
- **Line count:** the plan is 600 lines, the top of the 250–600 range.
- **Unchanged since round 1:** everything recorded under *Checked and sound* in
  `plan-reviewer-1.md` was left alone by this revision and still holds.
