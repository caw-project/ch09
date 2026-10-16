# The delivery workflow runs in Python and takes an issue by its key

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

ADR `261016-pluggable-delivery-backends` put delivery issues behind a backend library,
`tools/delivery`, and moved the `issue-writer` skill onto it, so an issue can now be a GitHub
issue as well as a file in `docs/issues/`. `scripts/deliver.sh` was left alone: it still took a
local file, read the number from an `Issue: N` line, and built every path — branch, worktree,
plan folder — from that number. A GitHub issue could be written but not delivered.

The script was 1,005 lines of bash 3.2, kept that way because macOS ships it. Its state machine
held per-pair rounds and open send-backs as variables named at runtime with `eval`, because
bash 3.2 has no associative arrays, and its results were picked apart with `jq`. It was proven
by one black-box test, `.claude/delivery/loop-test.sh`, which drives it with a fake `claude`.
The rules that bound each stage — the tools it may call and the paths it may write — are the
workflow's safety boundary, and nothing tested them directly.

The next slice runs the delivery from GitHub Actions: stage labels move on the issue at each
transition, and stops and answers may move into comments. Those are backend calls made from
inside the loop, at the points where the state changes. In bash each would be another CLI call
whose output has to be parsed back into `eval`-named variables. In Python they are method calls
on the backend object the issue was fetched with.

## Decision

We will run the delivery workflow in Python, as the package `delivery.run` inside
`tools/delivery`, and name the issue it delivers by its **key** — `issue-8` for a local issue,
`gh-3` for a GitHub one. `scripts/deliver.sh` stays the entry point, because `scripts/` is
where developers and CI start everything, but it is now a wrapper that runs
`uv run delivery deliver` from the repo root. The package's docstring replaces the script's
header as the reference.

The backend resolves as it does for every `delivery` command, and a key for another backend is
refused. On every run, start or resume, the issue is fetched through the backend and written to
`docs/plans/<key>/00-issue.md` in a single shape: the title as a heading, then the body. Local
issues are read from the checkout that runs the workflow, never the worktree, which may be cut
from a `main` that doesn't have them yet. The branch, worktree and plan folder are all named from
the key. Local keys are `issue-N`, so every existing plan, branch and worktree keeps its name.

Keys are unique only within one backend: two GitHub repos each have a `gh-3`. The first fetch
writes `docs/plans/<key>/source.json` — backend, URL and number — and a later run whose issue
comes from anywhere else is refused. The file is committed with the plan, so the guard still
holds after the plan merges.

The agents stay unaware of the backend. Their context block names the key (`Issue: gh-3`) and
the plan folder (`Plan dir: docs/plans/gh-3/`), and they take every path from it rather than
building one. No agent calls `delivery` or `gh`, and no agent is given the issue's URL.

The port changes no behaviour. The tool and write rules were printed from the bash functions
over every stage, situation and override, into `tools/delivery/tests/unit/fixtures/
deliver-rules.json`, and the Python rules are tested equal to it. `loop-test.sh` passed
against the bash before the port and passes against the Python after it, with only the way it
names the issue changed.

## Consequences

The rules that make up the safety boundary are now unit-tested row by row, and the state machine,
context block, invocation and record formats each have unit tests of their own. A GitHub issue
can be delivered from a laptop today. The next slice's label and comment calls have a place to
go: the loop already holds the backend.

The fixture is now a second statement of the rules. A deliberate change to a stage's tools or
write scope has to change both the fixture and the rule, which is the point, but it is friction.
`history.log` keeps the bash format, so measured runs stay comparable.

A run the bash script started can't be resumed. Its state was shell assignments. The Python
runner reports a bash run that finished as done, and refuses one that didn't, pointing at
`--restart`. No run was in flight when this landed.

The wrapper is still bash 3.2. It needs `uv`, which every stage already did. `jq` is no
longer needed.

`00-issue.md` no longer starts with `Issue: N` or a numbered heading, for any backend. Plans
written before this keep their old copies until their next run fetches the issue again.

## Alternatives Considered

### Keep the bash state machine and add a fetch command

Add `delivery issue fetch KEY --to <path>`, change about 30 lines of `deliver.sh` to call it
and build paths from the key. It is the smallest change, but the port is still owed: the next
slice's label changes land inside the loop, which is exactly where bash 3.2 is weakest.

### Resume bash-started runs

The bash state file is plain assignments, so it could have been parsed. Every worktree on disk
had finished, so the reader would have been code for no run, and a source of drift between two
state formats.

### Record an issue's source only in `build/delivery/`

The run directory is ignored by git and lives in the worktree. A guard kept there disappears
when the worktree is removed and never reaches `main`, which is where two repos' `gh-3` plans
would actually collide.

### No guard: one repo is one GitHub backend

The simplest rule to write down, and easy to break by accident the first time a fork or a
second trial repo is used. The guard is a few lines, and the failure it prevents is silent:
one issue's plan overwriting another's.
