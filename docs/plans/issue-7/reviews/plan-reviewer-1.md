# Plan review — issue 7, round 1: changes_requested

A strong plan. Its library claims all hold against the installed TanStack 5.101.4, and it
found two traps the issue missed: `cancelRefetch` defaults, and a re-render lost to
structural sharing. Two major findings remain. The "anchored" negative the plan prescribes
for every quiet-id test can't fail the wrong builds its own *Also fails* column names. And a
fetch for another reason that joins the tracker's own fetch already in flight is left
unanswered against R3's "that fetch clears the departed set".

## Expectations                 (round 1 — written before the plan was opened)

**Decisions**
- E1. Where does the trigger live, given `nameFor` runs in render in seven components? An
  effect per consumer over the ids it rendered, a module/store set that the hook drains, or
  a `nameFor` that records misses for a later effect — and how is "one request for several
  unknown ids in one render" across *several components* guaranteed?
- E2. Where does the departed set live, and what is its key — per workspace (R6)? Is it
  TanStack-owned state, a module map, or Zustand (D24: client state only — is a departed
  set "server state"?). Is it cleared by *any* fetch that lands, or only one for "another
  reason" (R3)? How does the hook tell a refetch it started from a staleness/reconnect one?
- E3. "Started after the id was first seen" (R3) — how is a fetch's start time compared to
  an id's first-seen moment? `dataUpdatedAt` is the *end* of a fetch; what records the start?
- E4. Which TanStack call makes the refetch — `refetchQueries`, `invalidateQueries`, or
  `fetchQuery` — and with what `cancelRefetch`? (Issue: "check the installed version".)
  Does the call join an in-flight fetch (R2 "start nothing while it runs") or cancel it?
- E5. R2's follow-up: ids seen during an in-flight fetch that lands without them start
  **one** refetch — is it one for all of them together, and does an id first seen *before*
  the in-flight fetch started become departed at once instead (R3 vs R2)?
- E6. What counts as "the directory is fetched again for another reason" — staleness, a
  reconnect, a workspace switch, a reload, a window focus after 5 min, a mount after stale.
  Does the hook's own refetch count as clearing the departed set (it must not)?
- E7. R5: the reconnect refetch — `invalidateQueries` on `directoryKeys.members(ws)` in
  `onConnect`? On the first connect too (a fresh tab already loading the directory)?

**Conflicts**
- C1. R3 "until the directory is fetched again for another reason … That fetch clears the
  departed set" vs Decided 3 "a departed id refetches at most once per fetch of the
  directory" — the latter could be read as "once per *any* fetch" incl. the hook's own.
- C2. Timing t5: "socket reconnects → refetch (R5) → departed set cleared; alan unknown
  again after it" — does alan then start *another* refetch (he's unknown and not departed),
  or is he departed by the reconnect's fetch, which started after he was first seen? R3
  says the reconnect fetch clears the set; does it also re-mark ids missing from it?
- C3. The first-connect `onConnect` (R5) on page load vs the first load (R2): one request?
- C4. Doc 06 §4 says a workspace switch clears the TanStack cache; the code does not (no
  `queryClient.clear()`). R6 relies on per-workspace keys — does the plan note this?

**Tests** (Vitest, hook + one consumer)
- T1. Grace's name replaces her short id in a consumer (MessageList or similar), after a
  directory without her then one with her — through MSW, counting requests.
- T2. Several unknown ids, across more than one component in one render → exactly one request.
- T3. Departed: one request then none on further sightings — guard proves its positive.
- T4. First load pending: an unknown id starts nothing extra (held response); ids still
  unknown when it lands start exactly one refetch (R2) — two-sided.
- T5. An id first seen *during* an in-flight refetch, missing at landing → one more refetch;
  an id seen *before* it started, missing → departed, no more (the R3 boundary, both sides).
- T6. Reconnect refetches the directory (useChannelSocket test with the fake socket), and
  clears the departed set — a departed id unknown after it is... (whatever C2 settles).
- T7. Two workspaces: departed in A doesn't silence B; a refetch in flight for A lands in A only.
- T8. Staleness refetch with an unknown id at that moment → one request, not two.

**Risks**
- R-a. Render loop: refetch lands → re-render → `nameFor` miss → refetch again (for departed
  ids) — the departed set is what stops it; is it updated before the re-render effect runs?
- R-b. `invalidateQueries`/`refetchQueries` default `cancelRefetch: true` cancels an
  in-flight fetch *with data* — violating R2 (and an R1 refetch cancelling a staleness one).
- R-c. Seven observers, each with an effect → seven triggers per render unless deduped.
- R-d. Workspace switch: `accessToken` changes; a refetch closure in flight for A keyed on A.
- R-e. StrictMode double effects in dev double-trigger (harmless if deduped).
- R-f. An error response: does a failed refetch mark ids departed? (It didn't land "without
  them" — it didn't land.) Does an error loop refetches?
- R-g. Window-focus refetch after 5 min now counts as "another reason"; does the hook's own
  refetch of a stale query get mis-attributed?

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 an unknown id refetches, if not already fetching | `saw` steps 1–4; Task 1 rows 1–2 | covered |
| R2 one request at a time; ids seen during a fetch get one refetch if it lands without them | `saw` step 3, `load` step 3 (`seenAt ≥ startedAt` kept pending); rows 3, 4, 6 | covered (but see F1 for the "nothing more" halves) |
| R3 departed after a fetch *started after first seen* lands without it; quiet until a fetch for another reason, which clears the set | `load` steps 2–3, own flag (dec. 12); rows 4, 5, 7, 8 | covered, except a fetch for another reason that *joins* the tracker's own fetch (F2); the quiet halves are F1 |
| R4 short id while in flight; name everywhere when it lands | row 1, MessageList test, dec. 13 | covered |
| R5 a reconnect refetches the directory | Task 4, Task 2 rows 1–3 | covered |
| R6 per workspace, a refetch never writes the other's | key-derived workspace in `queryFn`, rows 10–11 | covered |
| *R1 + staleness*, one request | row 6 | covered |
| *R1 + R5*, one request | Task 2 rows 2–3, both orders | covered |
| *R3 + rejoin*, named at the next fetch for another reason | row 8 | covered |
| *R1 + switch* | row 10 | covered |
| Paths 1–6 | rows 3, MessageList, 2, 4–5, Task 2, 10 | covered; row 7 (second tab) declared uncovered, with a reason |
| Decided 1–5 | decision rows 1–5; file map is SPA-only | covered |
| Tests section (Vitest only, no BDD) | Test approach table | covered |
| Record: doc 06 section, hook header, no register/ADR | Tasks 3, 5 | covered (F4 on one sentence) |
| Not in this issue | *Not in this plan* | covered |
| E1 trigger outside render | dec. 8 (per-render Set + no-deps effect) | settled |
| E2 departed set's home, per workspace | dec. 9 (WeakMap per QueryClient) | settled |
| E3 "started after first seen" measured how | dec. 11 (logical clock; seenAt at the effect, which errs safe) | settled |
| E4 which call, `cancelRefetch` | dec. 10, Corrections 1 | settled |
| E5 R2 follow-up vs immediate departure | `load` step 3 | settled |
| E6 own refetch must not clear departed | dec. 12 | settled, except when joined (F2) |
| E7 / C3 the first connect | dec. 16, **assumed** | settled |
| C1 / C2 t5: re-departed by the clearing fetch, or one more refetch | dec. 7, "decided by the issue" | settled. It's a reading, not settled by the issue (F3) |
| C4 doc 06 §4 says a switch clears the cache; the code doesn't | not mentioned | sound: the switch re-creates the socket, whose `onConnect` (Task 4) refetches, so R3's "a workspace switch" holds without it |
| T1–T8 | rows 1–11, Task 2 | present; F1 affects T3, T4, T5 and the failure row |
| R-a render loop / R-f error loop | `load` settles before the success dispatch; dec. 15 | settled |
| R-b `cancelRefetch` | dec. 10 | settled |
| R-c seven effects | the first `saw` sets `fetchStatus` synchronously; the rest join | settled |
| R-e StrictMode | dec. 8 | settled (harmless; see *Left for later*) |

## Findings

### 1. The anchored negative can't fail the builds it is meant to catch — major
**Where:** Task 1, *How each test is built*, "Negatives are anchored"; the *Also fails*
column of rows 3, 4, 5, 8, 9; Task 2 rows 2–3 ("anchored: exactly 2"). · **Checked:**
`retryer.ts:219-222`, `:156` and `query.ts:528-566` (the `queryFn` starts synchronously inside
the effect's `refetchQueries`); `test/api.ts:88-101` (requests are recorded with no id, so
"waits for *its* request" can only mean "waits for the count to go up by one").

Take the build that wrongly refetches for a departed id, and suppose the departed id is
asked. Its `saw` starts refetch #N at once, during `act`. Then the anchor id is asked. It
sees `fetchStatus === 'fetching'` and joins #N, as R2 says it should. The test waits for
"one more" request, and #N is that request, so the count is exactly baseline + 1 and the
test passes. If the anchor is in #N's response, it is even named. So none of the "a retry on
each render", "a departed set kept per hook instance" or "a rejoin check on every render"
builds fails these tests. The departed halves of R3 and Decided 3 are then untested. The
`expected 1 to be 2` red stays valid, because each test fails earlier at red, so the gate
itself isn't vacuous. This is the shared context's *Wait on the last effect*.
**What settles it:** the plan prescribes an anchor that a wrongly started fetch can't absorb.
For example: take the baseline count before the quiet id is asked; wait until the directory
is idle (`isFetching` on the key is 0) *after* asking it; only then ask the anchor; wait for
its request and for idle again; then assert baseline + 1. Also fix Task 2 rows 2–3's
"anchored: exactly 2" so it matches the scheme (2 before the anchor, 3 after).

### 2. A fetch for another reason that joins the tracker's own fetch — major
**Where:** decision 12, `load` step 3 (`if (!own) departed.clear()`), Task 2 row 2. ·
**Checked:** `query.ts:404-419`: with `cancelRefetch: false`, or for an observer's
mount/focus refetch, a call during an in-flight fetch returns the existing promise. No new
`queryFn` call happens, so `own` stays `true`.

R3 lists a reconnect, staleness and a workspace switch as reasons, and says "That fetch
clears the departed set". The tracker can be mid-refetch for an unknown id when the socket
reconnects (Task 2 row 2 is exactly this case), or when a stale mount or focus refetch fires.
That reconnect's refetch *is* the tracker's own fetch, so the departed set isn't cleared. A
departed member who rejoined, or one whose messages came back in the recovered history,
stays a short id until the next separate fetch. The plan neither says this is acceptable nor
prevents it. **What settles it:** a decision row taking one side. Either accept it, with the
reason and the cost (≤5 min of a short id, the same as *R3 and a rejoin*). Or have
`onConnect` tell the tracker, for example with a `markOtherReason(ws)` that the landing
fetch honours. If it's the second, Task 2 row 2 also asserts that a departed id gets its one
refetch after the joined fetch lands.

### 3. Decision 7 is a reading, filed as "decided by the issue" — minor
**Where:** Decisions, row 7. · **Checked:** issue R3 and Timing t5.
R3's own definition would mark Alan departed again by the very fetch that clears the set,
because that fetch started after he was first seen. t5's "alan unknown again after it" can
be read either way. The plan's reading costs one extra request per fetch for another reason
while a departed author is on screen. It is defensible, so I accept it. It belongs among the
rows the human sees as **assumed**, with that cost written down.

### 4. Doc 06 wording: "a changed name shows within 5 minutes or on a reconnect" — minor
**Where:** Task 5, first bullet. · **Checked:** `useWorkspaceMembers.ts:44`; no
`refetchInterval` anywhere.
A 5-minute `staleTime` means a stale query refetches only on the next trigger: a mount, a
focus, a reconnect, or now an unknown id. It doesn't refetch *within* 5 minutes. The doc
should say "at the next refetch after 5 minutes (a mount, a window focus, a reconnect)".

### 5. Corrections 2 places `useChannelNames`' calls in a `useMemo` — minor
**Where:** Corrections 2. · **Checked:** `useChannelNames.ts:30-48`: plain render code, no
`useMemo`. The conclusion (they are tracked) still holds.

## Left for later stages

- F3, F4, F5 above.
- Decision 8 says StrictMode's double render "adds the same ids to the same set". In fact
  each render creates its own `Set`, and the committed render's effect and children use the
  second one. That is harmless, but don't rely on the claim.
- Row 5's "newly mounted consumer" can't be one more hook call in the same `renderHook`
  callback, which would break the rules of hooks. Use a second `renderHookWithProviders` with
  the same `queryClient`.
- Row 4 relies on the test *not* calling `rerender()` between releasing #2 and expecting #3.
  Otherwise the build that reads only `data` passes (decision 13).
- The MessageList test's "exactly 2 directory requests" is asserted after the name appears.
  Settle first, as in F1.

## Checked and sound

- Base commit `dca6fbb` = `git log -1`; 398 lines; the exemplar's header and sections are
  present; RED (1–2) comes before GREEN (3–4) with the test-reviewer gate; *Found while
  building* is empty; no task commits.
- TanStack 5.101.4 (primary checkout): `cancelRefetch ?? true` is at `queryClient.ts:319`; the
  cancel/join branch is at `query.ts:411-418`; `invalidateQueries` routes to `refetchQueries`;
  `retryer.start` calls `fn` synchronously when it can start; `updateResult` notifies only
  tracked props (`queryObserver.ts:666-700`). Corrections 1 and decisions 10–13 hold.
- `load` settles pending ids before the success dispatch, so the re-render's `saw` sees the
  departed set already updated. There's no render loop, and the error path is bounded
  (dec. 15).
- R6 holds: the workspace comes from the `queryKey`, and the departed set is per workspace.
  Switching back to A recreates the socket, so Task 4 refetches A's directory and clears A's
  set.
- Ripple: the eight `toHaveLength`/`toEqual([])` request-count assertions are in files that
  mount no directory consumer. `MessageList.test.tsx:28-29` stubs `auth.members` in
  `renderList`, as the plan says. `auth.problem` exists (`test/api.ts:331`).
  `useChannelSocket.test.tsx:356` is the test it mirrors. ESLint react-hooks is 5.2: no
  compiler rules, and a no-deps effect is allowed.
- No API, env, chart or OpenAPI change. Verification names `lint unit` and `e2e`, with a
  reason for leaving out `integration`. D28 and D16 are named and untouched. No 🔴 is built
  on.
- Each RED test's stated failure is what the runtime would report: today's hook fetches once,
  and no new production symbol is imported, so there's no load failure.
- Doc 06 line references `:203-204` and `:303-307`, and the baseline counts (938 / 488 / 24
  at `560114e3b455-dirty`), all match.
