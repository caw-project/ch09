# A name for a member who joined after the directory loaded — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** When the SPA is asked for the name of an id its workspace directory doesn't hold, it
fetches the directory again — once, joining any fetch already in flight — and the name replaces
the short id everywhere; an id that a later fetch still lacks stays a quiet short id.

**Architecture:** `nameFor` records the ids it could not name during render; an effect after
each render hands them to a **directory tracker** — one per `QueryClient`, state per workspace —
which starts a `refetchQueries(…, { cancelRefetch: false })` only when the directory has data
and no fetch is in flight. The directory's `queryFn` is wrapped by the tracker, so it knows when
each fetch started, whether the tracker started it, and settles every waiting id when it lands:
named, departed, or owed one more fetch. The hook also reads `fetchStatus`, so every consumer
re-renders when a fetch settles and reports what it still can't name. `useChannelSocket`'s
`onConnect` invalidates the directory with `cancelRefetch: false`, beside the channel list.

**Tech Stack:** React 19, TypeScript, TanStack Query 5.101.4, Vitest + MSW + Testing Library.
No Python, no service, no chart.

**Issue:** `docs/plans/issue-7/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-7`, branch `feature/issue-7`, from `main` at `dca6fbb`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Where | SPA only: no server event, no new route, no change to Auth or Messaging |
| 2 | While the refetch is in flight | The short id, as today — no placeholder |
| 3 | How often a departed id refetches | At most once per fetch of the directory |
| 4 | Renames | Out of scope |
| 5 | The register | No 🔴 entry; no new entry and no ADR — a fix inside D24's existing split |
| 6 | First load | Unknown ids start nothing while it runs; still unknown when it lands, they start **one** refetch, and are departed if that lands without them (Paths row 1) |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 7 | What a fetch for another reason does to a departed id still missing from it — **assumed** | It clears the departed set (R3), and an id cleared that way earns **one** more refetch of its own; that one lands without it and departs it again | Reading Timing t5's "alan unknown again after it" as "unknown, so asks again". The other reading — R3's own definition applied to the clearing fetch, which started after Alan was first seen, re-departs him on the spot with no extra request — is just as defensible. Cost of this reading: one extra `GET …/members` per fetch for another reason (≤ one per 5 minutes, plus reconnects) while a departed author is on screen. Changing it: in `load` step 3, depart missing previously-departed ids instead of clearing them — three lines and row 7's expected count (3, not 4) |
| 8 | Where the trigger runs | `nameFor` adds an id it can't name to a `Set` created fresh in each render; a `useEffect` with no dependency array hands that set to the tracker after the commit | The issue's assumption 2: never in render. A Zustand queue drained by one effect would need a store write during render, which React warns about. Under StrictMode each render builds its own `Set` and the committed render's effect reports its own; the effect running twice reports the same ids twice, which `saw` ignores (they are already pending) |
| 9 | Where the departed set and the in-flight bookkeeping live | `directoryTracker(queryClient)`: a `WeakMap<QueryClient, …>`, state per workspace id | It describes the cache's own fetches, so it lives and dies with the `QueryClient` — a test's fresh client gets a fresh tracker. Not Zustand: D24 keeps server-derived state out of the store, and a store would outlive a client |
| 10 | Which TanStack call | `refetchQueries({ queryKey, exact: true }, { cancelRefetch: false })`, called **only** when the query has data and `fetchStatus === 'idle'`; the reconnect uses `invalidateQueries(…, { cancelRefetch: false })` | Checked in the installed source: `queryClient.ts:313-320` defaults `cancelRefetch` to `true`, and `query.ts:404-419` then **cancels** an in-flight fetch whenever the query has data and starts a new one — two requests, breaking R2 and *R1 and R5*. With `false` it returns the in-flight promise (`query.ts:414-418`). See *Corrections* |
| 11 | How "started after the id was first seen" is measured | A logical clock per tracker (an integer that increments). `seenAt` is stamped when the effect reports an id; `startedAt` when the wrapped `queryFn` is invoked | Wall-clock time can tie within a millisecond in tests. The `queryFn` runs synchronously inside `refetchQueries`: `query.ts:528-566` dispatches `fetch` and calls `retryer.start()`, which calls `config.fn()` at once when it can start (`retryer.ts:219-222`, `:156`) |
| 12 | How the tracker tells its own fetch from one "for another reason" | It sets `ownStarting = true` around its `refetchQueries` call; the wrapped `queryFn` reads and clears it at entry | Same synchronous path as 11. Offline (`canStart` false) the fetch starts later and counts as "another reason" — it clears the departed set, which a fetch on coming back online should do anyway |
| 13 | Re-rendering when a fetch lands with nothing new | The hook reads `fetchStatus` as well as `data` | TanStack re-renders an observer only for the result fields it read (`queryObserver.ts:666-700`), and structural sharing hands back the **same** `data` reference when the response is equal (`utils.ts:402-418`). A refetch that lands without the newcomer is exactly that case: reading only `data`, no consumer re-renders, no effect runs, and R2's follow-up never starts. Reading `fetchStatus` re-renders each consumer at a fetch's start and end — cheap, and the tests pin it (Task 1's fixtures land *equal* data) |
| 14 | No data yet — **assumed** | Before the directory's first successful load (still loading, or failed), the tracker records ids but never starts a fetch; TanStack's own load and refetch-on-mount do | A refetch with no data is what TanStack already does, and an unknown-id trigger there would fire after every render of a failed first load. Changing it is one condition in `saw` and one test |
| 15 | A refetch that fails — **assumed** | The ids it was started for go quiet, exactly as if it had landed without them (departed, until a fetch for another reason). Ids first seen *during* it keep their one follow-up | The issue says nothing. Retrying on the next render would loop on a persistent 5xx — every failure re-renders. Cost of changing: one branch in the tracker's `catch`, one test |
| 16 | Every connect, including the first — **assumed** | `onConnect` invalidates the directory on every connect, as it already does the channel list (`useChannelSocket.ts:143`) | R5 says "as it refetches the channel list", and the nearest code does every connect. Cost: at most one extra `GET …/members` at start-up, when the directory loaded before the socket connected; with `cancelRefetch: false` a connect during the first load joins it. Skipping the first connect is a ref and one test |
| 17 | A TanStack retry attempt — **assumed** | Each attempt invokes the `queryFn` again; a retry of the tracker's own refetch is counted as "another reason" and clears the departed set | Production retries once, on a 5xx only (`main.tsx:21-24`). The cost is one extra refetch for a departed id after a server error. Threading attempt identity through costs more than it saves |
| 18 | `nameFor` called outside render — **assumed** | Not tracked: its id is added to a set whose effect has already run | Checked: every `nameFor` call today is in a render or a `useMemo` (`MessageList.tsx:329`, `ThreadPanel.tsx:123`, `DirectMessageList.tsx:47,105`, `MemberPanel.tsx:41`, `MessageComposer.tsx:157`, `ChannelView.tsx:82,121`, `SearchPage.tsx:34,75`, `useChannelNames.ts:31,46`). A handler that needs it later gets a name from the next render |
| 19 | Where doc 06 records it | A **"Names — added 2026-10-15"** paragraph in §5.2, after *Typing* (which already says names resolve through the directory) | §5.2 is where every cache-freshness rule of the shell lives |
| 20 | A reconnect that lands while the tracker's own refetch is in flight | `onConnect` calls `directoryTracker(queryClient).otherReason(workspaceId)` before its `invalidateQueries`. That marks the workspace so the fetch that lands next clears the departed set even if the tracker started it | With `cancelRefetch: false` the reconnect **joins** the in-flight fetch (`query.ts:414-418`) and no new `queryFn` call happens, so `own` stays true and, without the mark, R3's "a reconnect … clears the departed set" would silently not happen — exactly when recovered history may bring a departed author back. The alternative, accepting it, costs up to 5 minutes of a short id; the mark is one flag and Task 2 row 2 pins it |
| 21 | A stale mount or window-focus refetch that joins the tracker's own fetch — **assumed** | Not detected: that fetch counts as the tracker's own, and the departed set survives it | Both join rather than start (`queryObserver.ts:99-100` → `#executeFetch()` with no `cancelRefetch`; `query.ts:336,345` pass `cancelRefetch: false`), so the tracker can't see them without listening to the `QueryCache`. The window is a single request's duration; the cost is a departed id staying short until the next fetch for another reason (≤ 5 minutes, or a reconnect). Changing it: subscribe the tracker to the query's observer events — a larger change than the case is worth |

Nothing here touches a 🔴 entry. **D28** (no user-preferences feature) is the nearest, and it is
untouched: a display name is a profile field, not a per-user choice, and nothing here stores
one. **D16** (tombstone retention) is unrelated — a departed author's messages are rendered as
before.

## Corrections to the issue

1. **"`refetchQueries` or `invalidateQueries` while a fetch is in flight joins it" is not true by
   default in the installed 5.101.4.** Both default `cancelRefetch` to `true`
   (`node_modules/@tanstack/query-core/src/queryClient.ts:319`), and `Query.fetch` cancels the
   in-flight fetch and starts another whenever the query already has data
   (`query.ts:411-413`); it joins only with no data yet, or with `cancelRefetch: false`
   (`:414-418`). `useChannelSocket.ts:243-248` already relies on the cancelling behaviour for the
   channel list. This plan passes `cancelRefetch: false` on both of its calls (decision 10), and
   Task 2's tests fail a build that doesn't. Task 5 records it in doc 06.
2. **The issue's consumer list counts `useChannelNames` under `SearchPage`.** It is a helper that
   receives `nameFor` (`useChannelNames.ts:25`), not an eighth caller of the hook — no change. Its
   calls are plain render code (`useChannelNames.ts:30-48`, no `useMemo`), so they are recorded
   like the rest (decision 18).

## Test approach — recommendation to the test pair

**TDD.** This is a rule about when a cache refetches, inside one hook and one socket handler — no
new journey, and the issue rules one out: Dex's users are fixed and Auth's tables aren't
truncated, so the suite can't make a first-time joiner cheaply. The acceptance run is the proof
of the whole.

| Behaviour | Layer | File |
|---|---|---|
| R1–R4, R6, *R1 and staleness*, *R3 and a rejoin*, *R1 and a switch*; Paths rows 1–4, 6 | Vitest | `features/channels/useWorkspaceMembers.test.tsx` |
| A newcomer's message shows their name without a reload (Paths row 2, through a real consumer) | Vitest | `features/channels/MessageList.test.tsx` |
| R5, and *R1 and R5* in both orders (Paths row 5) | Vitest | `lib/realtime/useChannelSocket.test.tsx` |

**What no test here covers:**
- **A second tab** (Paths row 7) — each tab has its own `QueryClient` and tracker, so it is the same
  rules run twice; no test can add anything a one-tab test doesn't.
- **A member who joins mid-way through `workspaceMembers`' page loop** — the issue's third
  assumption; the R2 follow-up covers it, and that follow-up is tested.
- **The acceptance run's three checks** on the preview (issue, *Acceptance*) — the
  acceptance-reviewer's, not a test layer.

**Baseline**, from `docs/test-report.md` at revision `560114e3b455-dirty`: Unit 938 passed, of which
`frontend` 488 passed (Vitest); End-to-end 24 passed; Integration not run. The report's revision
predates `dca6fbb`, which added only issue files. Expected counts below are "N or more", because a
sibling branch may land first.

## Global constraints

- **TanStack Query owns the directory (D24).** No copy of members or names in Zustand; the
  tracker's sets hold ids and fetch bookkeeping only.
- **Query keys carry the workspace** (`directoryKeys.members(workspaceId)`, D24). The tracker
  reads the workspace from the key it was handed, never from a closure that a switch could
  outlive.
- No API change, so no OpenAPI regeneration; no env var; no chart or Ingress change (no route).
- Vitest queries by role, label or text — no `data-testid` (CLAUDE.md, Testing).
- The lint hook blocks on ESLint findings, including `react-hooks`; decision 8's effect has **no**
  dependency array on purpose — a comment says so.

## File map

Paths under `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `test/api.ts` | modify | `auth.membersBy`: a directory stub that answers per call and per workspace, and can hold a response | 1 |
| `test/directory.ts` | create | `settleDirectory`: idle, and still idle a macrotask later | 1 |
| `features/channels/useWorkspaceMembers.test.tsx` | create | the rules, through the hook | 1 |
| `features/channels/MessageList.test.tsx` | modify | one consumer test | 2 |
| `lib/realtime/useChannelSocket.test.tsx` | modify | R5, and R5 meeting R1 | 2 |
| `features/channels/directoryRefresh.ts` | create | `directoryTracker`: pending, departed, own-fetch flag, other-reason mark, the clock | 3 |
| `features/channels/useWorkspaceMembers.ts` | modify | records unknown ids, the effect, the wrapped `queryFn`, reads `fetchStatus`; header comment | 3 |
| `lib/realtime/useChannelSocket.ts` | modify | `onConnect` marks `otherReason` and invalidates `directoryKeys.members(workspaceId)`; its header's *Read state* paragraph | 4 |
| `docs/design/06-frontend-spa.md` | modify | §5.2 *Names* paragraph; §5.2 DM *Naming* bullet's "`shortId` when unknown" | 5 |

**Deliberately unchanged, checked:**
- The seven consumers — they call `nameFor` in render already; nothing in them changes.
- `lib/auth/api.ts` — `workspaceMembers` already reads every page.
- `main.tsx` — no `QueryClient` default changes; the calls pass their own `cancelRefetch`.
- **Existing Vitest tests that render a consumer.** Sweep: 15 files stub `auth.members`. Where a
  rendered author is not in the stub (`aMessage()` gives a random `authorId`), the new code
  makes **one more** `GET …/members` after the first load. No assertion counts all requests
  where a consumer is mounted: the exact-count ones (`xhrPut.test.ts:33`,
  `uploads.test.ts:187,205,244`, `useMarkRead.test.ts:124`, `CreateChannelDialog.test.tsx:61`,
  `ChannelHeader.test.tsx:51`, `useThread.test.ts:92,150`) render no directory consumer or
  filter by path. Tests with **no** members stub fail their first load and, by decision 14, start
  nothing more. If one does break, it is this ripple: fix the test's stub, record it in *Found
  while building*.
- No `tests/bdd` change: no journey added. The DM and messages journeys show names through the
  changed hook, so the e2e layer runs in Task 6.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–2 | test-writer | failing Vitest tests, each failing for the reason given — **test-reviewer gate** |
| GREEN | 3–4 | code-writer | Tasks 1–2 pass; `typecheck` clean |
| Finish | 5–6 | code-writer | the record, then verification |

One red phase: no generated types change, so Task 1's stubs compile against today's
`WorkspaceMember`.

---

## Task 1: The rules, through the hook (RED)

**Files:** `test/api.ts` (modify), `features/channels/useWorkspaceMembers.test.tsx` (create)

**Interfaces — test support, in `test/api.ts`:**

```ts
// In `auth`, beside `members`. `call` counts from 1, per workspace, per test.
// The reply may return a promise: that is how a test holds a fetch in flight.
membersBy(
  reply: (workspaceId: string, call: number) => WorkspaceMember[] | Promise<WorkspaceMember[]>,
): void
```

It records the request first (as `authJson` does), then awaits the reply and answers
`{ items, nextCursor: null }`. Reset the per-workspace call counts when it is called, not in
`setup.ts`. A test's `reply` answers every call past the last one it names with that last list,
so a request a wrong build makes, or an anchor, always gets an answer. A failure is still
`auth.problem('get', '/api/v1/workspaces/:workspaceId/members', …)`.

**Interfaces — test support, in a new `test/directory.ts`:**

```ts
/** Resolves once the directory for `workspaceId` is idle and stays idle across a macrotask.
 *  TanStack notifies observers on setTimeout(0) (`notifyManager.ts:15`, `systemSetTimeoutZero`),
 *  and the re-render that follows may start the next fetch from its effect — so one idle
 *  reading is not enough. A build that refetches forever never settles: the wait times out. */
export async function settleDirectory(queryClient: QueryClient, workspaceId: string): Promise<void>
```

Built as a `vi.waitFor` whose callback does, twice: `await act(() => new Promise((r) => setTimeout(r, 0)))`,
then `expect(queryClient.isFetching({ queryKey: directoryKeys.members(workspaceId) })).toBe(0)`.

**Interfaces — what the tests drive** (all existing, unchanged in shape):
`useWorkspaceMembers(accessToken, workspaceId): Directory`, `directoryKeys.members(workspaceId)`,
`shortId(userId)`.

**How each test is built:**
- `renderHookWithProviders(() => { const d = useWorkspaceMembers('token', ws); return asking.map(d.nameFor) }, { queryClient })`,
  where `asking` is a mutable array the test changes before `rerender()`. Two consumers in one
  render are one render callback calling the hook twice, each with its own list. A consumer
  that **mounts later** is a second `renderHookWithProviders` with the same `queryClient` —
  never one more hook call in the first callback, which breaks the rules of hooks.
- `memberRequests(ws)` = `requests().filter((r) => r.url.pathname === `/api/v1/workspaces/${ws}/members`)`.
  Requests are recorded on arrival, so a held fetch counts at once.
- A deferred per held response (`let release!: (m: WorkspaceMember[]) => void`), released inside
  `await act(async () => { … })`.
- **Negatives are settled, then anchored — `quiet(id)`.** "This id starts no request" is one
  procedure, written once as a local helper, and the rows below say `quiet(Alan)` for it:
  1. `await settleDirectory(queryClient, ws)`; `before = memberRequests(ws).length`.
  2. Ask the quiet id — the row says how (a `rerender()`, several, or a later-mounted consumer).
  3. `await settleDirectory(queryClient, ws)` — a fetch a wrong build started for the quiet id
     starts *here*, synchronously in the effect, and lands here, **before** any anchor exists to
     join it. A build that refetches on every render never settles, and the wait fails.
  4. Ask a brand-new anchor id (`'0199c0de-…'`); wait until `memberRequests(ws).length > before`;
     `settleDirectory` again.
  5. `expect(memberRequests(ws)).toHaveLength(before + 1)` and the quiet id still renders its short id.

  The anchor's request is the positive: the tracker can still fetch, so "nothing" is not a dead
  tracker. A build that fetched for the quiet id shows `before + 2`. The anchor departs when its
  fetch lands without it, so it starts nothing more. Each anchor uses up one call number, so a
  row's later replies count on from it.
- **Exact counts are taken settled.** Any "exactly N" below is asserted after `settleDirectory`,
  never straight after a name appears.
- **Equal data on a fetch that lands without an id.** Where a refetch lands without the newcomer,
  answer with the *same* member list as the cache holds, so structural sharing keeps the
  reference — this is what fails a hook that doesn't read `fetchStatus` (decision 13).
- Ids are UUID-shaped, so `shortId` is visibly 8 characters: Ada `0199a000-…-0001`, Grace
  `01a13ec0-…`, Alan `01b2…`, Bob `01c3…`. Two workspaces, `WS_A` and `WS_B`; the workspace is a
  mutable variable the render callback reads, so a switch is "change it, `rerender()`". `WS_B`'s
  directory always answers `[bob]` unless a row says otherwise.
- No fake timers: every wait is on a request or a render.

At red, today's hook fetches once and never again, so **every test fails at its first assertion
that a second `GET` was made**: `expected 1 to be 2` (or `vi.waitFor` timing out with that
message). The column below names that assertion, and the wrong build each test also fails.

| Test | Proves | Expected red | Also fails |
|---|---|---|---|
| `shows the short id while the refetch is in flight, then the name it brings` | R1, R4, decided 2: loaded `[ada]`; ask Grace → her short id **and** a 2nd request (held); release `[ada, grace]` → `'Grace Hopper'` | `expected 1 to be 2` on the request count | a placeholder in place of the short id |
| `asks once for several unknown ids in one render, and once for an id two consumers ask for` | R2 / Paths row 3: one consumer asks Grace and Alan, a second asks Grace; #2 `[ada, grace]`; settled, exactly 2 requests; both consumers show `'Grace Hopper'`; then `quiet(Alan)` (a `rerender()`) | `expected 1 to be 2` | one refetch per id or per consumer (3 or 4 settled); Alan not departed after #2 (`quiet` sees `before + 2`) |
| `starts nothing during the first load, then one refetch for ids it lacked, and departs them if that lacks them too` | Paths row 1, decided 6: first load held; ask Grace → still 1 request; release `[ada]` → a 2nd; release it `[ada]` → `quiet(Grace)` (a `rerender()`) | `expected 1 to be 2` after the first load lands | a fetch during the first load (2 while held); a build that departs on the first load (no 2nd); one that never departs (`before + 2`) |
| `an id first seen during a refetch gets one more; an id seen before it is departed` | R2's contrast and R3 (Timing t1+5 / t2): loaded `[ada]`; ask Bob → refetch #2 held; then ask Alan; release #2 `[ada]` and, **with no `rerender()` from the test**, expect #3 (Alan); release #3 `[ada]` → `quiet(Alan)`, `quiet(Bob)`; both short | `expected 1 to be 2` | a build that departs every missing id (no #3); one that refetches for both (`before + 2`); a hook reading only `data` (#2 lands equal, so nothing re-renders and no #3 — which is why the test must not `rerender()` itself) |
| `a departed id starts no further refetch, however often it is asked` | R3, decided 3: Alan departs after #2; `quiet(Alan)`, where step 2 is three `rerender()`s **and** a later-mounted consumer asking Alan | `expected 1 to be 2` | a departed set kept per hook instance (the new consumer refetches: `before + 2`) |
| `an unknown id seen while a refetch for another reason is in flight joins it` | *R1 and staleness*: loaded; `invalidateQueries` on the key → #2 held; ask Grace → still 2; release #2 `[ada]` → #3 (seen during); release `[ada, grace]` → name; settled, exactly 3 | `expected 2 to be 3` | a default `cancelRefetch` (a 3rd request while #2 is held, 4 settled) |
| `a fetch for another reason clears the departed set, and the id earns one more refetch` | R3, decision 7, Timing t5: Alan departs (#2); `invalidateQueries` → #3 `[ada]`; then #4 for Alan, `[ada]`; then `quiet(Alan)` | `expected 1 to be 2` | departed never cleared (no #4: the wait for it fails); cleared by the tracker's own fetch too (never settles) |
| `a departed member who rejoins is named at the next fetch for another reason, not before` | *R3 and a rejoin*: Alan departs; `quiet(Alan)` with the directory now answering `[ada, alan]` — still short; `invalidateQueries` → the next call `[ada, alan]` → `'Alan Turing'` | `expected 1 to be 2` | a rejoin check on every render (`before + 2`, and named early) |
| `a refetch that fails leaves the ids it was for quiet` | decision 15: #2 answers 500 (`auth.problem`); Grace short; `quiet(Grace)` (three `rerender()`s) | `expected 1 to be 2` | a retry on each render (never settles) |
| `a refetch for one workspace lands in that workspace's cache, after a switch` | R6 / *R1 and a switch*: `WS_A` loaded; ask Grace → A's #2 held; rerender with `WS_B` (B answers `[bob]`); release A's #2 `[ada, grace]` → `getQueryData(directoryKeys.members(WS_A))` holds Grace, B's does not, and B's consumer shows Grace short | `expected 1 to be 2` (A's requests) | a tracker or key that ignores the workspace |
| `each workspace keeps its own departed set` | R6: Alan departs in `WS_A`; switch to `WS_B` (loaded `[ada]`); ask Alan → B's #2 is made | `expected 1 to be 2` (A's requests) | one departed set for all workspaces (B never asks) |

Each test gets a one-line comment saying what breaks if the rule goes, as
`useChannelSocket.test.tsx` does.

- [ ] Add `auth.membersBy` to `test/api.ts` and `settleDirectory` in `test/directory.ts`, each with
  its doc comment.
- [ ] Write the eleven tests. Run `npm --prefix src/frontend test -- src/features/channels/useWorkspaceMembers.test.tsx`;
  record each failure message in the red report.
- [ ] `npm --prefix src/frontend run typecheck` is clean (no new production symbol is imported).
- [ ] Leave uncommitted.

## Task 2: One consumer, and the reconnect (RED)

**Files:** `features/channels/MessageList.test.tsx`, `lib/realtime/useChannelSocket.test.tsx` (modify)

**Interfaces** — the reconnect contract Task 4 implements, in `useChannelSocket`'s `onConnect`:

```ts
// A fetch for another reason, even when it joins the tracker's own (decision 20).
directoryTracker(queryClient).otherReason(workspaceId)
void queryClient.invalidateQueries(
  { queryKey: directoryKeys.members(workspaceId), exact: true },
  { cancelRefetch: false }, // join a fetch in flight; never cancel and restart it (Corrections 1)
)
```

`MessageList.test.tsx` — its `renderList()` stubs `auth.members` itself and the last `server.use`
wins, so the new test renders `MessageList` directly with the same props and `auth.membersBy`.

| Test | Proves | Expected red |
|---|---|---|
| `shows a newcomer's name on their message once the directory catches up` | Paths row 2 through a real consumer: history holds one message by Grace; directory call 1 `[ada]`, call 2 `[ada, grace]`; the article shows `'Grace Hopper'` without a reload; then `settleDirectory`, and exactly 2 directory requests | `findByText('Grace Hopper')` times out: `Unable to find an element with the text: Grace Hopper` |

`useChannelSocket.test.tsx` — a new `describe('the workspace directory')`. The second and third
tests mount both hooks in one render callback:
`useChannelSocket('token', WORKSPACE, null, ADA); const d = useWorkspaceMembers('token', WORKSPACE); return asking.map(d.nameFor)`.

| Test | Proves | Expected red |
|---|---|---|
| `refetches the workspace directory on every connect` | R5: seed `directoryKeys.members(WORKSPACE)`; `isInvalidated` false → connect → true; seed again → false; drop and connect → true. Mirrors `refetches the channel list on every connect` (`:356-374`) | `expected false to be true` after the first connect |
| `a connect while a refetch for an unknown author is in flight joins it, and still clears the departed set` | *R1 and R5*, unknown first, and decision 20: loaded `[ada]`, asking Alan; #2 `[ada]` → Alan departs; settle. Ask Grace too → #3 held; `serverConnect()` → still 3; release #3 `[ada, grace]` → `'Grace Hopper'`; then #4 for Alan (the departed set was cleared by the joined fetch), `[ada, grace]`; then `quiet(Alan)` | `expected 1 to be 2` (no refetch for Alan). A build with default `cancelRefetch` shows 4 while #3 is held; one without `otherReason` makes no #4 |
| `an unknown author arriving during a reconnect's refetch joins it` | *R1 and R5*, connect first: loaded `[ada]` (ask nobody); settle; `serverConnect()` → #2 held; ask Grace → still 2; release `[ada, grace]` → name; settled, exactly 2 | `expected 1 to be 2` (the connect starts no directory fetch) |

`quiet` and `settleDirectory` are the same as Task 1's; `quiet` is local to each file.

- [ ] Write the four tests. Run both files in one command; record each failure.
- [ ] Leave uncommitted.

---

## Task 3: The tracker and the hook (GREEN)

**Files:** `features/channels/directoryRefresh.ts` (create), `features/channels/useWorkspaceMembers.ts` (modify)

**Interfaces** — `directoryRefresh.ts`:

```ts
import type { QueryClient } from '@tanstack/react-query'
import type { WorkspaceMember } from '../../lib/auth/api'

export interface DirectoryTracker {
  /** After a commit: the ids this render could not name. Starts at most one refetch. */
  saw(workspaceId: string, ids: ReadonlySet<string>): void
  /** The directory's queryFn goes through this: it times the fetch and settles its ids. */
  load(workspaceId: string, fetch: () => Promise<WorkspaceMember[]>): Promise<WorkspaceMember[]>
  /** A fetch for another reason is starting or joining one in flight: the next fetch to land
   *  for this workspace clears the departed set, whoever started it (decision 20). */
  otherReason(workspaceId: string): void
}

/** One per QueryClient (a WeakMap), so a fresh client — a test's — starts clean. */
export function directoryTracker(queryClient: QueryClient): DirectoryTracker
```

State per workspace: `pending: Map<userId, seenAt>`, `departed: Set<userId>`,
`ownStarting: boolean`, `otherMarked: boolean`; one `clock` per tracker.

**`otherReason(ws)`**: `otherMarked = true`. Nothing else — the caller's `invalidateQueries` starts
or joins the fetch.

**`saw(ws, ids)`**, in this order:
1. For each id not in `departed` and not in `pending`: `pending.set(id, clock++)`.
2. Return if `pending` is empty.
3. `state = queryClient.getQueryState(directoryKeys.members(ws))`. Return if `state?.data === undefined`
   (decision 14) or `state.fetchStatus !== 'idle'` (join — R2).
4. `ownStarting = true; void queryClient.refetchQueries({ queryKey, exact: true }, { cancelRefetch: false }); ownStarting = false`.

**`load(ws, fetch)`**:
1. At entry: `own = ownStarting; ownStarting = false; startedAt = clock++;
   hadData = queryClient.getQueryData(key) !== undefined`.
2. `members = await fetch()`. On a throw: every pending id with `hadData && seenAt < startedAt`
   moves to `departed` (decision 15); rethrow.
3. On success: if `!own || otherMarked`, `departed.clear()` and `otherMarked = false` (R3,
   decisions 7 and 20 — the mark is read at landing, so a reconnect that joined mid-flight counts).
   Then for each pending id: in `members`
   → delete; else if `hadData && seenAt < startedAt` → move to `departed`; else keep it pending
   — the next render's `saw` starts its one follow-up (R2, decided 6).
4. Return `members`.

**`useWorkspaceMembers`:**
- `const tracker = directoryTracker(useQueryClient())`.
- `queryFn: ({ queryKey }) => tracker.load(queryKey[1] as string, () => workspaceMembers(accessToken, queryKey[1] as string))`
  — the workspace from the key, never the closure (Global constraints).
- `const { data, fetchStatus } = useQuery(…)` — **`fetchStatus` is read for its re-render**;
  say so in a comment citing decision 13, or a tidy-up will delete an "unused" variable and break R2.
- `const unknown = new Set<string>()` each render; `nameFor` adds to it when `byId` misses.
- `useEffect(() => { if (workspaceId && unknown.size > 0) tracker.saw(workspaceId, unknown) })` —
  no dependency array: it must run after every commit.
- Header comment: the short id is now also the label while a refetch is in flight, not only for
  someone who has left; and how an unknown id refetches (issue, *Record in this slice*).

- [ ] Write `directoryRefresh.ts`, then change the hook. Task 1 passes: 11 passed.
- [ ] `MessageList.test.tsx`'s new test passes; the whole Vitest run is green, or each breakage
  is the ripple named in the file map — fixed in that test's stub and recorded in *Found while
  building*.
- [ ] Leave uncommitted.

## Task 4: The reconnect (GREEN)

**Files:** `lib/realtime/useChannelSocket.ts`

- [ ] In `onConnect`, beside the channel-list invalidation (`:143`), Task 2's two calls exactly,
  `otherReason` first. Import `directoryKeys` from `../../features/channels/useWorkspaceMembers`
  and `directoryTracker` from `../../features/channels/directoryRefresh`.
- [ ] Header (*Read state rides on the same connection*, `:55-58`): every connect also refetches the
  directory — messages missed while down may be from new members — joining a fetch in flight.
- [ ] Task 2 passes: 4 passed. `npm --prefix src/frontend run typecheck` clean.
- [ ] Leave uncommitted.

## Task 5: The record

- [ ] Doc 06 §5.2, after the *Typing* paragraph (`:303-307`), **"Names — added 2026-10-15"**: the
  directory is one query per workspace, stale after 5 minutes; an id it doesn't hold refetches it
  once, joining a fetch in flight (`cancelRefetch: false` — the default cancels and restarts);
  ids seen before a fetch that lands without them are departed and quiet until a fetch for another
  reason (a reconnect counts even when it joins the tracker's own fetch; a stale mount or focus
  refetch that joins one does not); every socket connect refetches it; the short id shows
  meanwhile. **Renames are not covered** — a changed name shows at the next refetch after the
  5 minutes are up (a mount, a window focus, a reconnect, or an unknown id).
- [ ] Doc 06 §5.2 *Naming* bullet (`:203-204`): "(`shortId` when unknown)" → "(`shortId` while
  unknown — the directory refetches once for an id it lacks; see *Names*)".
- [ ] Sweep: `Grep "shortId|left the workspace|no longer in the workspace"` across
  `src/frontend/src` and `docs/design` — comments that say the short id means only "left" (e.g.
  `directMessages.ts:15`) get "or not yet loaded". Change only comments.
- [ ] No register entry, no ADR (decided 5).
- [ ] Leave uncommitted.

## Task 6: Verification

- [ ] `scripts/test.sh lint unit`, then `scripts/test.sh e2e` — each layer once; the whole e2e layer,
  because the DM and messages journeys render names through the changed hook and the socket's
  `onConnect` changed. No `integration`: no service Python, SQL or stream changes. Expected:
  frontend Vitest 503 or more (488 + 15), Unit 953 or more; e2e 24 or more, all passed.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh` — nothing new (no Python here; gitleaks and semgrep still run).
- [ ] **First real run**, on the Compose stack (`docker compose up -d --build`), as close to the
  issue's *Acceptance* as Dex's fixed users allow: sign in as Ada; in a second browser sign in as
  a user who has never signed in on this stack, so first-sign-in auto-join runs
  (`identities.provision_user`), and post in #general. Ada sees the name, at most briefly the short
  id, without a reload; the DM list names them. Then stop and start the messaging container while
  Ada watches: no name turns into a short id. In the browser's network panel, count
  `…/members` requests: one per unknown id, none repeating for a departed one. Expect this run to
  find something the tests didn't; fix it with a test, and record it below.
- [ ] If a sibling branch merged while this was in flight, merge `main` and rerun all of the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

- **No departures from the plan's tracker/hook/`onConnect` design.** All 15 new tests passed first
  time; the whole Vitest run (503) needed no stub fixes — the predicted ripple did not occur.
- `useChannelSocket.onConnect` guards `otherReason` with `if (workspaceId)` (the id is nullable)
  rather than casting; the invalidation runs either way, as the channel list's does.
- `directoryRefresh.ts` imports `directoryKeys` from `useWorkspaceMembers.ts`, which imports the
  tracker: a cycle used only inside function bodies, so safe under ESM. No test pins it.
- **The first real run by hand (two browsers, messaging restart) was not done** — left for the human.

## Not in this plan

- Renames before the 5 minutes are up, and any Auth membership or profile event (issue).
- Marking a departed member's messages as departed in the UI (issue).
- A retry for a refetch that failed, other than the next fetch for another reason (decision 15).

## Self-review

- **Requirements:** R1 → Task 1 rows 1–2, Task 3; R2 → rows 2–4, 6, Task 3 `saw` step 3; R3 →
  rows 3–5, 7–8; R4 → row 1, Task 2 consumer; R5 → Task 2 socket rows, Task 4; R6 → rows 10–11.
- **Where the rules meet:** R1+staleness → row 6; R1+R5 → Task 2 rows 2–3 (both orders; row 2 also
  proves the joined reconnect clears the departed set, decision 20); R3+rejoin → row 8; R1+switch
  → row 10.
- **Paths:** row 1 → Task 1 row 3; 2 → MessageList test; 3 → row 2; 4 → rows 4–5; 5 → Task 2;
  6 → row 10; 7 → *What no test covers*.
- **Decided already:** 1 → file map (SPA only); 2 → row 1; 3 → rows 5, 7; 4 → *Not in this plan*;
  5 → *Decisions*. *Record in this slice* → Tasks 3 (header) and 5.
- **Interfaces named by a test:** `useWorkspaceMembers`, `directoryKeys.members`, `shortId`
  (Task 1); `auth.membersBy`, `settleDirectory` (Tasks 1–2); `onConnect`'s invalidation and
  `otherReason` (Task 2 rows 1–2). `directoryTracker` is reached only through the hook and
  `onConnect`, by design — every branch of `saw` and `load` has a row: no data (row 3), in flight
  (rows 3, 6), own vs other (rows 7–8), the other-reason mark on an own fetch (Task 2 row 2),
  throw (row 9).
- **Negatives:** every "starts nothing" is `quiet(id)` — settled before the anchor exists, so a
  wrongly started fetch can't be absorbed by the anchor's request.
- **Names:** `directoryTracker`, `saw`, `load`, `otherReason`, `membersBy`, `settleDirectory`,
  `quiet` — the same in every task.
- **Known ripple:** existing consumer tests may make one more directory request (file map). The
  code-writer should budget for it.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** The anchor is replaced by `quiet(id)` (Task 1, *How each test is built*): settle
   with the new `settleDirectory` (idle across a macrotask, `notifyManager.ts:15`), take the
   baseline, ask the quiet id, **settle again** so a wrongly started fetch lands before any anchor
   exists, then ask the anchor and assert `before + 1`. A looping build never settles. Rows 2–5,
   7–9 and Task 2 rows 2–3 now use it, or a settled exact count; their *Also fails* column says
   what each wrong build shows. Task 2 row 2's count is now 3 while held and 4 + the anchor.
2. **Fixed, by preventing it.** Decision 20: `onConnect` calls `directoryTracker(…).otherReason(ws)`
   before its invalidation, and `load` clears the departed set at landing when the mark is set,
   even on its own fetch. Task 2 row 2 now has a departed Alan and asserts his one refetch (#4)
   after the joined fetch lands. The stale-mount and focus joins, which the tracker can't see
   (`queryObserver.ts:99-100`, `query.ts:336,345`), are decision 21, **assumed**, with the cost.
3. **Fixed.** Decision 7 moved to the *taken in this plan* table, marked **assumed**, with the other
   reading and the cost (one extra request per fetch for another reason while a departed author
   is on screen).
4. **Fixed.** Task 5's wording: "at the next refetch after the 5 minutes are up (a mount, a window
   focus, a reconnect, or an unknown id)".
5. **Fixed.** Corrections 2 now says `useChannelNames`' calls are plain render code
   (`useChannelNames.ts:30-48`).

*Left for later stages*, taken now: decision 8's StrictMode sentence corrected; a later-mounted
consumer is a second `renderHookWithProviders` with the same `queryClient` (*How each test is
built*, row 5); row 4 says the test must not `rerender()` between releasing #2 and expecting #3;
the MessageList test counts after `settleDirectory`.
