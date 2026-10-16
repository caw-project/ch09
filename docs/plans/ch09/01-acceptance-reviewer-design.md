# Acceptance reviewer — design

A seventh stage for `scripts/deliver.sh`: the **acceptance-reviewer**. It checks the
delivered work, deploys it to a preview environment and runs it there, and collects the
proof a person needs to accept the branch without rebuilding, deploying or clicking
through it themselves. A later change has the same agent open the PR, so the proof is
laid out for a PR description from the start.

## What it is for

After the code-reviewer approves, a person still has to see the feature running before
they accept it. Today that means a deploy, a sign-in, and finding the feature by hand.
The acceptance-reviewer does that once, for everyone, and writes down what it saw.

**Success:** a person opens `docs/plans/issue-<N>/04-proof.md` and can accept or reject
the branch from it, with a live preview to click through if they want to.

**Not in scope:** creating the PR. `04-proof.md` is shaped so that step can lift its
sections whole.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | One stage, a reviewer with no writer — a pair of its own, `acceptance` | Nothing it finds is its to fix; fixes belong to the code pair |
| 2 | An **acceptance lens**, not a fourth code review | The plan, test and code reviewers have already reviewed; this checks the issue's acceptance criteria against the running app, and the record against itself |
| 3 | Sends back to the **code-writer** only, and only when a criterion fails on the preview or the standard smoke pack fails, caused by the branch | The existing rule carries a fault further back: the code stages send back to the test pair |
| 4 | Everything else it finds goes in `04-proof.md` for the human | A send-back costs a code round and a redeploy; a note costs nothing |
| 5 | `04-proof.md` is tracked, beside the other issue docs | It is the record of acceptance, and the PR's source |
| 6 | Screenshots, the feature's smoke pack and their results are disposable, under the ignored `build/acceptance/` | They are evidence for one run; the PR step uploads what it needs |
| 7 | The preview is **left up** when it finishes | So the human can click through; `04-proof.md` says how to take it down |
| 7a | **`deliver.sh` deploys the preview**, before each acceptance pass, retrying a failure once; the agent gets the outcome as `Preview:` and judges a failure | Added after review: a cold build and three Helm waits can outlast the agent's 10-minute Bash cap, and a deploy killed mid-Helm leaves the release locked |
| 7b | A dirty preview's image tag carries its namespace (`<sha>-<namespace>-dirty`) | Added after review: every delivery worktree from one commit tags `<sha>-dirty`, so previews left side by side would pull each other's images on a restart |
| 8 | A new `scripts/smoke.sh` runs a pytest + Playwright pack against an origin | `scripts/test.sh` rewrites the committed test report, which only the code-writer writes; driving a browser by hand isn't repeatable |
| 9 | Sonnet | Most of the stage is running and recording, like the stages already on Sonnet. Unmeasured — revisit with a run's numbers |

## 1. The pipeline — `scripts/deliver.sh`

```
plan-writer -> plan-reviewer -> test-writer -> test-reviewer -> code-writer -> code-reviewer -> acceptance-reviewer -> done
```

- `acceptance-reviewer` is appended to `STAGES`. `pair_of` gives `acceptance` and `role_of`
  gives `reviewer`, so the existing helpers serve it unchanged.
- **Results it may return:**
  - `approved` — on to `done`. Checked by `04-proof.md` existing and being non-empty, in
    place of a review file.
  - `send_back` — to the `code-writer`, with why in
    `docs/plans/issue-<N>/reviews/acceptance-reviewer-sendback-<R>.md`. The flow then comes
    forward through the code-reviewer to acceptance again. `earlier_pair` maps
    `acceptance` to `code`.
  - `needs_human` — as for every stage.
  - `changes_requested` — refused: there is no writer to take it. The script dies naming
    the stage, as it does for any status a stage may not return.
- **New state:**
  - `ROUNDS_acceptance` and `FINAL_acceptance`
  - `SB_acceptance_reviewer` in the open send-backs
  - `SENDBACKS_code`, bounded by `DELIVER_MAX_SENDBACKS`
  - `acceptance-reviewer` added to `SENDERS`
  - all of it written by `save_state`
- **The send-back branch** skips the `PENDING_` hand-off and the pair-round advance when
  the sender has no writer of its own. Its own round still advances, so a second pass is
  a rework pass and its proof is rewritten, not appended to.
- **Context block** for the stage:
  - the red report and the green report
  - `Proof: docs/plans/issue-<N>/04-proof.md`
  - `Evidence: build/acceptance/`
  - the send-back file path
- **The preview** is deployed by the workflow before each acceptance pass:
  `scripts/deploy.sh preview up` in the worktree, logged to `build/acceptance/preview-up.log`,
  retried once. The context block says `Preview: up at <origin> — log: …` or
  `Preview: failed twice — log: …`.
- **An approval needs a fresh proof**: `04-proof.md`'s hash must differ from before the
  pass, so an earlier pass's proof can't end a run.
- **Tools** (`allowed_tools`): `Read Grep Glob Write Edit Skill`, `read_only_bash`,
  `Bash(scripts/deploy.sh preview url)` and `Bash(scripts/smoke.sh *)`. No test runner, no
  build, nothing that writes the committed test report.
- **Write scope:** `^docs/plans/issue-<N>/(04-proof\.md$|reviews/acceptance-reviewer-sendback-)`.
  `build/` is outside every snapshot, so its evidence is unchecked by design.
- **Turns:** 200 for a first pass. Most of the stage's time is the deploy's wall clock,
  not turns.
- **Model:** `default_model` gives `sonnet`, matching the agent's `model:` line.
- **Pre-flight** adds `cloudflared`, `k3d`, `kubectl` and `curl`, the preview's
  dependencies — found missing at the last stage, they would cost every stage before it.
- **The closing log** points at `04-proof.md` first, then the preview's origin.
- **The header** gains the stage, its send-back, and the preview left running.

Two deliveries at once are already unsupported for `preview up` (both upgrade KEDA); the
header says so. `DELIVER_RUN` gives a distinct branch, so a distinct preview namespace.

## 2. The agent — `.claude/agents/acceptance-reviewer.md`

It reads `.claude/delivery/agent-context.md` first, like the other six; its own file holds
only its role.

**A first pass:**

1. **The record.** Read:
   - the issue's acceptance criteria
   - the plan's decisions, **assumed** ones especially
   - the red and green reports, and their *Departures from the plan*
   - every review's *Left for the human* and *Left for later stages*

   Note anything the record contradicts itself on.
2. **The preview.** The workflow has run `scripts/deploy.sh preview up` (its own
   `check_origin` proves the SPA and the JWKS through the Ingress) and retried a failure
   once; the `Preview:` line gives the origin or the failure. On a failure:
   - a failure the branch caused (a chart or image change) is a send-back;
   - anything else (Docker, k3d, Cloudflare) is `needs_human`.
3. **The standard pack.** `scripts/smoke.sh --out build/acceptance/standard`.
4. **The feature pack.** Write `build/acceptance/smoke/test_issue_<N>.py`: one test per
   acceptance criterion that can be seen from outside the app, each saving a screenshot
   of the state that proves it. Criteria only visible inside (a log line, a stored
   column) are mapped to the test in the branch's own suite that proves them, by name.
   Run it with `scripts/smoke.sh --out build/acceptance/feature build/acceptance/smoke`.
5. **The verdict.** Write `04-proof.md`, then return `approved`, `send_back` or
   `needs_human`.

**A rework pass** — after its own send-back has come forward again:

- the workflow has redeployed the preview (the tunnels are reused);
- rerun both packs, and the feature pack's tests for what changed;
- rewrite `04-proof.md`.

**Its summary** gives the verdict, the origin, and the criteria proven out of the total.

## 3. The smoke harness — `tests/smoke/` and `scripts/smoke.sh`

**`tests/smoke/`** is importable as `smoke.*` through the existing `pythonpath =
["tests"]`. The testkit plugin leaves paths outside `src/services` alone.

- **`smoke/fixtures.py`** — a plugin loaded with `-p smoke.fixtures`, so a pack anywhere,
  including one in `build/`, gets the same fixtures:
  - `origin` — from `--origin`, required
  - `page` — Playwright (sync), signed in through Dex as `ada@collabhub.dev`
  - `shot(name)` — a full-page screenshot to `<out>/screenshots/<test>-<name>.png`
  - `run_id` — a `smoke-<timestamp>` prefix for anything a test creates
- **Non-destructive, by rule.** It reaches the app only through the origin:
  - no database
  - no truncation
  - no Compose ports
  - nothing created without the `run_id` prefix

  It is safe against a preview someone else is using, or against k3d.
- **Never collected by a plain `uv run pytest`.** `testpaths` narrows from `tests` to
  `tests/bdd`, so only `scripts/smoke.sh`, which names its paths, runs a pack. No marker:
  `smoke` is taken (a Gherkin tag in `tests/bdd`), and nothing would select on one.
- **The standard pack**, `tests/smoke/test_platform.py` — what every deploy of CollabHub
  must do:
  - the SPA loads, with no console errors
  - the JWKS answers
  - `/api/v1/internal/` is not routable (D40): it falls through to the SPA's
    `index.html`, so it answers HTML, never a service's JSON
  - Ada signs in and lands in the shared workspace
  - a channel and a message created now are still there after a reload
  - an upload through the object-store origin returns its object

  Each test takes a screenshot where there is something to see.
- **`scripts/smoke.sh [--origin URL] [--out DIR] [paths…]`**:
  - **Flags, not environment variables** — an agent's allow-list matches a command, and
    an environment prefix turns it into another one.
  - **Defaults:** the origin from `scripts/deploy.sh preview url`, and `build/smoke/` for
    the output.
  - **Paths** are extra packs, run beside `tests/smoke`.
  - **Output:** JUnit XML and screenshots into the output directory, and a one-line
    result. It never touches `docs/test-report.md`.
  - bash 3.2, `lib/common.sh`, like the others.

  Developers and CI can run it after any deploy, not only a preview.

## 4. `04-proof.md`

Laid out for the PR to lift. Screenshot links are relative to the worktree, and resolve
only there — the PR step uploads them.

```markdown
# Issue #<N> — acceptance proof: <accepted | sent back | needs a human>

## Summary
3–5 bullets a reviewer reads first: what the feature does, as seen running.

## Try it
- Origin: <APP_ORIGIN> — sign in as ada@collabhub.dev / collabhub
- Quick-tunnel URLs die with cloudflared: `scripts/deploy.sh preview url`, or `preview up` for new ones
- Take it down: `BRANCH=feature/issue-<N> scripts/deploy.sh preview down`

## Acceptance criteria
| # | Criterion (from the issue) | Proven by | Result | Screenshot |

## Preview
Branch, commit, image tag, namespace; deploy outcome; origin checks.

## Standard smoke pack
Passed / failed / skipped; each failure and what it printed.

## Feature smoke pack
Each test: what it does, what it shows, result.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — listed by test.

## For the human
Assumed decisions, departures from the plan, and every *Left for the human* and
*Left for later stages* still open — each with where it came from.

## The run
Stages, time and cost from build/delivery/history.log.
```

## 5. Proving it

New behaviour is test-driven (D32). The red set, written and reviewed before any of the
change:

- **`.claude/delivery/loop-test.sh`**, the state machine with a fake `claude`:
  - `approved` with a proof ends the run;
  - `approved` without `04-proof.md` stops it;
  - `send_back` runs the code-writer, the code-reviewer, then acceptance again, which is
    told it is a rework pass after its own send-back;
  - `changes_requested` from acceptance stops the run;
  - a send-back past `DELIVER_MAX_SENDBACKS` stops for a human;
  - writing outside its scope stops the run.
- **Unit:** `scripts/smoke.sh`'s argument handling and origin default, through `/bin/bash`,
  as `test_preview_script.py` tests `preview.sh`.
- **Against a real stack:** the standard pack, run with `scripts/smoke.sh --origin
  http://localhost:8080` on k3d, then on a preview. It has nothing lower to prove it.
- **End to end:** one `scripts/deliver.sh` run of a small issue (007), its numbers
  recorded in a ch09 handoff.

Kept in step:

- `scripts/deliver.sh`'s header
- `.claude/delivery/agent-context.md` — the team table, the context block's new lines,
  who may send back to whom
- `CLAUDE.md`'s *Delivery workflow* — seven agents, the model line, the preview left up
- `CLAUDE.md`'s *Repo layout* and *Testing* — `tests/smoke`, `scripts/smoke.sh`
- `docs/plans/exemplar-implementation-plan.md`, if a plan should name criteria the
  acceptance-reviewer can see
