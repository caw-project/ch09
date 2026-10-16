# Test review — gh-3, round 3: approved

This is a rework pass for the code-reviewer's send-back. The one new red test fails for the reason the send-back gives, and the one guard assertion is green by design. I found nothing open.

## Responses checked
| Send-back item | Writer's change | Outcome |
|---|---|---|
| 1. Migration 0002 misses `İ`/`i` duplicates (critical) | `test_duplicates_are_found_the_way_the_index_folds_case` plants an older "İvan" and a newer "ivan", upgrades to 0002, expects `["İvan", "ivan 2"]`, then expects an insert of "IVAN" to raise `IntegrityError`. | Resolved. |
| 2. Negative half of `is_display_name_conflict` (minor) | `test_email_uniqueness_ignores_case` asserts `is_display_name_conflict(exc.value) is False`. `a_user` now gives each user its own name. | Resolved. |

## What ran
- `uv run pytest src/services/auth/tests/integration/test_name_migration.py src/services/auth/tests/integration/test_schema.py -q` gave 1 failed, 8 passed.
- The failure is the new test. It fails at `upgrade(..., "0002")` with `UniqueViolationError: could not create unique index "uq_users_display_name"`, `Key (lower(display_name::text))=(ivan) is duplicated`. This is the failure the send-back reported.
- The other tests in `test_name_migration.py` and `test_schema.py` pass, including the new guard.
- I ran no sketch. The fix belongs in the migration's `_dedupe`, and this round changed only tests. A build that does the comparison with Postgres `lower()` gives the expected `["İvan", "ivan 2"]`.

## Findings
None.

## Left for later stages
- For the code-writer: compute every key in `_dedupe` (cleaned names and candidates) with Postgres `lower()` on `bind`, as the send-back says. Do not special-case `İ`.
- Optional: `TABLES` in `tests/integration/conftest.py` does not list `user_preferences`. `TRUNCATE … CASCADE` already clears it, so this is not needed.

## Checked and sound
- **Red for the right reason:** the new test fails at the real index build, not at a setup or load step. Only the new test is red.
- **Wrong build it catches:** a Python-`lower()` comparison. The failing run above shows it. The test uses the fixture's real planted rows, so there is no mock.
- **Both halves checked:** the renamed result checks the migration, and the "IVAN" insert checks that the index exists afterwards.
- **Guard in `test_schema.py`:** a build whose `is_display_name_conflict` returns True for any `IntegrityError` would fail it. Unique per-user names keep the email clash from being a name clash.
- **Existing assertions:** none weakened. The diff adds 23 lines to `test_name_migration.py` and changes `a_user` and one assertion in `test_schema.py`.
