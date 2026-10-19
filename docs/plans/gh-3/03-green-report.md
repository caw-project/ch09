# Green — gh-3, round 1

Auth (names, key, migration 0002, preferences, rename and sign-in routes) and the SPA (Settings page, clock, return path) are built and the record is written. Auth's 280 tests and the 582 Vitest tests pass. **Not green end to end**: one type error in `SettingsPage.test.tsx:262` fails `tsc`, so `lint`, `build` and the frontend image fail and **the e2e journey has not run**. Sent back to the test-writer (`reviews/code-writer-sendback-3.md`).

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
- `uv run pytest src/services/auth` — 280 passed.
- `npm --prefix src/frontend test` — 582 passed. `npm … run lint` — clean.
- `npm --prefix src/frontend run typecheck` / `run build` — **fail**: `SettingsPage.test.tsx(262,7) TS2322` (a test file).
- `scripts/test.sh lint unit` — lint **failed** on that error (so unit did not run in that call); `scripts/test.sh unit` — passed (pytest + Vitest 582, coverage 95% statements).
- `conventions.py` over the changed Python — clean. `security.sh` — clean.
- `scripts/test.sh e2e` — **not run** (the image build runs `npm run build`). Auth integration was not run through `scripts/test.sh integration` (the plan's verification names `integration`; I ran Auth's integration tests with `uv run pytest`, in the 280).

## Beyond the tests
- Doc-comments for D46/D28 reasons in `names.py`, `models.py`, `routers/users.py`, `usePreferences.ts`, `useProfile.ts`, `SettingsPage.tsx`; stale D28 text removed from `MessageItem`, `ThreadSummary`, `SearchResult`, `schemas.py`, both READMEs, doc 06 §9.
- `provision_user` never logs a name (CH008); the 409 names nobody.

## Departures from the plan
1. `useClock` is a `useSyncExternalStore` cache read rather than `useQuery({ queryFn: skipToken })` (plan-reviewer-2 finding 1, test-reviewer-2).
2. `upgrade_to_head` kept (the test `conftest.py` imports it).

## Picked up from earlier reviews
`skipToken` conflict — see 1. Minor test findings (decomposed-form no-op, `{"theme": null}`) concern tests; left.

## Left for the human
First real run (`docker compose up -d --build`): rename Ada, try `GRACE` as Alan, choose 24-hour, reload and sign out on `/settings`. Check that "Back to chat" still returns to the channel after visiting Settings (relies on `ChatLayout` not remounting between routes; `App.test` covers it). Rerun e2e after the send-back.
