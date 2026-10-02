# Code review — issue 2, round 1: approved

The build does what the plan says, task by task, and every check the plan names is green: Vitest
296, typecheck, lint, build, and the e2e layer's 21 of 21 with the search journey in
`build/test-results/e2e.xml`. All eight mutants survived the approved suite, and my probes catch
only one of them. Five probes of paths no approved test takes all pass on the real code. So what the
mutants changed is held by reading alone (*Unpinned*), but none of it is wrong. One minor finding: a palette class that doesn't exist.

## Expectations                 (round 1 — written before the code was opened)

**Task 5 — `searchMessages`, `jump.ts`, `loadedPageCount`, `refetchHistory`, the join-ack call sites.**
- *No test pins:* `refetchHistory`'s `direction === 'forward'` half (a build waiting on *any* fetch,
  a refetch included, passes both `refetchHistory` tests: neither has a refetch in flight when it is
  called); `exact: true`; the subscription unsubscribing once it fires; the docstring paragraph in
  `useChannelSocket.ts` on join refetches.
- *Takes for granted:* `fetchMeta.fetchMore.direction` is set by `fetchNextPage` and the cache's
  `updated` event reaches the listener synchronously, before observers re-render — so the refetch
  starts before the jump's effect can ask for the next page (Timing 2 needs exactly that order).
- *Could go wrong:* a subscription that never fires (query removed) leaks; a page fetch that errors
  → idle with `status: error` must still lead to the refetch (recovery); calling it twice while a
  page is in flight subscribes twice → two invalidations (harmless, one cancels the other).
- *Wrong build:* drop the direction check (survives, I expect — mutate); call `invalidateQueries`
  inside the listener without re-checking (fine).

**Task 6 — `useMessageJump`, `MessageList`, `useMarkRead.flush`, `MessageItem`.**
- *No test pins:* `{ replace: true }` on the param removal (tests read only `location()`); the
  `cancelRefetch: false` on `loadOlder`'s `fetchNextPage` (test-reviewer 7 — covered by the idle
  guard only); clearing the timer on unmount; `tooFarBack` cleared when another jump starts
  (decision 22); `onScrolled()` after give-up (no test reads a read or `atBottom` after the cap);
  `olderWanted`'s "still within `LOAD_THRESHOLD`" check; `transition-colors duration-700` /
  `bg-accent/15`; the third docstring paragraph; `flush` memoised.
- *Takes for granted:* the render-time adoption sees the hook's own param removal while the phase
  is already `highlighting` (else found → removal → "gone while seeking" → abandon); the effect's
  deps include `isFetching`/`messages`, so a declined `loadOlder` (cache fetching, render idle)
  is retried when that fetch ends; `previousCount === 0` on the first render with data, cached or
  not; `error` from a failed page fetch makes `MessageList` render its alert (its existing early
  return).
- *Could go wrong:* **a new target arriving while the old one is *highlighting*** — the plan
  restarts `target`/`phase`/`tooFarBack` but does not say `highlightedId` is cleared; the old
  timer is cleared, so if nothing else clears it the old message stays highlighted forever (and
  for good if the new jump gives up or fails) — "only the latest target is ever … highlighted"
  (R9). The only latest-wins test switches during *seeking*. Probe. Also: same-id resubmit after
  the hook removed the param must restart (seenParam must follow the removal); a give-up whose
  stale `atBottom` keeps the read rule off after the jump ends; the hook calling `loadOlder` after
  unmount; the scroll handler and the jump both fetching (one at a time by the idle guard).
- *Wrong builds:* no `replace` (survives); no `highlightedId` reset on restart (survives?); no
  `onScrolled` at give-up (survives?); `loadOlder` without the idle guard (Timing 1 catches);
  no `flush` (caught); growth pull without `previousCount === 0` (caught by `pages back…`).

**Task 7 — search UI.**
- *No test pins:* `retry: false` and `staleTime: Infinity` on details; the box's `key` remount
  (pinned behaviourally); "Searching…"; `data-testid`s (BDD only); date format; Load more while a
  page is fetching (double click → two `c2` requests? TanStack dedupes `fetchNextPage` while
  fetching unless `cancelRefetch`). Workspace id in `searchKeys` (pinned).
- *Takes for granted:* `useWorkspaceMembers` and `useChannels` are usable from `/search` (no
  channel open); `ChatLayout` is the shell for `/search` so the socket and sidebar stay.
- *Could go wrong:* invalidate-then-navigate on a *different* q is harmless; comparing the URL by
  string where the current `q` is untrimmed or encoded differently; a Retry that shows while data
  exists; `#…` for a channel whose list failed.

**Task 8 — e2e harness.** `E2E_SCALE` gone; per-worktree project (human answer) on every compose
call incl. teardown and hint, `down -v --remove-orphans` after the lock; lock kept; comments
updated; `docker-compose.test.yml` comment; README lines. `CLAUDE.md` untouched (human's).

**Task 9 — record.** Doc 06 §5.4 (box, route, cache key, row, Load more, names, the jump's wait /
`cancelRefetch: false` / `refetchHistory` / cap 10 / 2 s / `data-highlighted` / notice / removal /
abandon / latest-wins, the read exception); §4 unified-search line; §5.2 join-refetch bullet; D8c
note; the ADR. Each claim against the code.

**Task 10 / evidence.** `docs/test-report.md` at this tree with `-dirty`: unit ≥ 565 + new, e2e 21
with the search journey in `build/test-results/e2e.xml`.

## What ran

- `npm --prefix src/frontend test`: 31 files, **296 passed**. `run typecheck`: clean. `run lint`:
  clean. `run build`: built (379 kB JS).
- `bash -n scripts/test.sh`: clean. `python3 .claude/hooks/checks/conventions.py` over the 15 changed
  or new production files, plus the two BDD files: no findings.
- Evidence for `scripts/test.sh`'s layers: `docs/test-report.md` is at `950e66a2d292-dirty` (HEAD is
  `950e66a`). It shows Lint passed, Unit **618** (frontend 296), End-to-end **21**, and a *Search*
  section, "Ada finds a message and opens it in its channel ✅". `build/test-results/e2e.xml`:
  `tests="21" failures="0" errors="0"`, with `test_ada_finds_a_message_and_opens_it_in_its_channel`
  among them. Integration shows "not run". The plan names no integration layer (see *Left for
  the human*).
- `git status --short`: every changed file is in the plan's file map or the human's answer. No
  service code changed (`messaging/search.py` is clean). `CLAUDE.md` is untouched.
- **Mutants** (sketch, one at a time, each reverted). Every one **survived** the approved tests:
  1. `useMessageJump.ts` `{ replace: true }` → `false`: `MessageList.jump` and `ChannelView`, 25
     passed.
  2. `MessageList.tsx` `loadOlder` with no `cancelRefetch: false`: `MessageList.jump`,
     `MessageList` and `ChannelView`, 32 passed.
  3. `useMessages.ts` `refetchHistory` waits on any fetch (direction check dropped): `useMessages`,
     `useChannelSocket`, `MessageList.jump` and `MessageList`, 67 passed.
  4. `useMessageJump.ts` doesn't clear `highlightedId` on restart: the approved 25 passed. **Probes
     P1 and P1b fail** (the old message stays highlighted).
  5. `useMessageJump.ts` give-up with no `onScrolled()`: `MessageList.jump` plus the probes, 21
     passed.
  6. `MessageList.tsx` deferred older load with no `scrollTop < LOAD_THRESHOLD` check:
     `MessageList` and `MessageList.jump`, 23 passed.
  7. `SearchBox.tsx` navigates on every submit (a duplicate history entry): `SearchBox`, 7 passed.
  8. `useChannelNames.ts` doesn't wait for the list to settle: `SearchPage`, 15 passed.
- **Probes** (`MessageList.probe.test.tsx` in the sketch, real code). All **passed**:
  - P1: a second result clicked while the first is highlighted. Only the second is highlighted,
    and `scrollIntoView` goes to `[a, b]`.
  - P1b: a second result that gives up clears the first highlight.
  - P2: the same result clicked again after its jump ended (param already removed) jumps again.
  - P3: after a give-up, the read rule applies: `mark_read` for the newest, and `readingChannelId`
    is the channel.
  - P3b, the control for P3: with page `p6` held mid-seek and 1.5 s waited at the bottom with
    attention, nothing is read and `readingChannelId` is null. The first version of P3b failed
    because its check landed after the seek had already ended. That was the probe's timing, not
    the code: holding `p6` fixed it.
- `sketch.sh clean` run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| 5 `searchMessages` | `lib/api/messaging.ts:178` | as planned |
| 5 `jump.ts` constants, `nextJumpStep` precedence | `jump.ts:12-50` | as planned |
| 5 `loadedPageCount`, `refetchHistory` (direction test, subscribe, re-call) | `useMessages.ts:91-124` | as planned |
| 5 both join-ack sites + docstring | `useChannelSocket.ts:30-33,138,206` | as planned |
| 6 hook state, render-time adoption, abandon while seeking, restart clears highlight/notice | `useMessageJump.ts:61-78` | as planned |
| 6 in-flight ref | none; `loadOlder`'s idle-now guard | departed (recorded, holds: a declined `fetch` is retried when the render's `isFetching` goes back to false — the effect's deps) |
| 6 found / give-up / failed / fetch actions; timer + cleanup | `useMessageJump.ts:105-160` | as planned |
| 11 `beingRead … && !jumping`; 28 `flush` on jumping | `MessageList.tsx:180-183,205` | as planned |
| 26 growth pull `(!jumping \|\| previous === 0)` | `MessageList.tsx:249-256` | as planned |
| 27 `loadOlder` idle-now, `cancelRefetch: false`, anchor | `MessageList.tsx:141-147` | as planned |
| 9 / R8 `olderWanted` + effect + threshold; docstring ¶3 | `MessageList.tsx:18-26,180-186,229-236` | as planned |
| 13/14 `data-highlighted`, `transition-colors duration-700`, `bg-accent/15` | `MessageItem.tsx:97-99` | as planned |
| notice `role="status"` `jump-notice` above scroller | `MessageList.tsx:283-291` | as planned (finding 1) |
| 17 search options; select unreversed | `useSearch.ts` | as planned |
| 20 names after settle; `retry:false`, `staleTime: Infinity` | `useChannelNames.ts` | as planned |
| 16/18 Retry only without data; blank prompt; "Searching…" | `SearchPage.tsx:36-59` | as planned |
| 19 invalidate, navigate only if the URL differs; key remount; `maxLength` | `SearchBox.tsx` | as planned |
| 15/24 `<Link>` row, `<time>`, plain body, `(edited)` | `SearchResult.tsx` | as planned |
| 23 box first in `<aside>`; `/search` protected | `ChatLayout.tsx:56`, `App.tsx` | as planned |
| 8 `E2E_SCALE` gone; README; compose comment | `scripts/test.sh`, `README.md`, `docker-compose.test.yml` | as planned. The per-worktree project and `down -v` follow the human's answer; the log tail on failure is recorded |
| 9 doc 06 §4, §5.2, §5.4; D8c; ADR | as in the diff | as planned; §5.4 sits above §5.3 (recorded) |
| 10 first real run | — | not done, listed for the human |

## Findings

### 1. The jump notice's border uses a colour the palette doesn't define — minor
**Where:** `MessageList.tsx:287` · **Checked:** Grep over `src/frontend/src`. `index.css` defines
`--color-border` and no `--color-line`. `border-line` appears nowhere else.
Tailwind v4 generates nothing for `border-line`, so the bottom border falls back to the default
colour (`currentColor`, the muted text grey), not the palette's `border-border` that every other
divider uses. Fix: `border-border`. Cosmetic, and no test can see it.

## Unpinned

What only reading protects. For each, the code is right as it stands:
- **`replace: true`** on all three param removals (mutant 1). Read at `useMessageJump.ts:86-93`.
- **`cancelRefetch: false`** (mutant 2). The idle-now guard makes it redundant, except for a fetch
  that starts between the guard and the call. Present at `MessageList.tsx:146`.
- **`refetchHistory`'s `direction === 'forward'`** (mutant 3). Without it, a join ack landing on a
  *refetch* would wait rather than cancel it. Nothing would be lost either way. Present.
- **Restarting from `highlighting` clears the old highlight** (mutant 4). R9: "only the latest
  target is ever … highlighted". Only my probes P1/P1b pin it. The approved latest-wins test
  switches during *seeking*. Worth a test some day.
- **`onScrolled()` at give-up** (mutant 5). The layout effect re-measures `atBottom` when
  `jumping` changes, so the read rule still resumes (P3). `onScrolled` also refreshes
  `wasAtBottom`, so the next arrival after the notice follows to the bottom. Nothing tests that.
- **R8's deferred load only if still near the top** (mutant 6, decision 9, assumed).
- **No duplicate history entry on resubmit** (mutant 7, decision 19). Present at
  `SearchBox.tsx:37`.
- **Names wait for the channel list to settle** (mutant 8, decision 20). The fixtures always settle
  the list before results arrive. Present at `useChannelNames.ts:25-28`.
- From test-reviewer-2: the live-socket join-ack test and the `SearchBox` route test, both read
  only at red, now pass against this build.

## Left for the human

1. **Finding 1** (minor): change `border-line` to `border-border` at `MessageList.tsx:287`.
2. **Question: R6 and a failed refetch with data.** Decision 16 shows Retry only when there is no
   data. Back to `/search` while Elasticsearch is down refetches, gets a 503, and shows "Search is
   unavailable." over the cached list with **no Retry** (Load more only if there is a next page).
   R6 says a 503 shows a Retry. The workaround today is Enter in the box, which refetches. The other
   reading is a Retry whenever `error` is set and no page fetch failed: one condition in
   `SearchPage.tsx`.
3. **Question: Back during the highlight on the same channel.** Decision 12 abandons only while
   *seeking*. Back from a jump on the open channel lands on `/c/A` with no param change (the hook
   already replaced the entry), so the highlight runs out its 2 s. That is harmless, and within
   decision 12.
4. `docs/test-report.md` shows **Integration "not run"**. This worktree had no earlier integration
   result, and the plan names none (no service code changed). Run
   `scripts/test.sh integration` before merge if the committed report should show all layers.
5. From the green report: change `CLAUDE.md:229-230` (the test stack runs ES and the Worker;
   per-worktree project), remove the old `collabhub-test_*` volumes, move §5.4 below §5.3 if
   wanted. `testkit/report.py`'s semgrep finding was there before this work.
6. **First real run** (plan Task 10, all six checks). Look especially at centring, the 2 s fade, the
   notice's look, and a target centred near the top loading an older page (decision 27).

## Checked and sound

- Render-time adoption: the hook's own removal arrives while `phase` is `highlighting`/`idle`, so it
  never reads as an abandon. The approved found test and P2 show the param is removed and a repeat
  click restarts.
- The jump's effect deps include `isFetching`, so a `loadOlder` declined against the cache
  (plan-reviewer-2 C) is retried when the fetch ends. There is no stuck seek.
- `refetchHistory`'s listener runs synchronously in the cache dispatch, before observers re-render,
  so the refetch starts before the jump can page again (Timing 2's exact sequence passes).
- Hooks run before `MessageList`'s early returns, so a failed page's alert and the hook's `failed`
  step coexist. The timer is cleared on unmount and on restart.
- The divider capture may now land between two jump pages. Its ceiling is still the newest
  message, as the issue's *Where the rules meet* allows.
- Search: workspace in the key; `enabled` on blank; no focus or reconnect refetch; select not
  reversed; plain-text body; `#…` placeholder; testids on input, link, Load more, empty, notice.
- No test, fixture or generated file changed by the code-writer; no Messaging change; no
  suppression comments; no Zustand server state (`jumping`/highlight are component state).
- Docs: §5.4, §4, §5.2, D8c and the ADR each match the code as read.
