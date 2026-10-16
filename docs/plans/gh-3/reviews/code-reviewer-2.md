# Code review — gh-3, round 2: approved

Finding 1 is fixed the way the send-back asked. `_dedupe` in migration `0002` now compares every cleaned name and every candidate with Postgres `lower()`, the function the index uses. The new red test passes, and every Auth test passes with it. Finding 2 was made by the test pair, and the code passes it unchanged. Nothing critical or major is open. One item goes to the human: `docs/test-report.md` is from the commit before this fix, so a `scripts/test.sh` rerun is needed before commit.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. The migration decides duplicates with Python `lower()` and the index with Postgres `lower()` (critical) | `fold()` runs `SELECT lower(CAST(:name AS varchar))` on `bind` and caches by name. `reserved`, `assigned` and the candidate filter all use it. There is no special case for `İ`. | **Resolved.** `test_duplicates_are_found_the_way_the_index_folds_case` passes. It failed on the old code (test-reviewer-3). |
| 2. Plan's GREEN test edits never made (minor) | Made by the test pair: `a_user` gives each user its own name, and `test_email_uniqueness_ignores_case` asserts `is_display_name_conflict(...) is False`. | **Resolved.** It passes against the unchanged `identities.py`. That is the guard my round-1 mutant showed was missing. |
| Unpinned items (burst baseline, `pathname + search`, Enter guard, `hourCycle`, `refetchOnMount`) | Left alone. No code change. | Let go. They were never findings, and they stay under *Unpinned* in round 1. |

## What ran

- `uv run pytest src/services/auth/tests/unit src/services/auth/tests/integration -q`: **242 passed** (80 unit + 162 integration), real Postgres through testcontainers. This includes the new migration test and the `test_schema.py` guard.
- `uv run ruff check src/services/auth`: "All checks passed!"
- `python3 .claude/hooks/checks/conventions.py` over the migration, `test_name_migration.py` and `test_schema.py`: no findings.
- `git diff 80f2e0d HEAD`: the code changes only in the migration (+20/−4). The tests change only in the two files above, and the edits are the ones test-reviewer-3 approved. No SPA file changed, so Vitest, typecheck, lint and build were not rerun. They stand at round 1 (569 passed, all clean).
- No new sketch or mutant. The round-1 code is the mutant for this fix: a Python-`lower()` comparison. test-reviewer-3's run shows the new test fails on it with `UniqueViolationError … Key (lower(display_name::text))=(ivan) is duplicated`, and passes now. My round-1 probes are not affected by this change. The `ẞSA`/`ßsa`, `ǅura`/`ǆura` and Kelvin-sign pairs passed before. Folding now matches the index, so they cannot get worse.
- `docs/test-report.md`: still at revision `f45e31d7b664` (Lint, Unit 1843, Integration 595, E2E 25, all passed). The migration change came after that run, so the committed report does not cover it. The report shows 595 integration tests, and the tree now has 596. See *Left for the human*.

## Findings

None.

## Reading the fix

- **The comparison is the index's.** The index is `lower(display_name)` on a `varchar` column. `lower(CAST(:name AS varchar))` folds under the same default collation. So any pair the index would reject is now seen as a duplicate, and the walk keeps going until Postgres sees the candidate as free. `CREATE UNIQUE INDEX` can no longer fail on names the dedupe has passed.
- **Candidates are folded the same way.** The suffix walk cannot pick a name that is free in Python but taken in Postgres.
- **Cost:** one query per distinct name and per candidate tried, cached. `candidates()` is lazy. This is acceptable for a one-off migration.
- **Unchanged behaviour:** rows are still ordered by `created_at, id`, and an `UPDATE` still runs only when `final != stored`. No name appears in any log call.

## Unpinned

As in round 1, nothing new. The burst baseline taken afresh, `pathname + search`, the failed callback carrying `state.from`, the Enter-key submit guard, `refetchOnMount: 'always'` and `hourCycle` are held only by reading (code-reviewer-1, *Unpinned*). The negative half of `is_display_name_conflict` is now pinned by the `test_schema.py` guard.

## Left for the human

- **Rerun `scripts/test.sh lint unit integration` and `scripts/test.sh e2e` before committing.** The committed `docs/test-report.md` comes from `f45e31d`, before the migration fix. I ran the whole Auth integration suite myself (162 passed), and the e2e stack runs `0002` on an empty `users` table, where `_dedupe` does nothing. So I don't expect a change. But the record should show this tree.
- The rest is as in code-reviewer-1:
  - the `CLAUDE.md` edits, which a code-writer may not make: they are accurate, so keep or revert them;
  - StrictMode on the dev server;
  - Back to chat from `/settings` itself;
  - the assumed decisions 14, 17 and 37;
  - before the first deploy, run `0002` on a copy of real data;
  - the `mktemp` errors in `security.sh`.

## Checked and sound

- The fix uses Postgres `lower()` for every key and has no `İ` special case.
- The new migration test and the `test_schema.py` guard pass, and the earlier tests still pass (242).
- Ruff and the conventions checks are clean on every changed file.
- No file outside the migration and the two approved test files changed since the send-back, apart from the green report and the run state.
