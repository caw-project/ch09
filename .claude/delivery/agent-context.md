# The delivery team — shared context for every agent

Every agent in `.claude/agents/` that `scripts/deliver.sh` runs reads this first. It holds
what is true for the whole team: who is on it, how a run works, what you may touch, how
writers and reviewers take turns, and when to stop for a human. Your own agent file holds
only what your role does. Where the two disagree, your agent file wins for your role;
`CLAUDE.md` wins over both.

## The team

One issue goes through six stages, a writer and a reviewer for each of plan, tests and
code:

| Stage | Does | Writes |
|---|---|---|
| **plan-writer** | turns the issue into an implementation plan | `docs/plans/issue-<N>/01-implementation-plan.md` |
| **plan-reviewer** | checks the plan against the issue, the exemplar and the code | its review |
| **test-writer** | builds the plan's RED tasks: the failing tests | tests |
| **test-reviewer** | checks the tests fail for the reasons the plan gives — the red gate | its review |
| **code-writer** | builds the GREEN tasks until the tests pass | code, docs the plan records |
| **code-reviewer** | checks the code against the plan, the tests and the conventions | its review |

Each stage sees the issue, the plan, the reviews and the repo — **never another agent's
conversation**. Write everything the next stage needs into the files, because nothing
else reaches it. Every stage after yours reviews too: a reviewer is the first check on
its writer's work, not the only one.

## How you are run

`scripts/deliver.sh` runs you headless, with no one watching and no one to answer a
question mid-run. You finish your work, or you stop and say exactly what a human has to
decide (see *Stopping for a human*).

Your prompt is a **context block**. The lines it can hold:

- `Issue:`, `Issue file:`, `Plan:` — the issue number, and the paths relative to the
  worktree root. The issue file is a copy, refreshed every run.
- `Worktree:` — where you are, and its branch.
- `Stage: <stage>, round <R> of <max>` — see *Rounds*.
- `Turns: <n>`, or `Final round: yes — <n> turns` — your allowance; see *The final round*.
- `Review to address:` — a writer being sent back: the review to answer.
- `Write your review to:` — a reviewer: exactly where the review goes.
- `Earlier reviews:` — every review so far, from every stage, approvals included.
- `Human answers:` — a person's answers to an earlier stop. They overrule the issue where
  they differ, and settle what they answer for every stage.

## Where you work, and what you may touch

- **Your working directory is the issue's worktree**, `../caw-issue-<N>` on
  `feature/issue-<N>`. Run commands there as they are.
- **Bash** is for the commands your stage is allowed — for most, `git`, `ls` and `wc` on
  paths inside the worktree. Read, search and list files with **Read, Grep and Glob**, by
  absolute path when they are outside the worktree; Bash can't reach those at all. `cat`,
  `sed`, `find`, `git -C`, or a `cd … &&` in front, can fall outside what you're allowed,
  and every refusal costs a turn.
- **Installed dependencies are not in the worktree.** A worktree has no `node_modules/`
  or `.venv/` of its own: find the primary checkout with `git worktree list` (the first
  line) and read its copy by absolute path.
- **Write only where your stage writes** (the table above, and your agent file). The
  workflow compares the tree before and after you run, and stops if you wrote anywhere
  else.
- **Never commit**, and never tell anyone to. The workflow checks HEAD after every stage
  and stops if it moved. Committing is the human's, always.

## What governs the work

- **The issue is the spec**, and human answers overrule it where they differ.
- **`CLAUDE.md`** — the repo's rules, including the test pyramid (D32): the failing test
  goes at the lowest layer that can prove the behaviour.
- **`docs/design/00-platform-conventions.md`** and the design doc of every service the
  work touches.
- **`docs/design/07-open-decisions-register.md`** — 🟢 is settled; 🟡 has a working
  default you may build on, saying so; **🔴 has no answer: never build on one, and never
  invent its answer.**
- **The plan**, once approved, is what the test and code stages build. A stage that
  departs from it says where and why, in its own output.

## Rounds

A writer and its reviewer take turns. The reviewer returns `approved` (on to the next
stage), `changes_requested` (back to the writer, round +1) or `needs_human`. A pair gets
`DELIVER_MAX_ROUNDS` reviews — 3 by default.

**Reviews** go in `docs/plans/issue-<N>/reviews/<reviewer>-<round>.md`, one per round, and
every verdict writes one: an approval is the record of what was checked. Findings are
numbered from 1 in each review and graded on one scale for the whole team:

- **Critical** — as it stands the work would ship a requirement wrong, break a rule in
  `CLAUDE.md` or the conventions, build on a 🔴 decision or contradict a 🟢 one, get past a
  gate with tests that prove nothing, or can't be built.
- **Major** — a hole the next stage would probably fall into: a race or edge case with no
  answer, a requirement with no test, a silent departure from the spec.
- **Minor** — wording, a stale reference, naming, presentation, a better-but-optional way.

**A writer sent back** reads every finding and changes its work in place — never starting
again from scratch. For each finding it either fixes it, or keeps its work and says why in
a **Review responses** section at the end of what it wrote: one line per finding, numbered
as the review numbers them. Nothing is skipped silently; the reviewer checks this section
first.

**A reviewer in round 2 onwards** starts from the Review responses: it checks each fix is
really there, or weighs the writer's reason for declining. It doesn't re-review untouched
work from scratch, and anything new it raises is at least major.

**A deadlock** is a finding raised before, declined by the writer with a reason, and still
held by the reviewer after weighing it. It never goes back a second time. Critical: the
reviewer stops for a human, with both positions. Major or minor: the reviewer lets it go,
records it under *Left for later stages* with both positions, and decides without it.

**Left for later stages** is how a minor finding survives an approval: the reviewer lists
it in its review, and the stages after read every earlier review (`Earlier reviews:`) and
pick up what concerns them.

## The final round

The pair's last permitted review is the **final round**, and the context block says so. It
is cut down so that a disagreement can't run on: fewer turns, less effort.

- **The writer** fixes critical and major findings with the smallest edits that do it,
  answers each minor one in Review responses with "fixed" or "left for a later stage", and
  spends no turns polishing. It re-argues a finding only if the review brought something
  new. Running short of turns, it stops editing and returns `done` with the work as it
  stands — an unfinished edit is worse than an unfixed minor finding.
- **The reviewer** may only approve or stop for a human — `changes_requested` is not
  available, and the workflow treats it as a stop. It checks the Review responses and the
  last review's critical and major findings, nothing else, and leans towards approving:
  a partly fixed major or an open minor goes under *Left for later stages* for the stages
  after, who review too. It stops for a human only over a critical finding still open, or
  a deadlock over one.

Rounds after a human has answered stay final rounds.

## Stopping for a human — `needs_human`

Stop, and return `needs_human`, when:

- the spec leaves out something you can't proceed without, and the code and docs don't
  settle it;
- the work depends on a 🔴 register decision, or contradicts the conventions or a 🟢 one;
- the issue is really several independent pieces of work;
- a finding, or a disagreement, needs a decision only a person can make — including a
  critical finding still open in the final round, or a deadlock over one.

Leave your work as it stands. Each question stands alone: what is unclear or in dispute,
where you looked, the options you can see, and what each would cost. A person answers them
in `docs/plans/issue-<N>/needs-human.md` and reruns the workflow, which resumes at your
stage — so ask everything at once. A second stop for something you could have seen the
first time wastes a round.

Running out of turns stops the workflow for a human too, with your partial work left in
place. Budget your turns: know what you'll finish with before you spend them.

## What you return

Your run ends by calling the **`StructuredOutput` tool** — every agent's `tools:` line
lists it. The workflow reads nothing else, so a JSON block in your reply is not a result.

- `status` — a writer returns `done` or `needs_human`; a reviewer returns `approved`,
  `changes_requested` or `needs_human`. Anything else stops the workflow.
- `summary` — two or three sentences for the human reading the run's log. Your agent file
  says what goes in it.
- `files` — the files you wrote, relative to the worktree root.
- `questions` — for `needs_human`, the questions as above. Empty otherwise.
