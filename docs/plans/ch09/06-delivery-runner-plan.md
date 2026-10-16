# Delivery backends — slice 2: the runner in Python, issues by key

Slice 1 put issues behind a backend and moved the `issue-writer` onto it
(`04-delivery-backends-plan.md`, ADR `261016-pluggable-delivery-backends`). `deliver.sh`
still takes a local file. This slice ports it to Python inside `tools/delivery`, so it
takes a **key** and fetches the issue through the backend — `gh-3` can be delivered from
a laptop — and makes the agents agnostic to where the issue came from. GitHub Actions,
stage labels, comments and the commit exception are the next slice.

Settled in a grilling session on 2026-10-16, building on handoff 05.

## Decided

| # | Decision |
|---|---|
| 1 | **Scope:** full port + keys + agnostic agents. No labels, comments, commits, pushes or GHA — those come with the workflow a person watches from the issue. |
| 2 | **Full port, not a thin shim.** State machine, rounds, final round, send-backs, turn-cap resume, crash rerun, tool/write rules, context block, `claude` invocation and the preview wrapper all move to Python. The next slice's label changes land at stage transitions, which bash 3.2's `eval` state can't carry safely. |
| 3 | **Key only:** `scripts/deliver.sh [--backend B] [--url U] KEY [--restart]`. Backend resolves as `resolve.py` does (args, else `DELIVERY_BACKEND`/`DELIVERY_URL`, else local). A key whose prefix doesn't match the backend (`gh-3` on local) exits 2. The file-path form goes. |
| 4 | **No bash→Python resume.** Every worktree on disk is `STAGE=done`. State is `build/delivery/state.json`; an old `state` not at `done` stops with "started under the bash deliver.sh — finish it there or `--restart`". `history.log` keeps its format, so measured runs stay comparable. |
| 5 | **One `00-issue.md` shape:** `# <title>`, blank, body — whatever the backend. Re-fetched on every run, start or resume, as the bash `cp` is now. No `Issue:` line; the key is in the context block. |
| 6 | **Context block:** `Issue: <key>` (no `#`), plus `Plan dir: docs/plans/<key>/` and `Human answers file: <path>`, always present, even before the file exists. Prompts take every path from the block and never build one. |
| 7 | **Collision guard:** `docs/plans/<key>/source.json` — `{"backend", "url", "number"}` — written on first fetch, committed with the plan; a run whose source differs is refused (exit 2). No agent reads it; the block doesn't name it. |
| 8 | **`delivery deliver KEY [--restart]`** in the same package, modules under `delivery/run/`, stdlib only. `jq` leaves preflight. |
| 9 | **`loop-test.sh` is the oracle.** It passes against bash before the port, then only its invocation changes — key `issue-999` instead of a file — and it must pass against Python. Local keys keep every path (`caw-issue-999-loop`, `docs/plans/issue-999/`), so no assertion moves. Pytest-ifying it is a follow-up. |
| 10 | **`claude` from `PATH` through an injected seam,** `(args, cwd) -> result JSON`, as `github.py`'s `Runner`. Flags identical to today's. |
| 11 | **Rules proven against a golden fixture** captured once from the bash functions — every stage × first pass / rework / final × with/without send-back — kept in the repo; the Python tables must equal it. |
| 12 | **Preflight:** today's list minus `jq`, plus `gh` when the backend is GitHub; then `backend.get(key)` is the backend check (not `check()`, which demands write). A failed fetch exits 1 before any worktree is made. |
| 13 | **Local issues come from the checkout running the command** (`REPO_ROOT`), never the worktree — a new worktree is cut from `main` and may lack an unmerged issue. |
| 14 | **`scripts/deliver.sh` is a wrapper:** `exec uv run --project "$REPO_ROOT" delivery deliver "$@"`. The behaviour reference moves from its header to `delivery/run/__init__.py`'s docstring. Every `DELIVER_*` name, exit code (0 done · 1 error · 2 needs a human or bad config · 3 unbuilt stage) and `--restart` stay. |
| 15 | **issue-writer's GitHub ending** gives the `scripts/deliver.sh --backend github --url … gh-N` command; one line says the GHA trigger is still to come. |
| 16 | **Records:** a new ADR (runner in Python, issues by key); this plan ticks off handoff 05's open items it closes. |

## Out of scope

Stage labels; `needs_human` on the issue; commits, pushes and PRs; the GHA workflow and its
preview, screenshots and concurrency (handoff 03 items 2–7); moving `loop-test.sh` to
pytest; a live GitHub test; Forgejo and Azure DevOps.

## Shapes

```
delivery [--backend B] [--url U] deliver KEY [--restart]
scripts/deliver.sh [--backend B] [--url U] KEY [--restart]     # the same, through uv
```

```
docs/plans/<key>/00-issue.md      # Title, blank, body
docs/plans/<key>/source.json      # {"backend": "github", "url": "https://github.com/o/r", "number": 3}
build/delivery/state.json         # stage, status, step, review, rounds/final/sendbacks per pair, open send-backs, pending reviews
```

Context block, changed lines only:

```
Issue: gh-3
Issue file: docs/plans/gh-3/00-issue.md
Plan dir: docs/plans/gh-3/
Human answers file: docs/plans/gh-3/needs-human.md
```

Modules under `tools/delivery/delivery/run/`: `settings` (env → `DELIVER_*`), `keys`
(key ↔ backend, branch/worktree/plan paths, `source.json` guard, `00-issue.md` render),
`state`, `machine` (`next_stage`, rounds, final round, send-backs, review and send-back
paths), `rules` (models, effort, turns, allowed tools, write scope/deny), `context`,
`invoke` (the `claude` seam, turn-cap resume, crash rerun), `workspace` (git worktree,
`.env`, snapshots), `preview`, `preflight`, and `__init__` (the loop and the docstring).

## Tasks

### RED

1. **Golden fixture.** A throwaway script sources `deliver.sh`'s rule functions and prints
   `allowed_tools`, `write_scope`, `write_denied`, `model_for`, `effort_for`, `turns_for`
   for every stage × first/rework/final × send-back open or not, plus the env overrides
   (`DELIVER_MODEL`, `_<STAGE>`, `_REWORK_*`, `DELIVER_FINAL_*`) →
   `tools/delivery/tests/unit/fixtures/deliver-rules.json`. Script not kept.
2. **`test_rules.py`** — each Python rule equals the fixture, row by row.
3. **`test_machine.py`** — `next_stage` per verdict; round advance; final round and its
   only-approve rule; `changes_requested` in a final round stops; send-back targets
   (test→plan, code→test, acceptance→code, plan can't); `DELIVER_MAX_SENDBACKS`; final
   round moved out by a send-back; review and send-back paths.
4. **`test_context.py`** — the block per stage and situation, against the bash's lines,
   with the decision-6 changes; `Plan dir:` and `Human answers file:` always present.
5. **`test_keys.py`** — prefix ↔ backend, mismatch is a `ConfigError`; branch, worktree
   and plan dir from key, with `DELIVER_RUN`; `00-issue.md` rendering; `source.json`
   written, matched, and refused on a different backend, URL or number.
6. **`test_state.py`** — JSON round trip; a bash `state` not at `done` refused with the
   message; at `done` reported done.
7. **`test_invoke.py`** — the argument list each stage gets through the seam (`--agent`,
   `--model`, `--effort`, `--max-turns`, `--allowedTools`, `--json-schema`,
   `--permission-mode`, `--resume`); a turn-capped pass resumed once; a crash rerun once;
   a status the role may not return is an error.
8. **`test_preflight.py`** — `gh` required only for GitHub, `jq` not at all; fetch failure
   exits 1 before any worktree.
9. **`test_cli.py`** — `deliver` parses key, backend, `--restart`; exit 2 on mismatch.
10. **`loop-test.sh`** — first run it unchanged against the bash and record it green. Then
    change only the invocation: write `$ROOT/docs/issues/999.md` (removed in the trap) and
    call `scripts/deliver.sh issue-999`. It goes red against the bash, which can't take a key.

Stop at red for review.

### GREEN

11. `delivery/run/` modules as above; `deliver` subcommand in `cli.py`.
12. `scripts/deliver.sh` becomes the wrapper; header → `delivery/run/__init__.py` docstring.
13. Agents and their docs to `<key>` and take-paths-from-the-block:
    `.claude/delivery/agent-context.md` (team table, context-block reference, reviews path,
    `needs-human.md`), the `description:` lines of plan-writer, plan-reviewer, test-writer,
    code-writer and acceptance-reviewer, `plan-writer.md:70`,
    `docs/plans/exemplar-implementation-plan.md:65`.
14. `issue-writer` SKILL.md: the per-backend ending (decision 15).

### Record

15. ADR via `adr-writer`: the delivery runner in Python, issues by key, `source.json`.
16. `CLAUDE.md`: the Delivery workflow paragraph — key, not file; reference is the module
    docstring; paths `docs/plans/<key>/`, `../caw-<key>`, `feature/<key>`; `deliver.sh`
    no longer "still takes only a local issue file". Bash 3.2 note for `scripts/` stays —
    the wrapper is still bash.
17. Handoff 05 open items closed by this slice listed here, under *Closed*, at the end.

### Verify

18. `scripts/test.sh lint unit` green; `.claude/delivery/loop-test.sh` green against the
    Python runner.
19. By hand: `scripts/deliver.sh issue-8` reaches plan-writer's first pass with the new
    block (`DELIVER_MODEL=haiku`, stopped after one stage); `scripts/deliver.sh --backend
    github --url https://github.com/caw-project/ch09 gh-3` fetches, writes `00-issue.md` and
    `source.json`, and reaches plan-writer. Fix issue #3's D46 tenancy note first (handoff
    05, *Known gaps*) if it is to run further.

## Found while building

- **`Human answers:` kept, not replaced.** Decision 6 said an always-present `Human answers
  file:` line. The bash's `Human answers:` appears only once a person has answered, which is
  what tells an agent there are answers to read, and agents never write the file — the
  workflow does. So the block keeps `Human answers:` as it was, and `agent-context.md` points
  at `needs-human.md` in the plan dir. `Plan dir:` covers every path an agent built.
- **The wrapper reorders arguments.** `delivery` takes `--backend`/`--url` before its
  command, and `scripts/deliver.sh --backend github --url … gh-3` puts them anywhere; the
  wrapper moves them in front of `deliver`.
- **Bad `DELIVER_*` settings exit 2, not 1.** They are configuration, and every `delivery`
  command exits 2 for that. Nothing tested for 1.
- **`loop-test.sh` passes `--backend local`**, so a `DELIVERY_BACKEND` left in the shell can't
  send the oracle to GitHub.
- **An integration test** (`tests/integration/test_deliver.py`) covers what only a remote
  backend does — fetch, issue copy, `source.json`, the refusal, a failed fetch before any
  worktree — against a real git repo, a fake `gh` and a fake agent. `loop-test.sh` is local only.
- **The acceptance-reviewer's feature pack** is `test_<key>.py` with `-` as `_`
  (`test_gh_3.py`): a hyphen isn't a module name.
- **Snapshots hash content in Python** (SHA-1 of the bytes) instead of `git hash-object`, one
  process per path. They only detect change, so git's clean filters don't matter.

- **From the independent review**, fixed with a test each:
  - agents and the deploy script ran inside the primary checkout's virtualenv, which
    `uv run` had activated for the runner; `agent_env` now drops `VIRTUAL_ENV` and its `bin`
    from PATH — only an active virtualenv's, never `sys.prefix`'s;
  - `issue-08` was a second delivery of `issue-8`: keys with a leading zero are refused;
  - a missing deploy script crashed the run; it now fails the try, as the bash's did, and a
    bare `DELIVER_DEPLOY_SH` name is found on PATH again;
  - a rerun of a finished delivery rewrote its committed `00-issue.md`; the done check now
    comes first;
  - an unexpected error (a corrupt state file, a failing git) is one `error:` line, not a
    traceback;
  - the wrapper runs `uv run --frozen`, so a run never relocks the primary checkout.
- **The code-writer may not write `.github/workflows/`**, decided with the user for the
  GitHub Actions slice and landed here: `write_denied` gains the pattern, the fixture row
  changed with it on purpose, and `agent-context.md` makes CI workflows out of scope for every
  stage. A pushed workflow change needs a token the delivery doesn't hold.
  Left as they are: `source.json` compares URLs case-sensitively (a false refusal, never a
  missed one); a refusal leaves the new worktree behind; `loop-test.sh` would overwrite a
  real `docs/issues/999.md`.

## Verified

- `uv run pytest tools/delivery`: 759 passed after the review's fixes and the workflow rule (751 before) — the 560 fixture passes, 7 stage rule tables,
  machine, context, keys, state, invoke, record, preflight, settings, CLI, and 5 integration.
- `loop-test.sh`: every scenario green against the bash before the port, and against the
  Python runner after it, through `scripts/deliver.sh issue-999`.
- By hand, with `claude` stubbed and a fake deploy: `scripts/deliver.sh --backend github --url
  https://github.com/caw-project/ch09 gh-3` fetched issue #3 through the real `gh`, wrote
  `00-issue.md` (138 lines: heading plus GitHub's 137) and `source.json`, ran all seven
  stages straight through on `feature/gh-3-stub`, and exited 0. No prompt held the issue's
  URL. A rerun said done; the same key from `sixeyed/claude-at-work-project` was refused,
  exit 2. The stub's worktree and branch were removed afterwards.
- The same issue locally: `gh-3` copied to `docs/issues/009.md` with `delivery issue create
  --backend local`, then `scripts/deliver.sh issue-9` with the same stubs — seven stages, exit 0,
  `source.json` `{"backend": "local", "url": null, "number": 9}`. Its `00-issue.md` is byte for
  byte the one `gh-3` renders: one shape for both backends. `issue-9` with `--backend github`
  is refused, exit 2. The stub's worktree and branch were removed; `docs/issues/009.md` stays.
- Not run: a real-model delivery of `gh-3` — issue #3 still needs its D46 tenancy note
  (handoff 05, *Known gaps*) before it is worth one.

## Closed

From handoff 05:

- **Job 1** — `deliver.sh` in Python: the state machine, per-stage settings, tool and write
  rules (fixture-tested), the context block, the preview wrapper, run state (bash runs: done
  reported, unfinished refused).
- **Job 2** — the library for a delivery: a key, not a file; the fetch into `00-issue.md`;
  paths from the key; the collision guard; `DELIVER_RUN`'s suffix. Labels, comments and
  listing work are still open — they come with the GHA slice.
- **Job 3** — agents that don't know the backend: descriptions, `agent-context.md`,
  `CLAUDE.md`, the exemplar plan; the three rules hold (no `delivery` or `gh`, no URL,
  `loop-test.sh` backend-free).
- **Open item 5** — the port's order: decided as one slice, behind `loop-test.sh`.

The next slice's brief is `07-delivery-actions-handoff.md`. Still open: stage labels, `needs_human` on GitHub, who commits and pushes, preview/screenshots/
PR body/concurrency/CI (handoff 03, items 2–7), a live GitHub test.
