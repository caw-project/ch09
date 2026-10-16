# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `f88ba89b6fc8-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `f88ba89b6fc8-dirty` |
| Unit | ✅ passed | 1050 | 0 | 0 | `f88ba89b6fc8-dirty` |
| Integration | ⚪ not run | | | | |
| End-to-end | ⚪ not run | | | | |

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
| other | ✅ 79 passed | — |
| shared | ✅ 94 passed | — |
| testkit | ✅ 119 passed | — |
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
