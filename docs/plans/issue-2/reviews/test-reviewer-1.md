# Test review — issue 2, round 1: changes_requested

The red is real: all 23 runnable new tests fail for the reasons the report gives, and 29 sit in three files
that fail at import, rightly. But run against a correct sketch, 2 tests can never go green (one
fixture trips the plan's own `heightBeforePrepend`, one asserts a message TanStack discards), 1 is flaky, and the
join-ack fix is pinned at only one of its two call sites. Two critical, two major, three minor.

## Expectations

Written before the red report or any test file was opened; read: issue, plan, plan-reviewer-2, and
`MessageList.tsx`, `useMessages.ts` as they stand.

- **`nextJumpStep` (jump.test.ts).** Today: `Failed to resolve import "./jump"`, every test. Vacuous: a
  cap test pinned on one side only (10 → give-up without 9 → fetch); `wait` vs `found` precedence tested
  with only one input set; `failed` not shown to beat `wait`/`found`. Wrong builds: `>` for `>=` at the
  cap; `found` checked before `fetching`; `give-up` instead of `fetch` when `hasNextPage` false with <10
  pages, or the reverse. Must also pin "found on the tenth page beats the cap".
- **`loadedPageCount` / `refetchHistory`.** Today `is not a function`. Vacuous: asserting only that
  the cache has 2 pages (an invalidate that cancels still leaves 1... but a build that never refetches
  also passes). Must show: no `cursor=null` request while the page is held, the page kept, then a refetch
  of `null` then the page-2 cursor; and the idle path (invalidate at once). Wrong build: plain
  `invalidateQueries`; or a wait that never refetches afterwards.
- **Join-ack vs page fetch (useChannelSocket).** Today: `expected 1 to be 2`. Vacuous: ack replied
  before the page fetch is in flight. Wrong build: ack handler wired to `refetchHistory` on one of two
  call sites only (`:134` and `:202`) — a test over one site passes.
- **Jump in MessageList.** Today the spy never fires. Vacuous versions: fade timer with `vi.waitFor`
  under fake timers; "no mark_read" checked synchronously; "does not pull" with a frozen layout; cap
  test where cached pages and own fetches coincide; "abandon" passing because nothing ever jumps (needs
  the held page to prove the jump was actually in flight); latest-wins where A and B pages coincide;
  the open-channel "no pull" half (plan-reviewer note A). Wrong builds: cap counted from the jump's own
  calls; read sent during jump on the open channel; param left in URL; highlight never removed; notice
  with the failed fetch; looking while fetching and cancelling the refetch.
- **R8 scroll-to-top.** Today an `older` request is made while the refetch is held. Vacuous: not
  growing `scrollHeight` so a stale `heightBeforePrepend` shows nothing; not checking the older page is
  requested after the refetch lands (a build that drops the wish passes).
- **ChannelView jump into another channel; App route.** Spy never called / "No such page.".
- **SearchBox / SearchPage.** Today: import failures, whole file. Hence a load failure hides everything
  by design (every test needs the module) — acceptable. Vacuous: reversing order with one item; "plain
  text" with no `<b>` element check; "(edited)" on every row; 404 name test where list also lacks the
  channel; "no fetch for list channel" asserted before list settled; "no live update" without a positive
  remount half; workspace switch without token check; `maxLength` test passing because userEvent respects
  it anyway (fine); blank submit then valid submit. Clauses: "trimmed", "at most 200", "newest first",
  "a page shorter than the limit does not end the list", `No messages match "x".` with no caveat, 503 text.
- **BDD.** Parse + bind only; steps reuse existing; unique word; the Then ends on server state.
- **Config/doc files:** nothing outside tests may change (scripts/test.sh etc. are GREEN Task 8).

## What ran

- Vitest, nine files (jump, useMessages, useChannelSocket, MessageList.jump, MessageList, ChannelView, App,
  features/search ×2): 23 failed, 57 passed, 3 files not loaded (`./jump`, `./SearchBox`, `./SearchPage`). Each first
  line matches the report's *Observed red* (the join-ack test fails one line earlier than the plan's, as the report says).
- `npm run typecheck`: the 7 missing-module/export errors the report lists, nothing else.
- `uv run pytest tests/bdd --collect-only -q`: 21 collected, includes the search scenario;
  `--generate-missing`: no stubs. The journey cannot run here (Compose); read, not run.
- Sketch (`build/sketch/frontend`, removed with `sketch.sh clean`): a correct build of `jump.ts`, `refetchHistory`,
  `loadedPageCount`, `useMessageJump`, the `MessageList` changes, `flush`, `data-highlighted`, `searchMessages`,
  `SearchBox`, `SearchPage`, the route and the box in the aside.
  - **Correct build:** `jump`, `useMessages`, `useChannelSocket`, search ×2, App, ChannelView: all green.
    `MessageList.jump`: **14 of 16 green, 2 red** — findings 1 and 2. With those two fixtures patched in the sketch
    copy only, 16 of 16 pass. `jumps to a message already loaded` failed in 3 of 4 whole-directory runs and passed
    alone — finding 3.
  - **Wrong builds, caught (red):** no read guard (2 tests); pulls while jumping (2); blocks the first scroll while
    jumping (`pages back`); cap at `>` instead of `>=` (3); never waits on fetching (14); looks while fetching, default
    `cancelRefetch`, no idle guard (Timing 1 and 2); onScroll fetches during a refetch (R8); drops the remembered older
    wish (R8); no flush (open-channel test); `refetchHistory` plain invalidate (4); waits but never refetches (3);
    first target sticks (`follows only the latest`); no abandon on param removal; reversed results (3); focus/reconnect
    refetch; key without workspace (2); detail fetched for listed channels; short page ends list (2); HTML body; no
    trim (3); no refetch on resubmit; box never resets.
  - **Wrong builds, green (findings):** `useChannelSocket.ts:202` left as `invalidateQueries` — all 17 pass
    (finding 4). Box shows `q` on every route — passes (minor 6). `loadOlder` with default `cancelRefetch` — passes
    (minor 7).

## Coverage

| Plan test / expectation | Test as written | Outcome |
|---|---|---|
| 7 `nextJumpStep` tests | jump.test.ts, 7, literals not imports | present, both sides of the cap, precedence |
| `loadedPageCount`; `refetchHistory` held and idle | useMessages.test.ts, 3 | present (split into two, reported) |
| join ack keeps a page | useChannelSocket.test.tsx, 1 | present for `:134` only — finding 4 |
| 16 jump tests | MessageList.jump.test.tsx | present; 2 unpassable, 1 flaky — findings 1–3 |
| R8 scroll-to-top | MessageList.test.tsx | present, sound (growth + `scrollTop` 0 + older asked after) |
| jump into another channel | ChannelView.test.tsx | present |
| SearchBox ×6 | SearchBox.test.tsx, 7 | present |
| SearchPage ×15 | SearchPage.test.tsx, 15 | present |
| `/search` route | App.test.tsx | present |
| the journey | search.feature + steps + page object | present, binds |
| plan-reviewer note A | open-channel test resets geometry | done — but see finding 2 |

## Findings

### 1. `does not pull to the bottom when a message arrives mid-jump` cannot pass against a correct build — critical
**Where:** `MessageList.jump.test.tsx:352-372` · **Checked:** sketch, `expected 1900 to be 700` at line 366; 16/16 once
`layoutEveryElement(VIEWPORT)` is added at the top.
`loadOlder` (plan decisions 26–27) sets `heightBeforePrepend = scrollHeight` when the jump fetches page 2 — jsdom's 0,
because the layout is stubbed only afterwards. The test then gives the list 1200px and upserts a message; the layout
effect reads that as a prepend and adds 1200 to `scrollTop` (700 → 1900). Any build to the plan fails the first
assertion. Fix: stub the layout for the whole test (`layoutEveryElement(VIEWPORT)`, as `pages back…` does) so the
height is the same before and after, then set `scrollTop` 700.

### 2. `holds reads off when a jump starts on the open channel…` ends on a read no build can send — critical
**Where:** `MessageList.jump.test.tsx:408-437`, mid-jump `upsertMessage(m(26))` · **Checked:** sketch, third `mark_read`
is `…19` where `…1a` is expected; a `console.log` showed `messages.length` 5 (26 missing) at the final request.
`fetchNextPage` builds its result from the pages at the *start* of the fetch, so an upsert made while page 2 is held
is overwritten when it lands. `reapplyAfterFetch` in `useChannelSocket` exists for exactly this; the test calls
`upsertMessage` directly and skips it. So `message 26` is gone before the +2000 read and `[24, 25, 26]` cannot hold.
Fix: upsert 26 again once the highlight starts (the sketch does, and 16/16 pass), or assert on what survives. The mid-jump
"no read, no pull" halves are sound.

### 3. `jumps to a message already loaded…` is racy — major
**Where:** `MessageList.jump.test.tsx:199-211` · **Checked:** sketch, `expected '?message=…' to be ''` at line 210 in 3 of 4
whole-directory runs (not alone).
The test waits for the spy, then reads `location().search` at once. The param is removed in the same effect, but
react-router commits that navigation in a transition, one render later. A correct build fails whenever load puts the
spy ahead of the location. Fix: `await vi.waitFor(() => expect(location().search).toBe(''))`.

### 4. The open-channel join path of the R8 fix is untested — major
**Where:** `useChannelSocket.test.tsx`, `keeps a page fetched while the join is acknowledged` · **Checked:** sketch with
`:202` reverted to `invalidateQueries`: 17/17 green.
The plan (Task 5, file map) routes both join-ack invalidations (`:134`, reconnect; `:202`, the channel opened while
connected) through `refetchHistory`. The test fires `serverConnect()`, so only `:134` runs. A build that fixes one site
loses the page on the other — the common one, every channel open on a live socket. Add a twin with the socket already
connected at mount (`socket.connected` true), page 2 held, ack, release.

### 5. The report overstates what the `refetchHistory` tests pin — minor
The report is otherwise accurate (counts, reds, 7 type errors, bound steps). `useMessages.test` passes
`{ cancelRefetch: false }` itself, so it pins `refetchHistory`, not the product's own `fetchNextPage` calls (see 7).

### 6. `shows the query on /search and nothing elsewhere` — minor
`/c/channel-general` carries no `q`, so a box that shows `q` on every route passes. The reset is pinned (a box that never
resets fails); the route rule is not. Navigate to `/c/channel-general?q=zeppelin`, or accept.

### 7. `cancelRefetch: false` on the product's page fetches is not pinned — minor
With `loadOlder`'s idle guard (decision 27), default `cancelRefetch` behaves the same, so every test passes. The guard is
what the tests prove. A note for the code-reviewer.

## Left for later stages

- Findings 5–7 (minor).
- From plan-reviewer-2, still the code pair's: B (Task 9 sweep matches `docs/issues/002.md` and an accepted ADR), C (the
  jump's in-flight ref when `loadOlder` declines). The sketch used no in-flight ref and passed, so C is for reading.
- The BDD journey is unrun by design; `search()`'s retry loop and the `highlighted` check are read, not exercised.
  First e2e run in Task 10.

## Checked and sound

- Red for the right reason: every non-import red is the behaviour missing (spy never called, cursor lists short, status
  absent, `is not a function`); the three load failures are whole-file by necessity.
- No production code, config or docs written; the changed files are the report's, plus `test/layout.ts`'s helper, which the
  plan names. No existing assertion weakened (57 existing tests pass).
- `jump.test.ts` uses literals, not imported constants; both sides of the cap, `found` beats the cap, `wait` beats `found`,
  `failed` beats both.
- Fake-clock tests fake only `setTimeout`/`clearTimeout`, flush with a bounded loop, and anchor negatives to a positive.
- Timing 1's named wrong build (looks while fetching, default cancel) fails; Timing 2's exact cursor sequence is met by a
  correct build; both abandon tests and latest-wins fail their wrong builds.
- SearchPage and SearchBox: order, plain text, edited-only-one, detail once, 404, listed-channel no fetch, short-page
  Load more, 503 + Retry, cached return, focus/reconnect with positive half, workspace switch (token read), blank `q`,
  link target — each fails the wrong build I tried.
- BDD: `@bdd` on the Feature line only; reused steps verbatim; no selector in a step; the last `Then`s read the page; the
  retry is inside the `When`.
