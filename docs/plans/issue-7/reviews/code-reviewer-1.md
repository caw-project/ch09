# Code review — issue 7, round 1: approved

Approved. The tracker, hook and `onConnect` change are built as the plan specifies, step by step;
every check the plan names is green and I reran it; doc 06 and the headers say what the code does.
Three minor findings, none blocking. Three mutants survive, and each is harmless in the real code
by reading or by probe (see *Unpinned*).

## Expectations

Written before the green report or any production file the writer touched was opened. (The plan's
*Found while building* sits inside the plan file and was read with it — four bullets, no departures
claimed.)

### Task 3 — the tracker (`directoryRefresh.ts`) and the hook

**What the plan asks for that no test pins**
- `ownStarting = false` reset in `saw` *after* `refetchQueries` — every test path calls the
  `queryFn` synchronously, so `load` clears it first; only offline/paused would show the leak.
- The `queryFn` takes the workspace **from the key**, not the closure (Global constraints).
  A closure build is hard to tell apart: an unobserved query keeps the options it last had.
- A comment on the `fetchStatus` read citing decision 13 (row 4 pins the read, not the comment).
- A comment saying the effect has no dependency array on purpose (Global constraints).
- A comment that `otherMarked` survives a fetch that never lands, kept as is (plan-reviewer-2 and
  test-reviewer-2 *Left for later stages*).
- The hook's header: the short id is also the in-flight label; how an unknown id refetches.
- One tracker per `QueryClient` via a `WeakMap`; state per workspace; one clock per tracker.
- `exact: true` on `refetchQueries`; `hadData` checked before the fetch, not after.

**What each step takes for granted**
- `refetchQueries(…, { cancelRefetch: false })` invokes the `queryFn` synchronously
  (`query.ts` → `retryer.start()`), so `ownStarting` is read by the right call. Must be true in
  the installed 5.101.4, on the first and every later fetch.
- `refetchQueries` does refetch the query — not filtered out as disabled/static — on every path
  where `saw` gets past its guards.
- Reading `fetchStatus` re-renders **every consumer** when a fetch settles, and every consumer
  then calls `nameFor` again **during that render**. That holds for a consumer calling `nameFor`
  directly in render; it does **not** hold for one whose `nameFor` call sits in a `useMemo` keyed
  on something stable across an equal-data landing (`members`, `data`, a list): that render
  reports no unknown ids, so R2's follow-up never starts from it — and on a name-bringing landing
  it would also show a stale label (R4 "every place"). To check in each of the seven consumers
  and `useChannelNames`.
- The directory query has an observer whenever an unknown id is asked (it does — the asking
  hook is the observer).
- A workspace switch / sign-out: whether the app clears the `QueryClient` or keeps it; the
  tracker must be right either way (a removed query's first load is "another reason").

**Where it could go wrong**
- Too much: a loop — a pending id that never departs (hadData false forever, a cancelled fetch
  whose `load` still resolves), a retry on every render after a failure; StrictMode's double
  effect starting two fetches. Too little: a follow-up that never starts because no consumer
  re-renders or the effect is skipped; departed never cleared on a reconnect that joined.
- A fetch cancelled by someone else (`cancelQueries`, a default-`cancelRefetch` call elsewhere
  matching the prefix `['workspace-members']`): `load` still settles ids against a response the
  cache discards — named ids lose their pending entry while the cache lacks them. Should self-heal
  (they are re-stamped as new).
- `nameFor` closing over `byId` of its render — fine; `unknown` must be fresh per render, not
  module- or ref-level (a ref set would re-report ids from old renders).
- Stale `accessToken` in the `queryFn` closure — pre-existing, unchanged.

**Plausible wrong builds, and whether a test catches them**
- `fetchStatus` not read → caught (row 4, per test-reviewer-1's sketch).
- default `cancelRefetch` → caught. No in-flight check → caught.
- departed set per hook instance (`useRef`) → caught (row 5).
- one set across workspaces → caught (row 11).
- depart every missing id (no `seenAt < startedAt`) → caught. Clear on own fetch → caught.
- `ownStarting` never reset in `saw` → likely survives (unpinned).
- `hadData` read after the fetch → first load would depart ids → row 3 should catch.
- failed refetch leaves ids pending → caught (row 9).
- workspace from closure in `queryFn` → likely survives.

### Task 4 — `onConnect`

**Not pinned:** `otherReason` called **before** `invalidateQueries` (order: the mark is read at
landing, so the order may not matter while a fetch is in flight — but with no fetch in flight
`invalidateQueries` starts one synchronously whose `load` reads the mark only at landing, so
either order works; a survivor here would be harmless); `exact: true`; the header paragraph.
**Takes for granted:** `workspaceId` in the `onConnect` closure is the token's workspace — the
effect re-runs on token change, which a switch implies. **Wrong build:** invalidating with a prefix
key that hits every workspace (survives? R6 untested for connect); `refetchQueries` instead of
`invalidateQueries` (caught by the `isInvalidated` test).

### Task 5 — the record
- Doc 06 §5.2 **"Names — added 2026-10-15"** after *Typing*: one query per workspace, stale after
  5 minutes; unknown id refetches once, joining (`cancelRefetch: false`, the default cancels);
  departed until a fetch for another reason (reconnect counts even when joined; stale mount/focus
  join does not); every connect refetches; short id meanwhile; renames not covered — at the next
  refetch after the 5 minutes (mount, focus, reconnect, unknown id).
- Doc 06 *Naming* bullet: "(`shortId` while unknown — … see *Names*)".
- Comment sweep: "left" → "or not yet loaded" (e.g. `directMessages.ts:15`); comments only.
- No register entry, no ADR.

### Task 6 — verification
- `docs/test-report.md` at this tree's revision `-dirty`: lint, unit (frontend ≥ 503), e2e ≥ 24
  all passed; `build/test-results/e2e.xml` has the DM and messages journeys passed. The plan names
  no new journey, so only the e2e layer as a whole. The first real run by hand: *Found while
  building* says not done — for the human/acceptance.

## What ran

- `npm --prefix src/frontend test`: 51 files, **503 passed**. `run typecheck`: clean. `run lint`:
  clean. `run build`: built (402.59 kB JS).
- `python3 .claude/hooks/checks/conventions.py` over the three production files: no output (clean).
- `git rev-parse --short=12 HEAD` = `dca6fbbd5003`; `docs/test-report.md` shows Lint passed, Unit 953
  (frontend 503) and End-to-end 24/0/0, all at `dca6fbbd5003-dirty` — matches the green report.
  `build/test-results/e2e.xml`: `tests="24" failures="0" errors="0"`, including
  `test_grace_sees_the_direct_message_ada_starts_and_replies`. Integration not run — the plan
  names none (no service change).
- Grep of every `nameFor` call outside tests: all in render bodies or plain helpers called from
  render (`MessageList.tsx:329`, `ThreadPanel.tsx:123`, `DirectMessageList.tsx:47,105`,
  `MemberPanel.tsx:41`, `MessageComposer.tsx:157`, `ChannelView.tsx:82,121`, `SearchPage.tsx:34,75`,
  `useChannelNames.ts:31,46`); **none inside a `useMemo`**, so the premise that every consumer
  re-reports its unknown ids on the `fetchStatus` re-render holds.
- Installed TanStack source: `queryClient.ts:324` filters `!isDisabled() && !isStatic()`;
  `query.ts:281-287` — with an observer, disabled only when inactive; `staleTime` is numeric, so
  never static. `saw`'s refetch is not filtered out on any path it reaches.
- Grep for `clear`/`removeQueries`/`cancelQueries`/a bare `invalidateQueries()`: only
  `useChannels.ts:163` (channel detail). Nothing cancels or drops the directory query.

**Mutants and probes** (`build/sketch/frontend`, cleaned):

| # | File | Change / path | Tests run | Result |
|---|---|---|---|---|
| 1 | `directoryRefresh.ts` | drop `ownStarting = false` after `refetchQueries` in `saw` | hook, socket, MessageList | **survived** (40/40) |
| 2 | `useWorkspaceMembers.ts` | `queryFn` takes the workspace from the closure, not the key | hook | **survived** (11/11) |
| 3 | `useWorkspaceMembers.ts` | don't read `fetchStatus` | hook, socket | caught — 3 red (rows 4, 6, 7) |
| 4 | `directoryRefresh.ts` | treat every load as `hadData` (first load departs) | hook, socket, MessageList | **survived** (40/40) |
| 5 | `directoryRefresh.ts` | never reset `otherMarked` | socket | caught — 1 red (R1+R5 joined) |
| 6 | `useChannelSocket.ts` | invalidate by the prefix `['workspace-members']` (no `exact`), `otherReason` after | socket | survived (21/21) — the real code has `exact: true` and the order is immaterial (see *Unpinned*) |
| P1 | probe, real code | hook under `<StrictMode>` (as `main.tsx` mounts it): unknown id → exactly 2 requests and the name; a departed id → 3, then quiet across rerenders | probe | passed |
| P2 | probe, real code | production retry (`retry: n < 1`, as `main.tsx` for a 5xx) on a refetch that 500s persistently: ≤ 3 requests, then quiet across rerenders, short id shown | probe | passed |

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T3 `DirectoryTracker` interface (`saw`, `load`, `otherReason`), `directoryTracker(qc)` via `WeakMap` | `directoryRefresh.ts:23-45,128` | as planned |
| T3 state per workspace: `pending` Map, `departed` Set, `ownStarting`, `otherMarked`; one clock per tracker | `:36-59` | as planned |
| T3 `saw` steps 1–4 (stamp new ids; return if none pending; no data or not idle → return; own flag around `refetchQueries(exact, cancelRefetch:false)`) | `:78-95` | as planned |
| T3 `load` steps 1–4 (own/startedAt/hadData at entry; throw → depart seen-before if hadData, rethrow; clear on `!own \|\| otherMarked`; settle pending) | `:97-125` | as planned (first-load branch only removes named ids — same as the plan's "keep it pending") |
| T3 hook: tracker from `useQueryClient`; `queryFn` workspace from the key; reads `fetchStatus` with decision-13 comment; fresh `unknown` Set per render; no-deps effect with comment | `useWorkspaceMembers.ts:47-89` | as planned |
| T3 hook header | `:14-23` | as planned |
| T4 `onConnect`: `otherReason` then `invalidateQueries({ exact }, { cancelRefetch:false })` | `useChannelSocket.ts:148-156` | departed — `if (workspaceId)` guard on `otherReason` (recorded; sound, the id is nullable) |
| T4 header *Read state* paragraph | `:55-60` | as planned |
| T5 doc 06 *Names* paragraph, *Naming* bullet | `06-frontend-spa.md:204,309-318` | as planned (wording: finding 2) |
| T5 comment sweep | `directMessages.ts:15` already says "a partner it doesn't know" — no change needed | as planned |
| T5 no register entry / ADR | none | as planned |
| T6 `test.sh lint unit`, `e2e`; conventions; security | report and evidence above | as planned |
| T6 first real run by hand | not done | missing — finding 1 |
| T6 *Found while building* | filled, 4 bullets | as planned |
| Decisions 7, 10–17, 20 | traced in `saw`/`load`/`onConnect` | as planned |
| Plan-reviewer-2 / test-reviewer-2 *Left for later*: comment on `otherMarked` outliving a fetch that never lands | `directoryRefresh.ts:31` | as planned |

## Findings

### 1. The plan's first real run by hand was not done — minor
**Where:** plan Task 6, third step; green report *Left for the human* · **Checked:** read.
Task 6 asks for a two-browser run on the Compose stack (a never-signed-in user posts; Ada sees the
name; restart messaging; count `…/members` requests). The report leaves it for the human without
saying why it couldn't be done headless. Not blocking: the acceptance-reviewer's preview run
performs the issue's *Acceptance* checks, which are the same three, and is the issue's stated proof.
The human should read the acceptance proof for the request count (one per unknown id, none
repeating for a departed one), which only a network panel shows.

### 2. Doc 06 *Names* says "a mount" counts as a fetch for another reason — minor
**Where:** `docs/design/06-frontend-spa.md:313` · **Checked:** read against `staleTime: 5 min`.
Only a mount (or focus) *after the 5 minutes* fetches; a fresh mount fetches nothing. The renames
sentence a line later gets this right. Suggest "a stale mount, a window focus, a reconnect".

### 3. Doc 06 *Naming* bullet no longer wrapped — minor
**Where:** `docs/design/06-frontend-spa.md:204` · **Checked:** read. The edited line runs ~140
characters where the rest of the section wraps near 95. Cosmetic.

## Unpinned

- **Mutant 1 (`ownStarting` left set).** Every test path invokes the `queryFn` synchronously inside
  `refetchQueries`, so `load` clears the flag first. Only a paused (offline) fetch would leave it set,
  making the next fetch for another reason count as own and keep the departed set. The real code
  resets it (`directoryRefresh.ts:94`); reading only.
- **Mutant 2 (workspace from the closure).** Survives because an unobserved query keeps the options
  of its last observer, so after a switch A's query still closes over A. The real code reads the key
  (`useWorkspaceMembers.ts:56-58`), as the Global constraints require; reading only.
- **Mutant 4 (`hadData` ignored).** The first load starts (in `useQuery`'s subscribe) before the
  hook's own effect reports ids, so ids asked during it are stamped after `startedAt` and keep their
  follow-up either way. `hadData` matters only when a first load *failed* and a later one succeeds:
  the real code then gives those ids one more refetch (decision 14's spirit, Paths row 1) where the
  mutant would depart them at once. No test drives a failed-then-successful first load.
- **Mutant 6 (prefix invalidation / order).** The real code passes `exact: true`
  (`useChannelSocket.ts:154`). Order is immaterial: `otherMarked` is read at landing, and both a
  started and a joined fetch land after both calls.
- **StrictMode and production retry** — probes P1 and P2 pass on the real code. No approved test
  runs either.

## Left for the human

- Findings 1–3 above (minor): read the acceptance proof for the `…/members` request count; two doc
  06 wording fixes if wanted.
- Decision 7's reading (an id cleared by a fetch for another reason earns one more refetch) and
  decision 21 (a stale mount/focus refetch that joins the tracker's own fetch doesn't clear the
  departed set) are recorded assumptions, built as written.
- The tracker's `pending`/`departed` sets live as long as the `QueryClient` — a tab's session — and
  nothing on sign-out clears them (nor the query cache: no `queryClient.clear()` anywhere). Harmless
  for ids; noted for whoever adds sign-out cache clearing.

## Checked and sound

- R1/R2/R3/R4/R6 through the hook; R5 and both R1+R5 orders through `onConnect` — 15 new tests pass.
- Mutants caught: no `fetchStatus` read (3 red), `otherMarked` never reset (1 red).
- No `nameFor` call in a `useMemo`; no consumer changed.
- `refetchQueries` not filtered out on `saw`'s path (installed source); nothing cancels the directory.
- No test, helper or fixture changed by the code-writer beyond the red set (`git diff` matches the
  red report's files); no file outside the file map; `docs/test-report.md` written by the script.
- D24: the tracker holds ids and bookkeeping only, no names; nothing in Zustand.
- No `data-testid`, no suppression comment, no ESLint disable; the "unused" `fetchStatus` is kept by
  `void fetchStatus` with its reason.
