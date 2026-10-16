# The delivery runner commits and pushes its own branch

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

`scripts/deliver.sh` takes one issue through seven agents in a worktree on `feature/<key>`, and
until now it committed nothing: CLAUDE.md's *Never commit* held for every session, the
delivery included, and a person committed the finished branch. The run's progress lived in
`build/delivery/` — `state.json`, `history.log`, the send-back snapshots — which git ignores.
That worked because a delivery ran on a laptop whose disk outlived it: a stop for a human left
`needs-human.md` and the state where the person would answer them, and a rerun picked up
from there.

The next step is to run the same delivery from GitHub Actions, on a hosted runner, so an issue
can be delivered without anyone's machine. A hosted runner's disk dies with its job. A run
that stops for a human, fails, or finishes would take its state, its questions and all its
work with it, unless they are somewhere the next job can reach. The job is also killed at six
hours wherever it is, and the longest finished run so far took about 101 minutes on a laptop
— a large feature on a slower runner could reach the limit. Whatever survives the job has to
survive that kill too, and a person has to be able to answer a stop from GitHub, not only
from the terminal that started it.

## Decision

The delivery runner commits and pushes its own branch. It is the one exception to *Never
commit*, and it belongs to the runner alone: no agent commits, and the check after every stage
that HEAD hasn't moved still stops a run whose agent did. A person's session still never
commits.

The runner commits everything outside `build/` after every stage that finishes —
`delivery(<key>): <stage> <result>, round <R>`, with the stage's summary as the body — and at
a stop for a human (`needs a human at <stage>, round <R>`), on a failure (`failed at <stage>,
round <R>`, the error as the body) and at the acceptance-reviewer's approval (`accepted`). The
author is whoever git is configured as: the developer locally, `github-actions[bot]` in the
workflow. Run state moves into the plan dir, `docs/plans/<key>/run/`, so it is committed with
the branch; transcripts stay in the ignored `build/delivery/`. Snapshots of what a stage wrote
are taken against the branch's base rather than against what is uncommitted, so the runner's
own checkpoints don't make committed files look changed.

Each commit is pushed. The remote follows the issue's backend: `origin` for a `gh-` key, so a
GitHub issue's branch is on GitHub where its stop can be answered, and `forge` for an `issue-`
key. `DELIVER_REMOTE` overrides it, and `DELIVER_PUSH=0` commits without fetching or pushing,
which the loop test uses. Every run fetches first and brings the branch level: a branch only
on the remote is tracked, one the remote is ahead of is fast-forwarded, which is how an answer
committed on GitHub reaches the run. A branch that has diverged, or a worktree with uncommitted
changes while the remote is ahead, stops the run before any stage. Nothing is ever merged or
forced: a push the remote rejects stops the run with exit 1, naming both commits.

`DELIVER_DEADLINE` gives a run a deadline in epoch seconds. No stage starts with less than
`DELIVER_DEADLINE_MARGIN` minutes left (75 by default, the longest stage plus a deploy), so a
run ends at a checkpoint with exit 4, "run again to continue", before the job's limit can kill
it in the middle of a stage. `.github/workflows/deliver.yml` runs the same
`scripts/deliver.sh` on a hosted runner, sets the deadline 5½ hours into the job, and is
dispatched again with the same key to resume.

## Consequences

A delivery no longer depends on the machine that ran it. A stop can be answered on GitHub by
editing `needs-human.md` on the branch and dispatching the workflow again, or on a laptop that
fetches the branch; a run that ran out of time continues from its last checkpoint anywhere.
The branch is also a readable record of the run: one commit per stage, in order, with what
each stage said it did.

The cost is noise and a new failure mode. A delivery's branch carries ten or more runner
commits, which a squash merge removes but a plain merge keeps. Every stage now ends with a
push, so a remote that is unreachable or refuses the push stops the run where it used to carry
on — on purpose, because a run that can't push on a hosted runner is a run that will lose its
work. Someone pushing to a delivery's branch while it runs makes the next checkpoint's push
fail; the workflow uploads a git bundle so those commits can be recovered by hand.

Committing the run's state means `state.json`, `history.log` and the snapshots land in the
repo with the plan, and agents must not write to `docs/plans/<key>/run/`. The write check
ignores that folder as it ignores `build/`, so the rule is held by `agent-context.md`, not
enforced. A stage killed by the job's limit, rather than ended by the deadline, loses that
stage's work, but only that stage's: the next run reruns it from the last checkpoint.

Local runs change too. They now push to `forge` after every stage unless `DELIVER_PUSH=0`,
which also means a local run fetches first and stops on a branch someone else moved.

## Alternatives Considered

### Commit only at stops and at the approval

The first plan (handoff 07). It keeps the branch's history short, but a run killed by the
job's six-hour limit has reached neither, so its state and every stage's work are lost and the
next dispatch starts from nothing. Checkpointing after every stage costs a commit per stage and
loses at most one stage.

### Keep the state out of git and upload it as an Actions artifact

It keeps the branch clean, but an artifact belongs to one workflow run: the next run must find
and download it, a laptop can't resume from it without the same plumbing, and a person can't
answer `needs-human.md` by editing a file on the branch. The branch is already shared between
every place a delivery can run; putting the state on it needs no second channel.

### Let the agents commit

The code-writer and the others could commit their own work as they go. That removes the
runner's check that HEAD hasn't moved, which is what catches an agent doing something to the
branch it shouldn't, and spreads the commit rules across seven prompts instead of one place in
the runner.

### Dispatch the workflow again automatically on exit 4

`GITHUB_TOKEN` may trigger `workflow_dispatch`, so an out-of-time run could chain the next one
itself. That spends model time with nobody watching, and a delivery stuck in a loop could run
for days before anyone looked. For now a person dispatches it again; an automatic chain with a
hard cap can come later if long deliveries are common.

### Force-push, or merge, when the branch has diverged

Either would let a run carry on where it now stops. A force-push can throw away an answer a
person pushed, and a merge puts a conflict in front of an agent that can't ask about it. A
divergence is rare and always means two people, or two machines, worked the branch at once:
that is a person's to sort out.
