# Red tests — issue 2, round 1

BDD outside-in, as the plan recommends: one journey (`search.feature`, parses and binds), and everything under it
in Vitest. 52 new Vitest tests: 23 fail by running against missing behaviour or a missing export, 29 sit in three
files that fail to load because every test in them needs a module that doesn't exist yet (`./jump`, `./SearchBox`,
`./SearchPage`). Every existing test in the files I changed still passes. Nothing passes unexpectedly.

## Baseline
Before any change, the five existing files I extend (`useMessages.test.ts`, `useChannelSocket.test.tsx`,
`MessageList.test.tsx`, `ChannelView.test.tsx`, `App.test.tsx`): **57 passed**. After: the same 57 pass and the
new tests added to them fail (useMessages 3, useChannelSocket 1, MessageList 1, ChannelView 1, App 1 = 7).
`MessageList.jump.test.tsx` adds 16 failing; `jump.test.ts` (7), `SearchBox.test.tsx` (7), `SearchPage.test.tsx` (15)
fail to load. Combined run of all nine files: 57 passed, 23 failed, 3 files not loaded. Also changed:
`test/layout.ts` (`stubScrollIntoView`, new shared helper).

## Tests
`Obs.` = first line observed. All Vitest unless marked.

| File · test | Plan task | Proves | Observed red | Match |
|---|---|---|---|---|
| `jump.test.ts` · 7 tests (fetches under the cap · gives up at ten · found on the tenth · waits beats found · failed first · exhausted · tombstone) | 1 | `nextJumpStep` precedence, cap inclusive (9 → fetch, 10 → give-up), found beats cap | `Failed to resolve import "./jump"` (whole file; every test needs it) | yes |
| `useMessages.test.ts` · `counts loaded pages, and none for an uncached key` | 1 | `loadedPageCount` 3 / 0 | `TypeError: loadedPageCount is not a function` | yes |
| · `waits for a page fetch, keeps its page, then refetches` | 1 | no `null` request while page 2 is held; after release 2 pages kept, refetch asks `null, p2` | `TypeError: refetchHistory is not a function` | yes |
| · `invalidates at once when no page fetch is in flight` | 1 | unobserved → `isInvalidated`, nothing requested; observed → exactly one more refetch | `TypeError: refetchHistory is not a function` | yes |
| `useChannelSocket.test.tsx` · `keeps a page fetched while the join is acknowledged` | 1 | ack during a page fetch keeps the page, then refetches | `expected [ null, 'p2', null ] to deeply equal [ null, 'p2', null, 'p2' ]` | **differs, same cause**: today's `invalidateQueries` cancels the page fetch and refetches page 1 alone (the plan's `expected 1 to be 2` is the next line; I assert the request sequence first, which fails earlier) |
| `MessageList.jump.test.tsx` · `jumps to a message already loaded…` | 2 | found in loaded pages: scrollIntoView once `{block:'center'}` on that article, `data-highlighted`, param removed | `expected "vi.fn()" to be called 1 times, but got 0 times` | yes |
| · `pages back until it finds the message` | 2 | fresh list opens at newest (`scrollTop` 1200) while seeking; cursors `null,p2,p3`; found | `expected [ null ] to deeply equal [ null, 'p2' ]` (the `scrollTop` half passes at red, as the plan says) | yes |
| · `counts pages cached before the jump towards the ten` | 2 | 4 cached + 6 fetched = 10; no `p11`; notice | `Unable to find role="status"` (DOM shows pages up to message 17: the mount refetch only) | yes |
| · `stops at ten loaded pages with the notice` | 2 | no `p11`; notice; give-up scrolls to newest from `scrollTop` 300; param removed; no highlight | `expected [ null ] to deeply equal [ …10 ]`-style cursor wait (`toHaveLength(10)` at red: 1) | yes (fails earlier than the plan's "no status": nothing pages) |
| · `ends on a failed fetch with the list's own error` | 2 | page 2 → 503: param removed, `role="alert"`, no notice, no scroll | `expected '?message=0199…' to be ''` | yes |
| · `highlights a tombstone` | 2 | tombstone on page 2 highlighted | `received value must be an HTMLElement … Null` (page 2 never requested) | differs in wording only |
| · `fades the highlight after two seconds` | 2 | fake `setTimeout`/`clearTimeout`; highlight at +0, +1999; gone at +2000 | `expected [] to deeply equal [ '0199…17' ]` | yes |
| · `holds reads and the badge off during the jump, then reads once it ends` | 2 | nothing read, `readingChannelId` null while highlighted (+1999); read of newest after +2000 | `expected [ '0199…18' ] to deeply equal []` | yes |
| · `does not pull to the bottom when a message arrives mid-jump` | 2 | `scrollTop` stays 700 | `expected 1200 to be 700` | yes |
| · `waits for a refetch already in flight, then pages back (Timing 1)` | 2 | cached page 1, mount refetch held: no `p2` while held; after, `null,p2,p3`, found | `expected [ null ] to deeply equal [ null, 'p2', 'p3' ]` | yes |
| · `holds reads off when a jump starts on the open channel, after flushing a held read` | 2 | held read flushed at once; no read/no pull during; one read +2000 | `expected [ '0199…18' ] to deeply equal [ …18, …19 ]` | yes (1 where 2 expected) |
| · `keeps a page fetched across a reconnect, then looks again (Timing 2)` | 2 | `null,p2,p3,null,p2,p3,p4` and found | `expected [ null ] to deeply equal [ null, 'p2', 'p3' ]` (waiting for the held `p3`) | yes |
| · `abandons the jump when the list unmounts` | 2 | `p2` lands in the cache, no `p3`, no scroll, no notice | `expected [ null ] to deeply equal [ null, 'p2' ]` | yes |
| · `abandons the jump when the param is removed by navigation` | 2 | same, after navigating to `/c/…` without the param | same | yes |
| · `follows only the latest target` | 2 | A seeking, navigate to B (page 2): scroll only to B, no `p3` | same | yes |
| · `shows the divider and the highlight together` | 2 | `lastReadId` on page 2, target on page 3 | `received value must be an HTMLElement … Null` | differs in wording only |
| `MessageList.test.tsx` · `lets a refetch finish when the top is reached during it, then loads the older page` | 2 | no `older` while the refetch is held; `scrollTop` 0 after it lands (stale anchor would give 100); `older` then asked | `expected [ null, null, 'older' ] to deeply equal [ null, null ]` | yes |
| `ChannelView.test.tsx` · `starts a jump into another channel once its history arrives` | 2 | "Loading…" and no scroll while detail is held; after, highlighted in `#random` | `expected "vi.fn()" to be called 1 times, but got 0 times` | yes |
| `SearchBox.test.tsx` · 7 tests (submit ×2 routes, blank, 200 cap, route text, resubmit, landmark) | 3 | see plan | `Failed to resolve import "./SearchBox"` (whole file) | yes |
| `SearchPage.test.tsx` · 15 tests | 3 | see plan | `Failed to resolve import "./SearchPage"` (whole file) | yes |
| `App.test.tsx` · `shows search results on /search for a signed-in user` | 3 | `/search` is a protected route inside the shell | `Unable to find an element with the text: the zeppelin lands` — DOM is "No such page." | yes |
| BDD · `Ada finds a message and opens it in its channel` | 4 | the journey | collects, binds; first e2e run stops at `search()` waiting for `search-box` | yes |

## Types
`npm --prefix src/frontend run typecheck`: 7 errors, all missing modules/exports:
`jump.test.ts` → `./jump`; `MessageList.jump.test.tsx` → `refetchHistory` from `./useMessages`;
`useMessages.test.ts` → `loadedPageCount`, `refetchHistory`; `SearchBox.test.tsx` → `./SearchBox`, `./SearchPage`;
`SearchPage.test.tsx` → `./SearchPage`. Nothing else.

## BDD
`uv run pytest tests/bdd --collect-only -q` → 21 tests collected, including
`test_search_steps.py::test_ada_finds_a_message_and_opens_it_in_its_channel`.
`uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` prints no stub: every step binds
(`Given Ada is signed in`, `has created…`, `has sent…`, `is looking at…` reused from `steps/conftest.py`; four new
phrases in `test_search_steps.py`). Expected red at the first e2e run: `search()` times out on
`get_by_test_id("search-box")`. Page-object testids used: `search-box`, `search-result`, `search-empty`,
`message-item` + `data-highlighted`.

## Departures from the plan
- **`search()` loop** uses `time.monotonic()` for its 10 s budget and `results.or_(empty)` to wait for either
  outcome; no `Then` acts.
- **`jump` red messages**: several arrangement waits (`p2` requested) fail before the assertion the plan names —
  same cause, noted in the table. The `Timing 1` "none while held" half passes at red, as the plan says.
- **`refetchHistory` test split** into a held-page test and an idle test whose two halves cover the unobserved
  (marked, nothing requested) and observed (one refetch) cases.
- **The SearchBox resubmit test** types `{Enter}` into a box already holding `x` rather than retyping.
- **`stubScrollIntoView()`** returns a plain `vi.fn()` mock; the element it was called on is `spy.mock.contexts[i]`.
- No test dropped, none moved layer.

## Picked up from earlier reviews (plan-reviewer-2, *Left for later stages*)
- **A (open-channel no-pull half):** done — the test resets `giveLayout` (`scrollTop` 700, not frozen) after the
  navigation and before the mid-jump upsert, so a pull writes 1200 and is detectable.
- B, C: code-writer's.

## For the code-writer
- Tests drive the jump only through `MessageList`; `useMessageJump`/`jump.ts` internals are yours, but `nextJumpStep`,
  `loadedPageCount`, `refetchHistory`, `searchKeys`-less `SearchBox`/`SearchPage` props follow the plan exactly.
- **Fake-clock tests** (`fades…`, `holds reads and the badge…`, `holds reads off when a jump starts on the open
  channel…`) fake only `setTimeout`/`clearTimeout`, flush with a bounded `advanceTimersByTimeAsync(0)` loop, and the
  highlight must start when found lands (no clock advance before it) and last exactly 2000 ms; the read after the
  jump is asserted at +2000 with nothing at +1999.
- **Timing 2** expects exactly `[null,p2,p3,null,p2,p3,p4]`: the refetch must start before the jump looks again.
- **Open-channel jump** expects the held read sent in the commit the param arrives (no time passes), through
  `useMarkRead().flush()`.
- **`pages back…`** pins `scrollTop === scrollHeight` while seeking on a fresh list; **`stops at ten…`** away from the
  bottom, so give-up's own scroll to newest is what makes 1200.
- **SearchPage** is queried by role/text only; the row's link must contain the body text (the BDD page object
  filters `search-result` by body). Channel names render `#general`, placeholder exactly `#…`.
- The 503-for-page-2 tests layer an `msw` handler that returns `undefined` for other cursors, so a failed page is a
  `ProblemError` the list's own banner shows.

## Review responses (round 2, to test-reviewer-1)
Reran `useChannelSocket`, `MessageList.jump`, `SearchBox`: 2 + 16 fail as before, `SearchBox` fails to load (the module
is missing), typecheck still 7 missing-module errors. All of these are red, so none of the fixed tests can be shown green
here; findings 1–3 were verified green by the reviewer's sketch.
1. **Fixed.** `does not pull to the bottom…` calls `layoutEveryElement(VIEWPORT)` first, so page 2 loading is not read as
   a prepend. Red now: `expected 1200 to be 700`.
2. **Fixed.** `holds reads off when a jump starts on the open channel…` upserts message 26 again once the highlight has
   started, with a comment on why (a page fetch overwrites an upsert made while it was held; `reapplyAfterFetch` handles
   that live). The mid-jump "no read, no pull" halves are kept.
3. **Fixed.** `jumps to a message already loaded…` waits for `location().search` to be `''` with `vi.waitFor`.
4. **Fixed.** The join-ack test is one body run twice: `…acknowledged on connect` (`:134`) and `…of a channel opened on
   a live socket…` (`:202`; channel null at connect, then opened by rerender). Each fails a build that reverts its own
   call site to `invalidateQueries`. Both red: `expected [ null, 'p2', null ] to deeply equal [ null, 'p2', null, 'p2' ]`.
5. **Accepted.** `useMessages.test` pins `refetchHistory`, not the product's own page fetches.
6. **Fixed.** The `SearchBox` route test navigates to `/c/channel-general?q=zeppelin`, so a box that shows `q` on every
   route fails.
7. **Left for the code-reviewer.** `cancelRefetch: false` on the product's page fetches is covered behaviourally by
   `loadOlder`'s idle guard.

Departure: the single join-ack test is now two (split by call site), so useChannelSocket adds 2 failing tests, not 1.
