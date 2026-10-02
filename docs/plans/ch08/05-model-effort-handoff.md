# Delivery team — handoff after the model and effort runs

Handoff 04's open item 4: every stage ran on Opus at default effort, and nobody had tried
anything else. This is what was tried, what it showed, and what the team runs on now. Read
`04-team-review-handoff.md` first.

## Where it stands

**The team's models, hard-coded in `scripts/deliver.sh` (`default_model`) and in each
agent's `model:` line:**

| Stage | Model | Effort |
|---|---|---|
| plan-writer, plan-reviewer | Opus | default |
| test-writer, test-reviewer | Sonnet | default |
| code-writer | Sonnet | default |
| code-reviewer | Opus | default |

A rework pass runs on the same model and effort as a first pass. The final round keeps
medium effort, as before. Hard-coded for now: it may come to depend on the issue's
complexity as the team evolves.

**Three builds of issue 1 on that configuration, none stopped for a human:**

| Run | Stages | Stage time | Cost | Loops | Blind judge, of 15 |
|---|---|---|---|---|---|
| p3 | 10 | 55.3 min | $19.81 | 2 plan rounds, 2 test rounds | 14 |
| q1 | 14 | 62.4 min | $21.52 | the same, and a code-reviewer send-back | 14 |
| q2 | 10 | 63.8 min | $22.42 | 2 plan rounds, 2 test rounds | 14 |
| **Average** | | **60.5 min** | **$21.25** | | |
| All Opus (r1–r4 and f2) | 8–14 | 72–85 min, average 77 | $30–34, average $32 | | 14 in each of r1–r4 |

About a fifth less time and a third less cost, with no difference a blind judge could find.
The slowest of the three is faster than the fastest all-Opus run. The row every build
breaks is M3, as in handoff 04.

## What changed

**`scripts/deliver.sh`**

- *A model and an effort for each stage.* `default_model` gives the table above;
  `DELIVER_MODEL_<STAGE>` overrides one stage, `DELIVER_MODEL` every stage.
  `DELIVER_EFFORT` and `DELIVER_EFFORT_<STAGE>` set a first pass's effort; nothing is set
  by default.
- *A rework pass can have its own.* `DELIVER_REWORK_MODEL` and `DELIVER_REWORK_EFFORT`
  apply to a pass that answers a review or follows a send-back. Unset by default. The final
  round keeps `DELIVER_FINAL_EFFORT` whatever the rework effort is.
- *`history.log` says what each step ran with* — `[7.8m 77 turns $1.74 · sonnet · default]`
  — and so does the stage's line in the run's output.

**`.claude/agents/`** — `model: sonnet` in test-writer, test-reviewer and code-writer, so a
stage run by hand uses what the workflow does.

**`.claude/delivery/loop-test.sh`** — the fake `claude` records `--model` and `--effort`;
five new scenarios (19 in all) over a stage's own setting, the defaults, `DELIVER_MODEL`
over everything, the rework model and effort, the final round's effort winning, and a
resume keeping its flags.

## The runs

Fourteen builds of issue 1 in a day, each in `../caw-issue-1-<run>` on
`feature/issue-1-<run>`, uncommitted, run from this branch's `deliver.sh` with the agents
as they were on `main`. Up to five ran at once. Every one delivered without a human. Each
was judged blind as in handoff 04 — a fresh Opus session given only the issue and the
SPA, a verdict on the same 15 rows, each proved by a probe it wrote — under labels
`b8`–`b22` in `~/scm/caw-judge/`.

| Run | Sonnet stages | Other change | Stages | Time | Cost | Judge |
|---|---|---|---|---|---|---|
| f2 | — | — | 10 | 77.7 min | $30.32 | not judged |
| m2 | — | Opus writers at medium effort | 17 | 95.4 min | $38.53 | 14 |
| m3 | — | plan-writer at xhigh effort | 13 | 100.7 min | $36.53 | 14 |
| p1 | code-writer | — | 10 | 81.9 min | $31.17 | 14 |
| m1 | test-writer, code-writer | rework at high effort | 16 | 80.2 min | $30.30 | 14 |
| n1 | test-writer, code-writer | Opus for rework | 10 | 71.7 min | $26.17 | 15, then 14 |
| n2 | test-writer, code-writer | Opus test-reviewer at medium | 10 | 65.8 min | $23.32 | 14 |
| f1 | test-writer, code-writer | — | 16 | 90.1 min | $30.50 | 14 |
| p2 | test-writer, code-writer | test-writer at high effort | 12 | 70.7 min | $25.12 | 14 |
| n3 | plan-writer, test-writer, code-writer | — | 19 | 78.0 min | $26.39 | 12, then 12 |
| p3, q1, q2 | test pair, code-writer | — | 10–14 | 55–64 min | $20–22 | 14 each |
| q3 | test pair, code pair | — | 10 | 58.4 min | $20.01 | 14 |

f1 and f2 were started as fast-mode runs; fast mode never took effect (below), so they are
plain repeats. p1 and p2 were interrupted by the account's session limit and resumed; the
interrupted attempts (3 minutes, $1.95) are left out of their figures and kept in
`build/delivery/limit/`.

## What the runs showed

**Models**

- **A Sonnet code-writer is faster and under half the cost**: a first pass of 6.5–9.3
  minutes and $1.74–2.31 over ten runs, against 9.8–13.4 minutes and $3.98–5.82 for Opus.
- **A Sonnet test-writer alone is cheaper, not faster.** Its first pass saves about $2 and
  a minute or two, but at default effort its tests went back for a second round every time, and with an Opus
  test-reviewer each round is dear. Five such runs averaged 76 minutes — the baseline.
- **The test pair is where the time is, and both halves have to move.** With an Opus
  reviewer the pair takes 25–42 minutes and $9.50–17; all Sonnet, 18–26 minutes and $6–8.50.
  The Sonnet test-reviewer is not a soft gate: it sent the tests back in all four first
  reviews, sketching a plan-faithful build and wrong ones as the Opus reviewer does.
- **Loops get cheap.** q1 took a code-reviewer send-back — a new test, its review, the fix
  and the re-review — in 5 minutes and $1.69, and still beat every all-Opus run.
- **A Sonnet plan-writer builds a weaker design.** n3's plan kept one divider capture a
  visit; two judges each found the same three rows broken (M2, M3, P2). It saved $3.
- **A Sonnet code-reviewer does less.** q3's ran 4 mutants in 3.2 minutes, where Opus runs
  7–19 in 6–11. Its build was judged sound, but the Opus code-reviewer sent work back five
  times across these runs for real bugs. Not tested: whether Sonnet would find those.
- **An Opus test-writer with a Sonnet code-writer (p1) gained nothing** — its test pair
  alone took 42 minutes.

**Effort** — nothing tried saved time or improved a build.

| Tried | Result |
|---|---|
| Opus writers at medium (m2) | first passes at or above the default range |
| plan-writer at xhigh (m3) | 25 minutes for the first pass, not 10; still two plan rounds |
| Opus test-reviewer at medium (n2) | 11.6 minutes, inside the default range |
| Sonnet test-writer at high (p2) | 19 minutes, not 12; approved in one round, then a send-back |
| high effort on rework (m1, m2) | rework passes as long as at default; one still rejected |
| Opus for a Sonnet writer's rework (n1) | twice the time and cost of Sonnet's, accepted the same |

Rework passes are 1–5 minutes and nearly always accepted as they are, so there is little
for more effort to buy. Small samples: "no benefit seen", not "none exists". What the
default effort of a headless run is was never established — the CLI doesn't report it.

**The host doesn't matter.** 85–97% of a run's stage time is the model's; the machine's
share is 2–13 minutes of tests and builds, and it was no longer with five runs at once.

**Fast mode didn't take effect.** With `fastMode` in `--settings` a headless result says
fast mode is on and its usage says `speed: standard`; the beta header is refused for a
subscription login. Dropped.

**What recurs, whatever the models**

- **The plan pair took two rounds in every run** (three in m2, n3 and f2).
- **The code-reviewer's send-backs were real bugs.** A read waiting in its window sent on
  the old socket at a workspace switch: m1, n3, f1 (and r1 before them). A divider capture
  kept across a quick channel bounce: p2. A hold released at unmount: q1.
- **A plan gave a test helper to the code-writer** (`test/render.tsx`, m2 and m3), who may
  not write it: a send-back each time, and r3 before them left it as dead code.
- **M3 is the issue's, not a model's.** Every plan settles "existed when the channel was
  opened" as "loaded when the opening fetches settled", every later stage holds the build
  to the plan, and the judge reads the issue's line literally. n2's code-reviewer saw it and
  filed it as minor, because the plan had decided it.
- **Judges disagree.** Two on n1 gave 15 and 14; a read held across a disconnect was
  called major twice and minor twice. One judge a build shows parity, not much more.

## Open

1. **Other issues.** Everything here is issue 1, SPA-only. The model table is unproven on
   a backend issue, and on a harder one — where it may want to follow the issue's
   complexity. Handoff 04's item 1 stands.
2. **A usage limit is treated as a crash.** `deliver.sh` reran the stage after 30 seconds
   and exited 1. It should stop as paused and say when to rerun; rerunning the same command
   does resume at the interrupted stage.
3. **The plan pair's second round**, the largest fixed cost left: 5–10 minutes a run.
4. **Two gaps in issue 1** to settle before it is a baseline again: M3 (what "existed at
   open" is measured against), and whether a read held in its window survives a disconnect
   — judges reported it on n1, f1, p2 and q3.
5. **An assumed decision that contradicts a line of the issue** passes the plan-reviewer
   as a reasonable reading. Should it be a major finding?
6. **The plan-writer's checklist**: a change under `src/frontend/src/test/` belongs to a
   RED task, never a GREEN one.
7. **A Sonnet code-reviewer**, tested fairly: give it the builds Opus sent back.
8. **Worktrees to remove**: `../caw-issue-1-m1` … `-m3`, `-n1` … `-n3`, `-f1`, `-f2`,
   `-p1` … `-p3`, `-q1` … `-q3` and their branches; the judges' copies `b8`–`b22` in
   `~/scm/caw-judge/`; and handoff 04's list.
