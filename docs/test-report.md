# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `3daf13ab38e2-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `3daf13ab38e2-dirty` |
| Unit | ✅ passed | 1751 | 0 | 0 | `3daf13ab38e2-dirty` |
| Integration | ✅ passed | 26 | 0 | 0 | `3daf13ab38e2-dirty` |
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
| other | ✅ 780 passed | ✅ 26 passed |
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
