# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `1accafe40fbf-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `1accafe40fbf-dirty` |
| Unit | ✅ passed | 1863 | 0 | 0 | `1accafe40fbf-dirty` |
| Integration | ✅ passed | 47 | 0 | 0 | `1accafe40fbf-dirty` |
| End-to-end | ⚪ not run | | | | |

> Integration ran with `tools/delivery`, so it is not the whole layer.

## Failures

None.

## Journeys

No journeys recorded.

## By service

| Service | Unit | Integration |
|---|---|---|
| asset | ✅ 39 passed | — |
| auth | ✅ 59 passed | — |
| canvas | ✅ 2 passed | — |
| messaging | ✅ 136 passed | — |
| other | ✅ 881 passed | ✅ 47 passed |
| shared | ✅ 94 passed | — |
| testkit | ✅ 130 passed | — |
| worker | ✅ 19 passed | — |
| frontend | ✅ 503 passed | — |

## Coverage

Unit tests only.

| Package | Lines | Branches |
|---|---|---|
| asset | `██████░░░░` 66% | `█████░░░░░` 54% |
| auth | `██████░░░░` 61% | `█░░░░░░░░░` 18% |
| canvas | `█████████░` 96% | — |
| contracts | `██████████` 100% | — |
| messaging | `█████░░░░░` 56% | `███░░░░░░░` 31% |
| shared | `█████████░` 90% | `███████░░░` 75% |
| worker | `██████░░░░` 65% | `███░░░░░░░` 30% |
| frontend | `█████████░` 96% | `████████░░` 87% |
