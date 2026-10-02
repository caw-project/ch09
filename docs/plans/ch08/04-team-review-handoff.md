# Delivery team — handoff after the whole-team review

A review of every agent prompt, `scripts/deliver.sh` and the shared context, with one aim:
the team delivers an issue without stopping for a human. Read `03-code-pair-handoff.md`
first; this picks up its *Next session* list.

## Where it stands

**Not merged, not committed:** `feature/delivery-tune` · `../caw-delivery-tune`. It changes
`scripts/deliver.sh`, `.claude/delivery/agent-context.md`, `.claude/delivery/sketch.sh`, all
six agents, `docs/plans/exemplar-implementation-plan.md` and `CLAUDE.md`, and adds
`.claude/delivery/loop-test.sh` and this file.

**Four builds of issue 1 from scratch, none stopped for a human.** Each is uncommitted in
its own worktree, `../caw-issue-1-r1` … `-r4` on `feature/issue-1-r1` … `-r4`, created with
`DELIVER_RUN`. The delivery files were copied over a fresh worktree from `main` and hidden
from `git status` with `git update-index --skip-worktree`, so the agents saw a clean tree.
`../caw-issue-1`, the rerun handoff 03 describes, is untouched.

| Run | Prompts | Stages | Stage time | Cost | Loops |
|---|---|---|---|---|---|
| handoff 03's rerun | before | 16 | 95 min | $36.61 | 3 plan rounds, 1 send-back, 2 test rounds, 2 code rounds |
| r1 | revised | 12 | 85 min | $33.92 | 2 plan rounds; code-reviewer send-back (a pending read sent on a workspace switch) |
| r2 | + one turn a sketch | 14 | 74 min | $31.55 | 2 plan rounds; 2 test rounds; code-reviewer send-back (a return through an empty channel opened unread, at the top) |
| r3 | as r2 | 8 | 72 min | $30.32 | 2 plan rounds; test and code pairs approved first time |
| r4 | + examples generalised | 10 | 77 min | $33.88 | 2 plan rounds; 2 test rounds |

Average of r1–r4: 77 minutes, $32.42. r2 and r3 ran at the same time on one machine. Every
build: lint, unit and e2e 20/20 green in its committed report; Vitest and the typecheck
rerun by hand on r2, r3 and r4 after the run (210, 223 and 230 tests, clean).

## What changed

**`scripts/deliver.sh`**

- *A reviewer's own round* (handoff 03, item 1). A reviewer that sends back has its pair's
  round advanced, so its next review is a new file, and its review is handed to its own
  writer as `Review to address:` when the flow comes forward.
- *A send-back never lands in a final round.* Each pair keeps its own final round as state
  (`FINAL_<pair>`); a send-back moves it out so an ordinary review and a final one are always
  ahead. What bounds send-backs is a count, `DELIVER_MAX_SENDBACKS` (3 a pair).
- *Scoped passes.* A snapshot at each send-back gives every later stage
  `Changed since the send-back by <stage>:`. Several send-backs can be open at once.
- *Turn caps by stage* (item 2): first pass 150 (plan pair), 200 (test-writer), 250 (the
  rest); `DELIVER_REWORK_MAX_TURNS` 100; final round 60. The context block says
  `Rework pass: yes` on a pass that answers a review or follows a send-back.
- *Out of turns is resumed once*, in the same session (`--resume`), with half as many turns
  again; a stage that dies without a result is rerun once. Checked against the real CLI.
  Neither happened in r1–r4.
- *`history.log` carries time, turns and cost* for every step, and the run prints them at
  the end (item 4's first step).
- *`DELIVER_RUN=<name>`* builds the same issue again in `../caw-issue-<N>-<name>`.
- *Reach.* Writers may `rm` inside their scope; the code-writer may `uv add`, `uv lock` and
  `npm install <pkg>`, and write `pyproject.toml`, `uv.lock`, `ruff.toml`, `README.md` and
  `.github/`; the code pair may run `ruff check`, `helm lint`, `helm template` and
  `bash -n`; the plan-reviewer has Edit, for its own review.

**`.claude/delivery/loop-test.sh`** — the stub loop, now in the repo: a fake `claude` and 13
scenarios over rounds, both kinds of send-back, nested send-backs, the send-back limit,
out-of-turns and a crash. Run it after any change to `deliver.sh`.

**`.claude/delivery/sketch.sh`** — `service <name>` and `pytest <paths>` copy a Python
service under `build/sketch/services/` and run its tests against the copy (the copies go
first on `PYTHONPATH`). `reset <path>` puts one file back. Tried by hand on `messaging`: a
mutant in the copy failed 7 unit tests. **No delivery has used it.**

**The shared context and the prompts**

- *Decide, record, carry on.* A gap in the issue is settled from what is written, then by
  the best-fitting reading, and recorded: an **assumed** decision row in the plan, a
  departure in a report, *Left for the human* in a review. `needs_human` is kept for a 🔴
  dependency, a hard-to-undo choice with nothing written to favour a side, a broken
  environment, and a critical finding deadlocked in the final round. The plans recorded
  8–13 assumed decisions each.
- *A fault further back is a send-back, not a stop* — a code stage that finds the plan wrong
  says so in its send-back, and the test pair passes it on.
- *A rework pass*, *Spend turns well* (batch independent calls; read once), *a failure your
  work can't have caused* (rerun once, record, carry on), and `CLAUDE.md` not read again —
  it is already in context.
- *The plan-writer checks its plan before returning* against what plan-reviewers have sent
  plans back for, including handoff 02's three lessons; the plan-reviewer has them as item
  12. The verification task names the `scripts/test.sh` layers the change reaches, each run
  once, e2e unfiltered.
- *Reviewers:* raise everything in round 1; one turn a sketch or mutant (the Edit, then the
  run); Python sketches and mutants.
- *Examples generalised.* The plan-reviewer's checklist items 2, 3, 6, 7 and 8 and two
  phrases in the code-reviewer were worded from issue 1's own faults ("on focus", "fixed at
  open", "a return visit"). They now name the class. r4 ran with them and delivered.

## What the runs showed

- **The plan pair always takes two rounds**, and round 1 finds something different each
  time: a divider that a cache write could trigger early (r1), a pending read sent on a
  workspace switch (r2, r4), a journey step no build could pass (r3).
- **The code-reviewer's send-backs were real bugs**, each fixed test-first in 8–9 minutes of
  rework across four passes.
- **The test-reviewer is the dearest stage**: $4.12–7.13 and 105–175 turns, sketching 26–30
  wrong builds. One turn a sketch cut its cost, not its turns.
- **Rework passes are short**: 1.3–5.6 minutes, 19–85 turns.

## The control: a plain session, and a blind review

Asked whether the team beats a plain Claude Code session given the same issue. Three plain
headless sessions (Opus) each built issue 1 in a repo with no trace of the team: an export of
`main` with the agents, `.claude/delivery/`, `deliver.sh`, the `issue-writer` skill, both
exemplars and `docs/plans/ch08/` removed, one commit, outside `~/scm/manning`. None read
anything outside its repo. Then a fresh judge per build — seven of them, each given only the
issue and the SPA's source and tests under a shuffled label — gave a verdict on the same 15
rows (the issue's six *Where the rules meet* bullets and nine *Paths* rows), each proved by a
probe test it wrote and ran.

| | Team (r1–r4) | Plain session (c1–c3) |
|---|---|---|
| Rows holding, of 15 | 14 in every build | 14 in every build |
| Row broken | M3 in every build | M3 in every build |
| Time | 72–85 min | 20–30 min |
| Cost | $30–34 | $6.50–7.39 |
| Production code | about 805 lines | about 795 lines |
| Test code | about 2,390 lines | about 1,510 lines |

- **No difference in measured correctness**, at about a fifth of the cost. All seven builds
  have the same bug: a message that arrives while a channel's opening fetches are in flight
  gets a "New messages" divider. The issue asks for the divider both to wait for those
  fetches and never to appear for a live message; no stage of any team run caught it.
- **The team writes about 60% more test code.** The judges called all four team suites strong;
  two of the three plain suites test the pieces alone and never wired together.
- **Limits:** one judge a build, 15 rows, one SPA-only feature, a spec already hardened by the
  team's earlier failures. "No difference detected", not "no difference exists".
- The control repos are in `~/scm/caw-control/`, the judges' copies and results in
  `~/scm/caw-judge/`; neither is durable.

Where the conversation went from there, none of it built: the team's value may be the board
and the artifacts rather than the code; a single builder session driven phase by phase from
outside, with one independent reviewer after it, might keep both at a third of the cost; and
in CI the durable state has to be the issue branch, not a session on a runner.

## Open

0. **Is the six-stage team worth its cost?** Run both from a weaker spec — issue 1's wording
   before `issue-writer` — and on a backend issue. Fix the issue's M3 contradiction first.

1. **A backend issue.** Issue 1 is SPA-only and is the only issue the team has run. Python
   sketches, integration tests from a headless stage, a migration and a dependency install
   are in the script and the prompts and unproven by a delivery.
2. **The Integration row.** Every build's committed report says "not run" where `main`'s says
   381 passed: a fresh worktree has no integration results and an SPA-only plan doesn't name
   the layer. The code-reviewer leaves it for the human. Decide: always `all`, a
   `testkit.report` that keeps the committed row, or the human reruns it.
3. **Handoff 03's R4 question** (an error ack, then a reconnect) is still undecided. Each
   build now settles it as an assumption, so the four may differ.
4. **Model and effort per stage** are untried: every stage is Opus at default effort.
5. **The code-reviewer's falsification by subagent** (handoff 03, item 3) — not tried.
6. **What the three reviewers share** is still in three files (handoff 02's final pass).
7. **`App.test.tsx`'s intermittent failure** didn't show in four runs; the flaky-test rule is
   there for when it does.
8. **Worktrees to remove:** `../caw-issue-1-r1` … `-r4` and their branches, once one build is
   chosen for review or none is; and the older ones handoff 03 lists.
