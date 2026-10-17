# Green — gh-3, round 1

Auth (names, preferences, two migrations, the rename and sign-in suffixing, two routes) and the SPA (`/settings`, the clock, the return path, `updateProfile`, `lastChannelId`) are built to the plan, with the record (register D28/D46, Conventions §3 and §5.4, docs 01 and 06, two ADRs). Every test and check is green, including the new journey.

## Baseline
The tree was as the red report describes: tests were committed, no production code. I did not rerun the whole red set before building (Auth unit 59 existing + two files failing to collect; Vitest 503 + 36 failing + 2 load failures, per the red report and the test review's own runs). No difference was noticed when the files first ran against the build.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `auth/names.py`, `auth/preferences.py` | Auth unit 107 pass (59 + 48) | refused set per the plan's table |
| 6 | `models.py`, `alembic/versions/0002…`, `0003…` | `test_migration_0002`, `test_schema` pass | key set by `@validates` |
| 7 | `identities.py`, `schemas.py`, `routers/users.py` | Auth integration 157 pass | rename in a SAVEPOINT; sign-in retry loop; preferences routes before `/{user_id}` |
| 8 | `lib/auth/api.ts`, `lib/time.ts`, `features/settings/*`, `ChatLayout`, `WorkspaceSwitcher`, `MessageItem`, `ThreadSummary`, `SearchResult`, `stores/chat.ts`, `useWorkspaceMembers.ts` | settings 26 pass | |
| 9 | `storage.ts`, `session.ts`, `App.tsx` | `session`, `App` pass | |
| 10–11 | docstrings, README, docs 00/01/06/07, 2 ADRs | — | |

## What ran
- `npm --prefix src/frontend test`: 54 files, **558 passed** (503 + 55).
- `npm --prefix src/frontend run typecheck`: clean. `run lint`: clean. `run build`: built.
- `scripts/test.sh lint unit integration`: lint passed; unit **1860 passed**; integration **594 passed** (Auth 157 of them).
- `scripts/test.sh e2e`: **25 passed, 0 failed**, including `Grace sees the name Alan gives himself on his message`. It passed on its first run.
- `python3 .claude/hooks/checks/conventions.py` over every changed Python file: clean. `.claude/hooks/security.sh`: clean.
- A flake: see *Departures* 7.

## Beyond the tests
- Doc-comments on `names.py`, `preferences.py`, `User`/`UserPreferences`, `useSetClock` (why `scope`, why the conditional restore), `useUpdateDisplayName` (hook-level `onSuccess`, awaited cancel), `adopt`/`updateProfile`.
- CH009 waivers on `_taken_keys` and the migration read, each citing D46 and Conventions §3.
- `resetLastChannel()` in `ChatLayout`'s workspace cleanup (decision 29).
- The D46/D28 record, Conventions §3 third exception and §5.4 note; doc 01 §3, §4, §5.1; doc 06 §3, §4, §5.2, §9; README.

## Departures from the plan
See plan *Found while building*: `useClock` in its own file; `directoryKeys.all`; the form not rendered until fetched; an unchanged avatar writes nothing; `usePreferences` on defaults.

## Picked up from earlier reviews
- `_taken_keys` reads deleted rows (test-review 1): yes, with the waiver.
- `resetLastChannel()` on workspace change (test-review): added.
- `hourCycle`, not `hour12` (test-review 1): used.
- Revisit shows the server's name (test-review 3): `refetchOnMount: 'always'` and `isFetchedAfterMount`.
- Two failed clock saves in a row (plan-review 2): left, optional.
- `scope` kept (test-review): yes.

## Left for the human
- First real run by hand (`docker compose up -d --build`): rename Ada, watch the sidebar and her message; take Grace's name in capitals (409 on the field); choose 24-hour and look at an afternoon message; sign out on `/settings` and sign back in (lands on `/settings`).
- Read the assumed decisions: 12, 13, 15, 17/19/22, 25, 28, 29, 30, 34, 37.
- `origin/feature/gh-3-run1` edits the same files; the two cannot both merge.
