# Test report — implementation plan

2026-09-17. Branch `feature/test-report`, worktree `caw-test-report`.

Until CI exists, a test run gives nothing to look back at: the result scrolls past in a terminal.
The goal is a report that `scripts/test.sh` writes on every run and that gets committed along with
the change it describes. The remote is a self-hosted forge, which renders Markdown and shows HTML
as source, so the report is **one Markdown file**.

Decisions, as Elton agreed them:

| # | Question | Answer |
|---|---|---|
| 1 | Format | Every tool writes a machine-readable result; one script merges them into Markdown |
| 2 | One file or one per run? | **One file**, overwritten. Git history is the history |
| 3 | Playwright screenshots? | **None** |

Decisions taken in this plan:

| # | Question | Answer |
|---|---|---|
| 4 | Where does the report live? | `docs/test-report.md` |
| 5 | Where do raw results go? | `build/test-results/`, which `.gitignore` already covers |
| 6 | Journeys: Cucumber JSON or JUnit? | **JUnit.** pytest-bdd leaves a scenario that fails in setup out of its Cucumber JSON entirely — a run against a stack that is down wrote `[]` for 19 errors. Feature and scenario names reach the JUnit file as per-test properties instead |
| 7 | A run of some layers only | Each layer keeps its last result. A layer is replaced only when it runs again, and one recorded at another revision is flagged in the report |
| 8 | A filtered run (`-- -k auth`) | Recorded, and shown against the layer, so a partial run cannot pass for a whole one |
| 9 | Durations, timestamps, hostnames | **Left out.** The report changes when a result changes, so its diff is the news |
| 10 | Frontend coverage | Included: Vitest writes Cobertura, the same shape as coverage.py's XML. Its figures are the file's header totals — see "Found while building" |
| 11 | Where the code lives | `testkit` — the dev-only test harness. `testkit.report` renders; a `testkit.plugin` hook labels journeys |

## How it fits together

```
scripts/test.sh
  per layer:  clear that layer's files in build/test-results/
              run the layer in a subshell, keeping its exit status
              python -m testkit.report record <layer> <status> <revision> -- <pytest args>
              python -m testkit.report render     → docs/test-report.md
              exit with the layer's status if it failed
```

A layer's results in `build/test-results/`:

| File | Written by |
|---|---|
| `<layer>.json` — `{"layer", "status", "revision", "args"}` | `testkit.report record` |
| `unit-python.xml`, `unit-python-coverage.xml` | pytest `--junitxml`, `--cov-report=xml:` |
| `unit-frontend.xml`, `unit-frontend-coverage/cobertura-coverage.xml` | Vitest `junit` reporter, `--coverage` with the `cobertura` reporter |
| `integration.xml` | pytest `--junitxml` |
| `e2e.xml` | pytest `--junitxml`, with per-scenario properties |

`lint` has a status and no XML. A layer that failed before its tool wrote anything — Docker down,
a failed `compose up` — has a status and no XML, and the report says so.

The revision is `git rev-parse --short=12 HEAD`, plus `-dirty` for uncommitted changes **other
than the report itself**. Otherwise a second run before a commit would call a clean tree dirty.

### Journey labels

`testkit.plugin` gives every item that carries pytest-bdd's `__scenario__` these user properties,
which pytest writes into the JUnit file under every family, xunit2 included:

| Property | Value |
|---|---|
| `feature` | the feature's name — `Reactions` |
| `scenario` | the scenario's name |
| `line` | the scenario's line in its `.feature` file, so a feature's scenarios keep file order |
| `tags` | the scenario's and feature's tags, sorted, space-separated — `bdd pending` |

### The report

~~~markdown
# Test report

Written by `scripts/test.sh` on every run; edits by hand are overwritten. Revision `e4d3396abcde`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `e4d3396abcde` |
| Unit | ❌ failed | 812 | 2 | 0 | `e4d3396abcde` |
| Integration | ⚪ not run | | | | |
| End-to-end | ✅ passed | 17 | 0 | 2 | ⚠️ `a1b2c3d4e5f6` |

> ⚠️ End-to-end was recorded at another revision.
> Unit ran with `-k auth`, so it is not the whole layer.

## Failures
### Unit · messaging · `…test_x::test_y`
```text
the failure's message, at most 20 lines
```

## Journeys
### Reactions
4 of 5 passed, 1 pending.
| Scenario | Result |                   ← ✅ passed · ❌ failed · ⏸️ pending · ⏭️ skipped

## By service
| Service | Unit | Integration |        ← ✅ 120 passed · ❌ 2 of 202 failed · —

## Coverage
| Package | Lines | Branches |         ← `████████░░` 81%
~~~

Failures come straight after the layers, because they are what a failed run is read for.

- **Failed** counts JUnit failures and errors together.
- **Service** is the third part of a pytest classname (`src.services.<service>.tests…`); every
  Vitest case is `frontend`.
- **Coverage** is unit only, as today. Lines are covered `<line>`s over all of them per service;
  branches are summed from `condition-coverage="50% (1/2)"`. Services sort by name, `frontend` last.
- **Journeys** group by `feature`, features by name, scenarios by `line`. A skipped scenario tagged
  `pending` is ⏸️ pending.
- `|` in a table cell is escaped. Failures sort by layer, then service, then test.

## Tests — red first

Unit, both in `src/services/testkit/tests/unit/`:

- **`test_report.py`** — `testkit.report` over results laid out in `tmp_path`: layer statuses and
  counts; not run; failed with no results; earlier revision; filtered args; per-service counts from
  pytest and Vitest classnames; coverage from both XML shapes and the bar; journeys grouped, ordered
  and pending; failures listed, sorted and truncated; `|` escaped; nothing from a timestamp,
  hostname or duration reaches the output; `record` then `render` through `main`.
- **`test_journeys.py`** — a subprocess pytest run over a demo feature, the way `test_plugin.py`
  runs one, whose `--junitxml` output carries the four properties.

`scripts/test.sh` itself has no unit layer to live in. It is proven by running it: a passing
`unit` run, a `unit -- -k` run, and a run with a test broken on purpose then restored.

## Build — after red review

1. `testkit/report.py` and the plugin hook, to green.
2. `scripts/test.sh`: result paths, the per-layer subshell, record and render. The root
   `coverage.xml` moves into `build/test-results/`.
3. Commit-ready docs: CLAUDE.md's Testing section and the `scripts/test.sh` header name the report.
   The first `docs/test-report.md` comes from a real `scripts/test.sh all` run.

## Found while building

The first real run gave the frontend 89% of lines where Vitest printed 88.9%, which a bar
that rounds down cannot show. Two causes, each pinned by a test before the fix:

- **Vitest's Cobertura lists a function's lines twice**, under its class and again under
  `<methods>`: 909 `<line>` elements for 622 lines. Only a class's own `<lines>` count now.
- **Istanbul attaches several branches to one line**, and `condition-coverage` shows only
  some, so summing it gave 211/278 against Vitest's 309/397. A file that is all one service
  — the frontend's — is read from its header totals instead. coverage.py's per-line sums
  match its header exactly, so the Python services are still summed per package.
