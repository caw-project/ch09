# Plan review — gh-3, round 2: approved

All nine round-1 findings are fixed in the plan, and the library claims behind the fixes check
out against the installed TanStack Query. One new minor issue, which round 1's fix introduced:
`useClock`'s `skipToken` observer shares one Query with the enabled one (Decision 42). It is narrow
and the code pair can settle it, so it goes under *Left for later stages*. No critical or major
finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 races with fetches in flight (major) | D39 `adopt` guard; D32 write then `invalidateQueries`; D30 `cancelQueries` in `onMutate`, invalidate in the last `onSettled`; Task 3 tests `a directory fetch in flight…`, `a preferences fetch in flight or started mid-save…`, `a switch in flight over a rename…` | **resolved.** Checked `queryClient.js:141-147` (`cancelQueries`, `revert: true`), `:165-169` (`refetchQueries` sets `cancelRefetch: true`), `query.js:183-189` (cancels a fetch already in flight when data exists), `queryClient.js:60-61` (`isMutating` counts `pending`), `mutation.js:94-144` (`pending` is dispatched before `onMutate` and before the scope wait; hook `onSettled` runs before the `success` dispatch, so the settling mutation counts itself and a scope-waiting one counts too). `session.ts:76-94` `adopt` awaits `me`+`workspaces` then `set`s, so a count taken before the await works. Each test holds the fetch and proves the new value survives |
| 2 preferences GET reaches unnamed tests (major) | D42 (`useClock` reads only); Task 3 *Known ripple* names four files | **resolved.** Grep of `*.test.tsx` for `ChatLayout`/`<App`: only `App`, `ChatLayout`, `ChatLayout.attachments` and `CreateChannelDialog` mount it (the other two hits are comments). `CreateChannelDialog.test.tsx:61` asserts `requests()` exactly in a dialog-only test, and the shell tests are at `:98-115`, as the plan says. All renders go through `renderWithProviders`' `MemoryRouter` (`test/render.tsx:61`), so `current-user` as a `<Link>` needs no new router |
| 3 two failed clock saves (minor) | D30 final invalidate; test `two failed choices end on what the server holds` | resolved. Traced Automatic → 24h (held) → 12h, both fail: 24h's `onError` sees 12h and doesn't revert, and `isMutating` is 2 so it doesn't invalidate; 12h reverts to 24h, then `isMutating` is 1 so it invalidates and the GET answers `{}` |
| 4 Req 8 vs KEEP_STACK rerun in a row (minor) | D41 **assumed** | resolved |
| 5 avatar dropped by the early return (minor) | D24 scoped to the name; guard test | resolved |
| 6 `from_idp` non-NFC (minor) | D19 normalises again; test with its positive | resolved |
| 7 second tab's sidebar (minor) | D40 **assumed** | resolved |
| 8 UTF-16 count (minor) | D36 `[...s].length`; 60-emoji case in the Save test | resolved |
| 9 `service_database` in an async test (minor) | Task 2 sync `at_0001` fixture | resolved. `testkit/databases.py:36-49` takes `Callable[[str], Awaitable[None]]` and calls `asyncio.run` twice, so `partial(upgrade_to, revision="0001")` fits |

## Findings

### 1. A `skipToken` observer resets the shared Query's `queryFn` — minor
**Where:** Decision 42, Task 3 *Interfaces* `useClock` · **Checked:** `queryObserver.js:84-94`
(every `setOptions` writes the observer's options onto the Query), react-query
`useBaseQuery.js:69-71` (`setOptions` in an effect on every render, so children before parents),
`query.js:183-203` (`fetch(undefined)` uses `this.options`; the fallback at `:198` only runs when
`queryFn` is falsy, and `skipToken` is a Symbol), `utils.js:225-237` (`skipToken` → `console.error`
and a rejected `Missing queryFn`).
There is one `['preferences']` Query, and its options are whichever observer last ran `setOptions`.
A `MessageItem` that renders without `ChatLayout` (a new message arriving) leaves `queryFn:
skipToken` on it. A later `invalidateQueries(['preferences'])` (D30's last `onSettled`) still finds
the Query active through `ChatLayout`'s observer, so it calls `fetch(undefined)` with the
`skipToken` options. The result is a console error and an error state, not the repair GET. D42's
claim that invalidation refetches only enabled queries is true, but this case slips past it. It
happens only when a clock save settles after the user has left `/settings` and a message has
re-rendered on its own: on `/settings` the page's own observer sets real options when it mounts.
That is why it is minor. To settle it, give `useClock` the same `queryFn` with `enabled: false`:
it still sends nothing, and the plan's `requests()` assertion still holds. A test that mounts an
enabled observer and a reading child, re-renders only the child, invalidates, and expects a GET
pins it.

## Left for later stages

- **Finding 1**, for the test and code pairs. The code-writer may make the `enabled: false` change
  as a recorded departure from D42, and the test-writer may add the test it names.
- `a directory fetch in flight…` and `two failed choices…` only send their call-3 or final GET
  when the hook under test has an active observer. Data seeded only with `setQueryData` has no
  `queryFn` and no observer (`query.js:102-106`). The test-writer should mount the directory and
  preferences hooks, not just seed the cache.
- From round 1: Task 10's `docker compose up` first real run is the exemplar's wording. Whether
  the code-writer runs it is decided by its own agent file.

## Checked and sound

- 600 lines in all, about 590 without *Review responses*, so within 250–600. RED 1–4 come before
  GREEN, and no task commits. *Found while building* is empty. Base `b5f3ffd` is the primary
  checkout's `main`.
- The new decision rows 39–42 are recorded with their alternatives, and 40 and 41 are marked
  **assumed**.
- The *Self-review*'s writers-of-the-same-state list matches D30, D32 and D39, and each pair has a
  named Vitest test.
- Nothing new builds on a 🔴 entry. The coverage table, library checks, expected reds, record and
  verification tasks are as in round 1, and the rework didn't touch them.
