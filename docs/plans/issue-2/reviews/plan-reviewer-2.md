# Plan review — issue 2, round 2: approved

All four major findings from round 1 are fixed, and each fix holds against the code and the installed
TanStack 5.101.4: the Timing 1 fixture now starts the refetch before the jump can look, the
cached-pages test separates the two readings of R7's cap, the open-channel jump has a start rule and a
test, and the list's position and scroll handler during a seek are decided in rows 26–27. The minor
findings are fixed too. Two small things from this pass go to the test and code pairs below.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Timing 1: wrong red, a fixture a correct build fails | Page 1 seeded, the mount refetch held from the first render; red is the final cursor assertion; the wrong build named (plan :294) | **resolved** — `queryObserver.ts:461-474` sets the optimistic `fetchState` when `shouldFetchOnMount`; the test client has no `staleTime` (`test/render.tsx:31`), so a cached mount is fetching from its first render. The "none while held" half passes at red, and the plan says so and names the build it fails |
| 2. Cached pages counted: no test fails the wrong reading | `counts pages cached before the jump towards the ten`: 4 cached, target on page 11, no `p11` (:287) | **resolved** — the mount refetch re-fetches `null…p4` (fresh cursors), the jump `p5…p10`; a build counting its own calls asks `p11–p14`. Two readings, two outcomes |
| 3. Jump into the open channel: no start rule, no test | Row 11 adopts the param during render; row 28 (assumed) flushes a held read; new test (:295) | **resolved** — `ChannelView` keeps `MessageList` mounted on a param change, so render-time adoption makes `beingRead` false in the commit the param arrives in, before the read effect (`MessageList.tsx:135-137`) runs. `readThrottle.ts:64-71` `flush` exists and sends the held read; `useMarkRead.ts:95-100` is where it is exposed. Row 28 is a recorded, defensible reading |
| 4. Where the list sits while seeking; the scroll handler | Row 26 (first scroll to newest, then no pull; prepends anchored via `loadOlder`); row 27 (assumed): handler armed, one page fetch at a time | **resolved** — `previousCount` starts at 0 (`MessageList.tsx:75`), so `previousCount === 0` lets a fresh list, cached or not, make its first scroll; `queryClient.isFetching(filters)` counts `fetchStatus: 'fetching'` (`queryClient.ts:107-112`), so "idle now" is real. Pinned by `pages back…` (`scrollTop === scrollHeight` while held) |
| 5. Sibling-branch line | Corrected (:168) | resolved |
| 6. README by-hand command | `README.md:191-192` in the map and Task 8 | resolved — line 192 holds it |
| 7. `--exclude-dir` | `git grep … ':!docs/plans'` | resolved as asked — but see note B |
| 8. R2 details | Reconnect in the focus test (:382); row 17 says every page refetches | resolved |
| 9. R8 `heightBeforePrepend` half | `giveLayout` 100 px taller, `scrollTop` still 0 before any prepend (:306) | resolved — `onScroll` at the top sets `wasAtBottom` false, so the refetch's growth doesn't pull, and only a stale `heightBeforePrepend` could move `scrollTop` |

## Findings

None open at critical or major.

## Left for later stages

- **A. The open-channel test's no-pull half (test-writer, test-reviewer).** In `holds reads off when a
  jump starts on the open channel…` (plan :295), the first `upsertMessage` happens at the bottom with an
  unfrozen `giveLayout`, so the list's own pull writes `scrollTop = scrollHeight`. The mid-jump upsert's
  "`scrollTop` unchanged" is then true for a build that pulls too — a pull writes the same value. Reset
  the layout (`giveLayout` again, `scrollTop = scrollHeight − clientHeight`) after the navigation and
  before the mid-jump upsert. Not blocking: the same guard is pinned on the fresh-mount path by
  `does not pull to the bottom when a message arrives mid-jump`, and this test's real point — no
  `mark_read`, the flush, the read after — is sound.
- **B. Task 9's sweep can't return nothing (code-writer).** `git grep -i -e "scale elasticsearch"
  -e "scale worker" … ':!docs/plans'` also matches `docs/issues/002.md:57,208` (the issue) and
  `docs/adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md:91` (an accepted ADR). Neither is
  to be rewritten: exclude `docs/issues`, and for the ADR either exclude it or add a dated
  "superseded by issue 2" note rather than editing its body. I could have seen this in round 1.
- **C. The jump's in-flight ref (code-writer).** Task 6 guards `fetch` with an in-flight ref, and row
  27's `loadOlder` may decline when a fetch began between the render and the effect (a join ack). Clear
  the ref when `loadOlder` declines, or on the next history change, so a declined step can't strand the
  seek. `waits for a refetch already in flight…` and Timing 2 would catch a stuck seek only if the
  timing lines up; the code-reviewer should read for it.
- Rows 9, 18, 20, 21, 22, 23, 27 and 28 are **assumed** and defensible — for the human at the end.
- From round 1, still standing: row 6 vs. Timing 1 (a join ack arriving after the jump started waits
  for the jump's page; harmless); the pre-existing first-load join-ack race (`query.ts:411`), not this
  issue's to fix; the R10 correction to `data-highlighted`.

## Checked and sound

- Plan 599 lines, within 250–600; header base `950e66a` matches `git log -1`; RED 1–4 before GREEN 5–7
  with the test-reviewer gate; *Found while building* empty; no task commits; Review responses
  answer all nine findings.
- New rows 26–28 and the changes to 11 are decision rows, not silent changes in tasks; the Self-review's
  *Paths* row now maps the open channel to its own test.
- `README.md:192,210`, `scripts/test.sh:229,290` are where the file map says — Task 8 covers each.
- Expected reds of the changed and new tests are what the runtime would report: no jump exists today,
  so the cursor, status and attribute assertions fail on their own; the open-channel test's
  "1 where 2 expected" is today's throttle holding the read for its window.
