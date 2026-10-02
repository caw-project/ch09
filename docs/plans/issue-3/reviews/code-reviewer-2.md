# Code review — issue 3, round 2: approved

**Verdict: approved.** All three findings from round 1 are fixed:
- The `thread_summary_changed` handler now re-applies after a fetch in flight, and the test pair's
  two new tests pin it.
- Doc 02 §3.1.6 and §3.1.7 now state the reply exclusions.
- The committed test report shows all four layers at this revision.

Every SPA check passes again. Both mutants of the fix were caught, and no critical or major
finding is open.

This was a rework pass, so the scope was limited:
- the changed files: `useChannelSocket.ts`, docs 02 and 06, and the test report;
- the new tests;
- the Review responses.

No Python changed since round 1, so the Python checks and the backend reading from round 1 still
hold.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Summary lost during a history refetch (major) | Fixed: `applyAndReapply` over the history key and the root's thread key; doc 06 §5.2 records it | **resolved**. The handler at `useChannelSocket.ts` is wrapped as the send-back asked. The callback is `applyThreadSummary`, which writes both caches, so a re-apply on either key restores both. Doc 06 §5.2's routing bullet says it. |
| 2. Doc 02 §3.1.6 / §3.1.7 missing reply exclusions (major) | Fixed | **resolved**. §3.1.6 says replies are dropped at hydration (`thread_root_id IS NULL`). §3.1.7 says a reply is the same 404 for `mark_read`, and that replies never count as unread. Both match `search._hydrate`, `channels._with_read_state` and `read_state.mark_read`, as I read them in round 1. |
| 3. Test report has no integration layer (major) | Fixed: `scripts/test.sh lint unit integration`, then `e2e` | **resolved**. Details are under *What ran*. |
| Minors: OpenAPI escaping, duplicate history entry, `heightBeforePrepend` after a failed fetch, post-commit summary read | Left for a later stage | **let go**. They are carried under *Left for the human*. |

## What ran

**Checks**

| Check | Result |
|---|---|
| `npm --prefix src/frontend test` | **318 passed** (318). That is 316 plus the two new tests. |
| `npm --prefix src/frontend run typecheck` | clean |
| `npm --prefix src/frontend run lint` | clean |
| `npm --prefix src/frontend run build` | built (376.69 kB JS) |

**Evidence from `scripts/test.sh`**
- `docs/test-report.md` is at revision `950e66a2d292-dirty`, and HEAD is `950e66a2d292`. Every
  layer passed:
  - Lint passed.
  - Unit: 648. That is 330 Python plus 318 Vitest, which matches the new Vitest count.
  - Integration: 420.
  - End-to-end: 21 of 21.
- The *Threads* journey "Grace sees Ada's reply in a thread without reloading" is ✅ in the report,
  and `build/test-results/e2e.xml` names it.

**Mutants**

These were run in the sketch copy, one at a time.

| File | Change | Tests run | Outcome |
|---|---|---|---|
| `useChannelSocket.ts` | `thread_summary_changed` re-applies over the thread key only (history key dropped) | `useChannelSocket.threads.test.tsx` | caught: `a summary arriving during a history refetch survives it` |
| `useChannelSocket.ts` | re-applies over the history key only (thread key dropped) | same | caught: `a summary arriving during a thread refetch survives it on the panel's root` |

`sketch.sh clean` was run, and `build/sketch` is gone.

## Findings

None open.

## Unpinned

Unchanged from round 1. These are present in the code and held only by reading:
- the `!isFetchingNextPage` load-older guard;
- `key={threadId}` on `ThreadPanel`;
- the 5 s reply ack timeout, which is shared with the channel send and pinned there;
- `deleted_now` gating the reply-summary broadcast;
- the socket `mark_read` of a reply returning before the upsert.

Round 1 gives the reasoning for each.

## Left for the human

- **Minor: OpenAPI escaping.** Run `uv run python -m messaging.openapi >
  src/frontend/openapi/messaging.json`. The content is already equal to the generator's output.
  Only two escaped characters differ.
- **Minor: opening the thread that is already open pushes a second history entry**, so the first
  Back appears to do nothing. Guard it in `useThreadParam` when `thread` already equals `rootId`.
- **Minor: a failed `fetchNextPage` leaves `heightBeforePrepend` set** in `ThreadPanel`. The next
  live reply is then treated as a prepend. Clear the ref when the fetch errors.
- **Minor: the REST reply's summary is read after the commit** (plan decision 9). If that read
  fails, the request answers 500 for a reply that is stored, and a retry would duplicate it.
- **Minor: *Found while building* item 8** still says nothing ran. Everything has run now, except
  the first real run.
- **The first real run** on Compose:
  - the issue's *Acceptance* list, in two browsers;
  - `EXPLAIN` of the summary query showing `ix_messages_thread`.
- **If `feature/issue-2` merges first:** keep `?message=` and `?thread=` together.
- **Read the assumed decisions 21–25** in the plan.
- **The writer's optional item:** make `thread=` a required keyword in `_as_message`.
- **Pre-existing and outside this branch:** the semgrep XXE note on `testkit/report.py`.

## Checked and sound

- The fix sits in the same `applyAndReapply` helper that message and reaction events use. There is
  no new idiom and no extra listener, so the socket effect's cleanup is unaffected.
- Doc 06 §5.2 and doc 02 §3.1.6 and §3.1.7 state what the code does.
- The two new tests were gated by test-reviewer-4 (approved). Each of them catches its own mutant.
- No file outside the plan's file map changed since round 1.
