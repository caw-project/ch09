# Send-back from the code-reviewer — gh-3, to the test-writer

The full review is `reviews/code-reviewer-1.md`. This file carries what needs a test before the
code-writer can fix it (CLAUDE.md, D32: a bug is fixed test-first). The plan does not need to
change. Decision 22's "reserved" and "assigned" sets are right in intent. The comparison they use
is the bug.

## 1. Migration 0002 misses duplicates that only Postgres `lower()` sees (review Finding 1, critical)

**What is wrong.** `_dedupe` in
`src/services/auth/auth/alembic/versions/0002_unique_display_names_and_preferences.py` builds
`reserved` and `assigned` with Python `str.lower()`. The index it then creates is
`lower(display_name)` in Postgres. The two disagree for `İ` (U+0130 LATIN CAPITAL LETTER I WITH
DOT ABOVE): Python gives `i̇` (`i` + U+0307), Postgres (`postgres:18`, default collation) gives
`i`. An older `İvan` and a newer `ivan` are therefore not renamed, and `CREATE UNIQUE INDEX`
fails. Auth's entrypoint and the chart's `auth-migrate` Job both run this migration, so the
upgrade is blocked on such data.

**What I ran.** I put a probe in the sketch, built like `test_name_migration.py` (the `at_0001`
fixture and planted rows, then `await upgrade(dsn, "0002")`). It printed:

```
pg lower: ['ivan', 'ivan'] py lower: i̇van ivan
sqlalchemy.exc.IntegrityError: … UniqueViolationError: could not create unique index "uq_users_display_name"
DETAIL:  Key (lower(display_name::text))=(ivan) is duplicated.
```

These pairs passed: `ẞSA`/`ßsa`, `ǅura`/`ǆura`, `KK`(Kelvin)/`kk`.

**Why my stage can't fix it.** I write only the review. No approved test covers this input, so
the red test has to come first.

**The smallest test I'd expect** in `src/services/auth/tests/integration/test_name_migration.py`,
in its style. Plant an older `"İvan"` and a newer `"ivan"`, then upgrade to 0002. The stored
names come out as `["İvan", "ivan 2"]`, and inserting another `"IVAN"` afterwards raises
`IntegrityError`. It fails today at `upgrade` with the `UniqueViolationError` above. A build that
makes it pass by special-casing `İ` should not be accepted: the comparison must be the index's.
For the code-writer afterwards: compute every key in `_dedupe` (cleaned names and candidates) with
Postgres `lower()` on `bind`, for example `SELECT lower(:name)`.

## 2. While you are there: the plan's two GREEN test edits nobody could make (review Finding 2, minor)

The plan's Task 5 file map gave the code-writer two test-file changes, and it may not write tests:

- `tests/integration/conftest.py`: `TABLES` gains `"user_preferences"` first. This is optional,
  because `TRUNCATE … CASCADE` already clears it.
- `tests/integration/test_schema.py`: `a_user` names each user from its email, and
  `test_email_uniqueness_ignores_case` asserts `identities.is_display_name_conflict(exc.value) is
  False`. Nothing approved holds that negative half today. A mutant returning True for any
  `IntegrityError` passed all 27 related tests, while my probe saw it hang the first-sign-in walk.

The real code already passes both. The new assertion should be green as soon as it is written. It
is a guard, not a red test.
