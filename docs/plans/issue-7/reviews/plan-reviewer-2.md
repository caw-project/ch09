# Plan review — issue 7, round 2: approved

Approved. Both major findings from round 1 are fixed. `quiet(id)` now waits for the
directory to settle before the anchor exists, so a wrongly started fetch shows up as
`before + 2`. Decision 20 makes a reconnect that joins the tracker's own fetch still clear
the departed set, and Task 2 row 2 pins it. The three minor findings, and the four items
under *Left for later stages*, are all taken up. Nothing new reaches major.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The anchored negative can't fail the builds it targets (major) | `quiet(id)`: settle, take the baseline, ask, **settle again**, then ask the anchor and assert `before + 1`. `settleDirectory` waits for idle and checks it again a macrotask later | **resolved** — see below |
| 2. A fetch for another reason joining the tracker's own fetch (major) | Decision 20: `otherReason(ws)` in `onConnect`, read at landing. Decision 21 (**assumed**): a stale mount or focus that joins isn't detected, and its cost is stated. Task 2 row 2 asserts #4 for departed Alan after the joined reconnect | **resolved** |
| 3. Decision 7 filed as "decided by the issue" (minor) | Moved to *taken in this plan*, marked **assumed**, with the other reading and its cost | resolved |
| 4. Doc 06 "within 5 minutes" (minor) | "at the next refetch after the 5 minutes are up (…)" | resolved |
| 5. Corrections 2 put `useChannelNames` in a `useMemo` (minor) | Now "plain render code (`useChannelNames.ts:30-48`)" | resolved |
| Left for later: StrictMode sentence, later-mounted consumer, no `rerender()` in row 4, settled count in the MessageList test | Each taken up in decision 8, *How each test is built*, row 4 and the Task 2 table | resolved |

**F1, checked.** Take the build that refetches for a departed id. Step 2's `rerender()`
starts the fetch synchronously inside the effect. Step 3's `settleDirectory` sees
`isFetching > 0` and retries until that fetch lands and the re-render it triggers has run.
`membersBy` answers every call past the last one named, so the fetch always lands. The
anchor's fetch then makes the count `before + 2`, and the test fails, as the plan says. A
build that loops never settles, and `waitFor` times out. What I checked:
- `notifyManager.ts:15`: the default scheduler is `systemSetTimeoutZero`, and
  `@tanstack/react-query/src` never overrides it (grep for `setScheduler` or
  `setBatchNotifyFunction` finds nothing). So a fetch that lands in the first wait has its
  observer notification queued ahead of the second wait's timer, and the second idle check
  sees any follow-up fetch.
- Vitest's `waitFor` (`chunks/index.m3L2HgmY.js:7125-7171`) awaits a thenable callback. A
  rejection sets `promiseStatus = "rejected"`, and the next interval calls the callback
  again. So an async `settleDirectory` callback does retry, and doesn't fail on its first
  rejection. Nothing in it uses fake timers, which the shared context rules out near
  `waitFor`.

**F2, checked.** I traced Task 2 row 2 through `saw` and `load` as specified:
1. Alan departs on #2.
2. Grace starts #3, which is `own`.
3. The connect marks the workspace and joins #3. `query.ts:414-418` with
   `cancelRefetch: false` returns the existing promise, so no `queryFn` runs.
4. At landing, `otherMarked` clears `departed`, and Grace is named.
5. The re-render's `saw` asks for Alan, which starts #4. #4 lands without him, and he
   departs again.

A build without `otherReason` makes no #4, and a build with the default `cancelRefetch`
shows 4 requests while #3 is held. Both fail. Decision 21's citations hold:
`queryObserver.ts:99-100` → `#executeFetch()`, and `query.ts:336,345` pass
`cancelRefetch: false`.

## Findings

None open.

## Left for later stages

- **`otherMarked` outlives a fetch that never lands** (code pair, minor). `load` resets the
  mark only on a successful landing. If the reconnect's fetch fails, or `invalidateQueries`
  starts no fetch because the query has no observer, the mark stays set, and the tracker's
  next *own* fetch clears the departed set. The cost is one extra request per departed id
  on screen, the same cost decision 7 already accepts. The departed set itself is right
  either way. The code-writer should keep this behaviour and give it a comment, rather than
  "fixing" it into a leak of the mark.
- **Test pair:** `settleDirectory` needs both idle checks, each after its own macrotask.
  Collapsing them into one wait-then-check lets a follow-up fetch from the re-render slip
  past. That is decision 13's case, the one row 4 depends on.
- Still open from round 1's record: decision 8's StrictMode claim is now worded correctly.
  Nothing more for later stages.

## Checked and sound

- Base commit `dca6fbb` = `git log -1`. The worktree is clean apart from
  `docs/plans/issue-7/`. The plan is 482 lines, within 250–600.
- Header and sections follow the exemplar. RED (1–2) comes before GREEN (3–4), with the
  test-reviewer gate. *Found while building* is empty. No task commits.
- The Review responses section covers every round-1 finding by number, and every
  *Left for later* item.
- The new interface `otherReason` is named in Task 3's interface, Task 2's contract and
  Task 4. Task 2 row 2 tests it. The file map's Task 4 row includes it.
- Doc 06 wording in Task 5 now records decisions 20 and 21. The *Naming* bullet change
  and the comment sweep are unchanged from round 1, which passed them.
- Expected reds are unchanged in kind. No new production symbol is imported at red, so
  there's no load failure.
