# Green — gh-3, round 1

Built Tasks 5–8: Auth's `names`, migration `0002`, `identities` suffixing, `preferences` and the two routes, and the SPA's Settings feature, formatters, return-to-path and sidebar link; the record is written. Every test and check is green, including the Display names journey on its first e2e run.

## Re-verification (second code-writer run)
The first run's work was committed by the runner as "failed at code-writer": it had written `CLAUDE.md`, which the write check refuses (only `src/ docs/ charts/ …` and `README.md` are allowed). This run found the code and record already in the tree, wrote nothing but this section, and re-ran everything: Auth unit 80 passed; Vitest 569 passed; typecheck, lint, build clean; `scripts/test.sh lint unit integration` passed (integration 595); `scripts/test.sh e2e` passed; conventions check clean; `security.sh` clean (its gitleaks/semgrep steps print `mktemp` errors in this environment). `docs/test-report.md` is the one file this run changed.

## Baseline
Not taken as a separate run: I went straight from reading to building, so the red counts below are the red report's, not re-observed. Before building, Auth unit was 59 passing plus two files that failed at collection (red report); Vitest was 505 passing, 27 failing and 4 files failing to load. That is what the report says and nothing I saw contradicted it.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `auth/names.py`, `alembic/versions/0002_…py`, `models.py`, `migrations.py` (`upgrade(dsn, revision)`), `identities.py` (`display_name_taken`, `is_display_name_conflict`, savepoint-walking `provision_user`) | Auth unit 80, integration 161 pass | CH009 waiver on the name check. `merge` and `provision_user` flush, never commit |
| 6 | `preferences.py`, `routers/preferences.py`, `routers/users.py`, `schemas.py`, `main.py` | same | 409 text is fixed; `{}` PATCH writes nothing |
| 7 | `lib/auth/{api,storage,session}.ts`, `lib/time.ts`, `features/settings/{SettingsPage.tsx,useProfile.ts,usePreferences.ts}`, `App.tsx`, `WorkspaceSwitcher`, `ChatLayout`, `MessageItem`, `ThreadSummary`, `SearchResult`, `useWorkspaceMembers` (`directoryKeys.all`) | Vitest 569 pass | |
| 8 | register (D28 🟢, D46), two ADRs, docs 01 and 06, `CLAUDE.md`, both READMEs, `index.css`, scenario vocabulary | n/a | |

## What ran
- `uv run pytest src/services/auth/tests/unit`: 80 passed. `…/integration`: 161 passed.
- `npm --prefix src/frontend test`: 58 files, 569 passed. `run typecheck`: clean. `run lint`: clean. `run build`: built.
- `scripts/test.sh lint unit integration`: passed — unit 1843, integration 595. (It was first red on a CH009 finding in my `display_name_taken`; fixed by moving the waiver onto the `select`, rerun green.)
- `scripts/test.sh e2e`: passed — 25 of 25, including the Display names scenario.
- `python3 .claude/hooks/checks/conventions.py` over `identities.py`: clean. `.claude/hooks/security.sh`: "clean: ruff-bandit, conventions, gitleaks, semgrep", though it printed `mktemp: too few X's` for gitleaks and semgrep, so those two may not have really run in this environment.

## Beyond the tests
- Doc-comments for `names`, `preferences`, `profileWrites`, `returnPath`, `useClock`, `useSetClock`, `useUpdateDisplayName`, `SettingsPage` and the D46 waiver say why each rule is there.
- `time.ts` uses `hourCycle` (decision 33). `isReturnable` in `storage.ts` is the open-redirect guard, applied on write and on take.
- The Settings radios are disabled until the server answers since mount; the form does not exist until `GET /users/me` has (both pinned).
- `App.tsx`: on a failed callback the taken path travels to `/sign-in` in `state.from`, so a retry still returns.
- Task 8's `CLAUDE.md`, READMEs, `index.css`, doc 01 §3/§4/§5.1, doc 06 §3/§4/§5.2/§9 and the vocabulary's §1 and ruling 6.

## Departures from the plan
- **Two GREEN edits the plan assigned were not made: the integration `conftest.py` `TABLES` and `test_schema.py`'s `a_user`.** The code-writer may not write any test file. I made both and reverted them after finding the rule. Neither is needed: `truncate` uses `CASCADE`, and `test_email_uniqueness_ignores_case` still passes (it asserts only `IntegrityError`). The gap: nothing asserts that the *email* index, not the name index, raised there. A follow-up for the test pair if wanted.
- `directoryKeys.all()` added (see *Found while building*).
- The radios also unlock on a failed read.
- `PATCH /users/me {}` no longer bumps `version`.

## Picked up from earlier reviews
- `cancelQueries` in `useSetClock.onMutate` (test-reviewer-2): done, `onMutate` awaits it before writing.
- `merge` leaves the commit to the caller; the route commits (plan-reviewer-2).
- Task 1's `Zl` note: refusal applies after trimming; a trailing U+2028 is trimmed and accepted.
- Unrecorded default preferences stub and `time.test.ts` `hourCycle` pin: nothing for the code to do.

## Left for the human
- The plan's first real run on the Compose stack in two browsers: rename Ada and watch her sidebar and own messages change; try Grace's name in capitals (expect the 409 text on the field); choose 24-hour and see cached times change; open `/settings` signed out, sign in, and land back on it.
- Assumed decisions to read: 14 (`lower()` folding gap), 17 (zero-width joiner refused, so emoji ZWJ names are refused), 37 (sidebar name read from the directory).
- `security.sh` printed `mktemp` errors for its gitleaks and semgrep steps; run it where those work.
- `main` was not merged.
- **`CLAUDE.md` was edited by the first run** (D28 paragraph, D46 tenancy exception) and is committed. A code-writer may not write it, so a person should read that 3-line diff and keep or revert it.
