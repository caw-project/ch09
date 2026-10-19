# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `e1bb28310ce2-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `e1bb28310ce2-dirty` |
| Unit | ✅ passed | 1833 | 0 | 0 | `e1bb28310ce2-dirty` |
| Integration | ✅ passed | 45 | 0 | 0 | `e1bb28310ce2-dirty` |
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
| other | ✅ 851 passed | ✅ 45 passed |
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
