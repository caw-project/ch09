# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `c183c51e1d62-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ❌ failed | | | | `c183c51e1d62-dirty` |
| Unit | ✅ passed | 1993 | 0 | 0 | `c183c51e1d62-dirty` |
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
| auth | ✅ 110 passed | — |
| canvas | ✅ 2 passed | — |
| messaging | ✅ 136 passed | — |
| other | ✅ 881 passed | — |
| shared | ✅ 94 passed | — |
| testkit | ✅ 130 passed | — |
| worker | ✅ 19 passed | — |
| frontend | ✅ 582 passed | — |

## Coverage

Unit tests only.

| Package | Lines | Branches |
|---|---|---|
| asset | `██████░░░░` 66% | `█████░░░░░` 54% |
| auth | `██████░░░░` 62% | `██░░░░░░░░` 27% |
| canvas | `█████████░` 96% | — |
| contracts | `██████████` 100% | — |
| messaging | `█████░░░░░` 56% | `███░░░░░░░` 31% |
| shared | `█████████░` 90% | `███████░░░` 75% |
| worker | `██████░░░░` 65% | `███░░░░░░░` 30% |
| frontend | `█████████░` 97% | `████████░░` 88% |
