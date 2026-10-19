# Green — gh-3, round 2

Auth (names, key, migration 0002, preferences, rename and sign-in routes) and the SPA (Settings page, clock, return path) are built and the record is written. After the test-writer fixed the type error in `SettingsPage.test.tsx` (`reviews/code-writer-sendback-3.md`), everything is green: typecheck, build, lint, unit (1993), integration (625) and the whole e2e layer (25). No code changed in this round.

## Baseline
Before building: Auth unit/integration for the new files failed at load or as the red report says; Vitest had 24 failures and 4 load failures. I did not rerun the baseline separately; the first full runs after building were green except the type error below. (The red report's counts: 54 failing, 9 green by design.)

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `auth/names.py`, `preferences.py`, `models.py`, `migrations.py`, `alembic/versions/0002_…py` | unit + migration + schema + merge pass | `upgrade_to_head` kept as wrapper |
| 6 | `identities.py`, `routers/users.py`, `schemas.py` | `uv run pytest src/services/auth`: **280 passed** | savepoint-per-candidate; 409 via constraint name |
| 7 | `lib/auth/api.ts`, `session.ts`, `storage.ts`, `lib/time.ts`, `stores/chat.ts` | `time`, `session` pass | |
| 8 | `usePreferences.ts`, `useProfile.ts`, `SettingsPage.tsx`, `App.tsx`, `WorkspaceSwitcher`, `ChatLayout`, `ChannelView`, `MessageItem`, `ThreadSummary`, `SearchResult` | Vitest **582 passed** (58 files) | |
| 9 | register D28/D46, Conventions §5.4, docs 01 and 06, 2 ADRs, vocabulary §35, two READMEs | — | |

## What ran
Round 2, after the send-back fix:
- `npm --prefix src/frontend run typecheck` — clean; `run build` — built.
- `scripts/test.sh lint unit` — passed (Vitest 582 in 58 files, coverage 95% statements; unit total 1993).
- `scripts/test.sh integration` — passed, 625.
- `scripts/test.sh e2e` — passed, 25 scenarios, whole layer.
- Round 1: `uv run pytest src/services/auth` 280 passed; `conventions.py` over the changed Python and `security.sh` — clean.

## Beyond the tests
- Doc-comments for D46/D28 reasons in `names.py`, `models.py`, `routers/users.py`, `usePreferences.ts`, `useProfile.ts`, `SettingsPage.tsx`; stale D28 text removed from `MessageItem`, `ThreadSummary`, `SearchResult`, `schemas.py`, both READMEs, doc 06 §9.
- `provision_user` never logs a name (CH008); the 409 names nobody.

## Departures from the plan
1. `useClock` is a `useSyncExternalStore` cache read rather than `useQuery({ queryFn: skipToken })` (plan-reviewer-2 finding 1, test-reviewer-2).
2. `upgrade_to_head` kept (the test `conftest.py` imports it).

## Picked up from earlier reviews
`skipToken` conflict — see 1. Minor test findings (decomposed-form no-op, `{"theme": null}`) concern tests; left.

## Left for the human
First real run (`docker compose up -d --build`): rename Ada, try `GRACE` as Alan, choose 24-hour, reload and sign out on `/settings`. Check that "Back to chat" still returns to the channel after visiting Settings (relies on `ChatLayout` not remounting between routes; `App.test` covers it). (The e2e rerun after the send-back is done and green.)

## Found while building
Round trip: a type error in a test file (`SettingsPage.test.tsx:262`) stopped `tsc` and the frontend image build; the test-writer fixed it and the journey now passes. No code change was needed.
