# Test review — issue 1, round 2: approved

The one critical finding from round 1 (the cached-return test failing against a correct build) is fixed
in the test. I read the fix but **could not run it**: Bash was denied in this session, so neither the
Vitest run nor the sketch was available. The rest of round 1's verified result stands, since nothing
else is reported changed. Approved with that limit stated.

## Responses checked

The red report is still headed "round 1" and has no *Review responses* section, so the writer's answer to
each finding is not recorded. I checked the tree instead.

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Cached-return test fails on a correct build (critical) | none written; test changed | **resolved, unrun.** `ChannelView.test.tsx` lines 342–372: the page is hidden at the start (342), and `setPageAttention({ visible: true, focused: true })` now comes *after* `open(/general/)` (361). `#random`'s list is unmounted by the click (fireEvent inside act, `key` per channel), so the only read the rule can allow is for `#general`. The assertion at 372 (`marks(socket)` is `[]` after one gate opens) can pass on a correct build. The wrong build — capturing before both refetches — still fails it, because the divider/emit would appear after one gate only. The comment at 359–360 states the order. |
| 2. "Refetches once" doesn't separate a double fire (minor) | none | left as a minor for the code pair, as in round 1 |

## What ran

- Nothing. `Bash` was refused ("don't ask mode"), so neither `npm test`, the typecheck, nor
  `sketch.sh` could run. I used Read and Grep on `ChannelView.test.tsx` (lines 334–385) and the red
  report. The fix is **unverified by running**.
- Round 1 results still apply to everything the writer did not touch: 38 of 38 new tests red as
  planned; 5 files fail to load by design; every other test went green against a correct sketch;
  `typecheck` and BDD binding as reported.

## Findings

### 1. No *Review responses* in the red report — minor
**Where:** `02-red-tests.md` · **Checked:** read the file in full; headed "round 1", no responses section.
The fix is in the test, so nothing is lost, but the report's departure entry (line 92) now reads
"keeps the page hidden until the click", which is close but not exact: attention turns on right after the
click. For the code pair: trust the test, not the sentence.

### 2. Run the fixed pair first — minor, for the code-writer
Not run by me. The code-writer's first run of `ChannelView.test.tsx › returning to a cached channel`
should be green once `key`, the capture and the list refetch are built. If it is red, check the order of
`setPageAttention` against `open(/general/)` before suspecting the build.

## Left for later stages

- Finding 2 from round 1: the "once, not twice" focus refetch is not proven by the tests; act only if the
  real-browser run (Task 9) shows two requests.
- The report's "Review responses" and departure wording (finding 1 above).
- Carried from round 1 and plan-reviewer-2: the journey doesn't wait for the `mark_read` ack before the
  reload; assumed decisions 15, 16, 22, 23, 28 for the human; the Playwright focus fallback in Task 9;
  the 1.2 s real-time sleeps in two component tests.

## Checked and sound

- Round 1's verified results (red for the right reason, no production code written, existing tests intact,
  coverage of every plan test, wrong-build sketches) stand; this round changed one test only.
- The fixed test keeps its positive half: after both gates open it waits for the divider and for
  `markIds(socket)` to equal `[idIn(GENERAL, 3)]`.
- Sketch cleanup: no sketch was created this round, so there is nothing to clean.
