# Delivery team — handoff after the plan pair

Where `scripts/deliver.sh` stands after building its first two agents, and what the
sessions that build the other four need to know that the repo doesn't already say.

## Where it stands

- **Built and merged:** `plan-writer` and `plan-reviewer` (`.claude/agents/`), the shared
  context every agent reads first (`.claude/delivery/agent-context.md`), and the workflow's
  round limits (`scripts/deliver.sh`, merge `402a5b4`).
- **Not built:** `test-writer`, `test-reviewer`, `code-writer`, `code-reviewer`. A run
  pauses with exit 3 at the first missing one, and resumes there once it exists.
- **The test issue:** `docs/issues/001.md` — unread counts and read markers in the SPA.
  Frontend only, with the backend already built (D31), so a whole run exercises
  planning, Vitest, one BDD journey and doc updates without a migration.
  `scripts/deliver.sh docs/issues/001.md` starts it in `../caw-issue-1` on
  `feature/issue-1`.

## What each new agent needs

Every one of these was a failed run before it was a rule.

1. **`StructuredOutput` in its `tools:` line.** `--json-schema` returns its result through
   that tool, and an agent's `tools:` is an allowlist that drops it. Without it the agent
   prints its JSON as text and the stage dies with "returned no structured result".
2. **An `allowed_tools` entry in `deliver.sh`.** In `dontAsk` mode anything not listed is
   refused; with no entry the script stops with "no tools are allowed for <stage> yet".
   The test and code writers will need more than the plan pair's read-only set — `npm`,
   `uv run pytest`, `scripts/test.sh` — so decide each one's reach deliberately.
3. **A `write_scope`**, where one applies, and a `writer_output` for a writer. The script
   compares the tree before and after and stops on a write outside the scope.
4. **Only its role in its own file.** Everything two agents share goes in
   `agent-context.md` (CLAUDE.md, *Delivery workflow*). Start the file with the step that
   reads it, as the plan agents do.

Bash in a headless stage **can't reach paths outside the worktree**, and read-only
commands inside it (`cat`, `sed`, `grep`) are let through whether listed or not. A
worktree has no `node_modules/` or `.venv/`: agents read those from the primary checkout
by absolute path with Read and Grep. A stage that has to *run* the frontend or Python
tests needs dependencies in the worktree itself — that is new ground for the test-writer,
and the first thing to settle.

## How to test an agent

- **The loop first, with a stub.** A fake `claude` on `PATH` that logs its arguments and
  returns scripted verdicts proves the state machine — rounds, final-round flags, exit
  codes, `needs_human` — in seconds and for nothing. Four scenarios covered it: three
  rounds of changes, resuming after human answers, approval in round 2, and running out
  of turns.
- **Then real runs from a fixed input.** Reset the worktree to the same starting state for
  each run — the plan pair used the same plan every time — so differences come from the
  prompt, not the input. Change one thing per run and compare findings in a table.
- **Read the transcript, not just the result.** `session_id` in the stage's JSON under
  `build/delivery/` finds it in `~/.claude/projects/<worktree-path>/`. It showed what no
  result could: that the reviewer fetched the issue and the plan in one batch, and so
  never formed a view before seeing the plan.

## What the plan pair taught

- **Plans vary between runs in substance, not just names.** Three plan-writer runs of the
  same issue shared a skeleton but differed on about a third of their own decisions, and
  each had a real defect the others didn't. The reviewer, not the writer, is where
  consistency comes from.
- **A reviewer anchors on what it reads.** Three reviewer runs that read the plan straight
  after the issue all marked the throttle requirement "covered" in the plan's words, and
  missed that it contradicted the issue. Having the reviewer write its expectations into
  the review file — as questions, from the issue alone — before opening the plan caught
  it, and everything the earlier runs caught as well. The test-reviewer and
  code-reviewer should work the same way: expectations from the plan first, then the
  tests or the code.
- **Name the checklist from real failures.** The plan-reviewer's checklist items come from
  defects the three plans actually had — library defaults assumed, guard tests green
  before the code, wrong expected reds, cache races, state "captured once" but
  recomputed, amplified error paths. Generic review advice found none of them.
- **Keep examples off the test issue.** An example in a prompt drawn from issue 1 primes
  the agent with issue 1's answer and makes the next run a worthless test.
- **The final round works.** Run 4 used all three rounds: the writer's third pass took
  20 of its 40 turns, the reviewer's 13, and it approved with minor findings passed on.

Run 4, the reference run: review 1 raised five majors and two minors in 50 turns ($2.27);
the full three rounds cost $7.37. Its plan and reviews are not in the repo — rerun issue 1
to get a fresh set.

## Open items

- **The issue is ambiguous in two places**, and every plan run hit both:
  - *Decided already* 4 says "trailing edge", while requirement 3 describes sending the
    latest id when the window ends — every plan read that as leading **and** trailing.
    Say which is meant.
  - Requirement 7's divider rule admits a live message arriving after open, against
    "fixed at open-time" and decision 9's "no new-messages indicator".
  - It also cites the D31 ADR's stale lines as 94–99; they are 96–99.
- **For the test-writer:** plan reviews end with *Left for later stages* — minor findings
  meant for the test and code pairs. The agent must read them (`Earlier reviews:` in its
  context block) and act on what concerns it.
- **The red gate under the workflow:** CLAUDE.md says the test-reviewer's approval is the
  review that an interactive session gets by stopping at red. Its prompt has to make that
  real — run the tests and check each fails for the reason the plan gives.
