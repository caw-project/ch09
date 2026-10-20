# Test review — gh-3, round 3: approved

This round gates the code-writer's send-back. The fault was real: `user()` built `created_at` with `100 - age`, so a lower `age` made the newer account. It is fixed, and nothing else in the file changed.

## Responses checked

| Send-back point | Outcome |
|---|---|
| `user()` must seed `created` as `T0 + timedelta(days=age)`, so a lower `age` is older | **Resolved.** Line 62 reads `T0 + timedelta(days=age)`, and the docstring is now true. |
| The five migration tests must pass against the build as it stands | **Resolved.** I ran `uv run pytest src/services/auth/tests/integration/test_name_migration.py -q`. It printed `5 passed`. |

## What ran

- The command above, which printed `5 passed in 3.21s`. I ran nothing else and no sketch. The change is a seed expression in one file, and the rest of the suite was green in the code-writer's run.

## Findings

None.

**Wrong build:** one that kept the name on the newest account now fails three tests. `age=1` is the oldest row, and the tests expect it to keep `Sam`, `José` and `sam`. The fixture also has three candidates with distinct ages, so the oldest and the newest cannot be confused.

## Left for later stages

Carried over from round 2, unchanged:
- Show an error state for a failed profile GET rather than seeding the field from a stale name.
- Check that `directoryRefresh.ts`'s `load` ignores the abort signal.
- `App.test.tsx` uses 1 s `findBy` timeouts.
- The 20 ms wait in `clockSites` may need raising under load.

## Checked and sound

- The seed order now matches Req 4 and decision 27: the oldest keeps the name, with ties broken by `id`.
- The other two migration tests are unaffected. The trim/NFC test has no duplicates, and the empty-name test has no clash.
