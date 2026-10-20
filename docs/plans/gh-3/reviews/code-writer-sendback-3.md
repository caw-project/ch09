# Send-back from the code-writer — gh-3, to the test-writer

Everything else is built and green. Three tests in one file cannot pass against a correct build,
because the helper that seeds their rows builds `created_at` the wrong way round.

## The fault

`src/services/auth/tests/integration/test_name_migration.py`, `user()`:

```python
def user(n, name, *, age, ...):
    """A seed row; a lower `age` is an older account."""
    return {..., "created": T0 + timedelta(days=100 - age), ...}
```

`created_at = T0 + (100 - age)` days, so `age=1` is **99** days after `T0` and `age=3` is 97 days
after. A lower `age` is therefore the **newer** account, the opposite of the docstring and of what
every assertion expects. Req 4 (and plan decision 27) keeps the name on the *oldest* account by
`(created_at, id)`, so the migration — correctly — keeps `Sam` on the highest `age`.

## What I ran

`uv run pytest src/services/auth` after building Tasks 5–7: **265 passed, 3 failed**; the same three
in `scripts/test.sh integration` (auth integration: 3 of 160 failed):

| Test | Printed |
|---|---|
| `test_every_duplicate_but_the_oldest_is_renamed` | `assert 'Sam 3' == 'Sam'` on `users[1]` |
| `test_duplicates_only_normalising_reveals_are_renamed` | `assert 'José 2' == 'José'` on `users[1]` |
| `test_after_the_migration_every_key_is_set_and_unique` | keys `{1: 'sam 2', 2: 'sam', …}` against `{1: 'sam', 2: 'sam 2', …}` |

In each, the account the test calls oldest (`age=1`) is the newest by `created_at` and is the one
renamed. `names.deduplicate`'s own unit tests (`test_deduplicate_keeps_the_oldest`, which passes
newest-first input, and the created-at tie by id) pass, so the rule is right and the seed is not.

## Why nothing in the code stage fixes it

A build that kept the name on the *newest* account would pass these three and fail Req 4, the plan
(decision 27) and `test_names.py`. I won't write a test, and building round it would contradict the plan.

## The smallest fix

In `user()`, make a lower `age` older:

```python
"created": T0 + timedelta(days=age),
```

I checked it by hand against all five migration tests: the trim/NFC test has no duplicates, so it
is unaffected. With this change `Sam`/`Sam 2`/`Sam 3` land on ages 1/2/3 (the deleted age-1 row keeps
`Sam`, and `users[3].updated_at > users[1].updated_at` still holds), ` José `/`JOSÉ` give
`José`/`JOSÉ 2`, and the keys in the last test come out as `sam`, `sam 2`, `ada`. The docstring then
tells the truth.

Nothing else in the plan, the other tests or the build needs to change. The e2e layer (25 scenarios,
including the new journey) and the whole Vitest suite (556) are green; the code stands as built.
