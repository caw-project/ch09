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
| **test-writer** | builds the plan's RED tasks: the failing tests | tests, and `docs/plans/issue-<N>/02-red-tests.md` |
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
- `Red report:` — from the test pair on: the test-writer's account of every failing
  test, what it fails with, and where the tests depart from the plan.
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
- **Installed dependencies start out missing.** A new worktree has no `node_modules/` or
  `.venv/` of its own. A stage that only reads finds the primary checkout with
  `git worktree list` (the first line) and reads its copy by absolute path. A stage that
  runs tests uses the worktree's own, which the test-writer installs (see *Running
  tests*) — never the primary checkout's, which may be a different branch's.
- **Write only where your stage writes** (the table above, and your agent file). The
  workflow compares the tree before and after you run, and stops if you wrote anywhere
  else.
- **Never commit**, and never tell anyone to. The workflow checks HEAD after every stage
  and stops if it moved. Committing is the human's, always.

## Running tests

The test and code stages run tests, and always the same way: from the worktree root, one
layer and as few files as prove the point.

| Layer | Command |
|---|---|
| Vitest | `npm --prefix src/frontend test -- <paths relative to src/frontend>` |
| Types | `npm --prefix src/frontend run typecheck` |
| Python unit or integration | `uv run pytest <paths>` — the directory decides the layer |
| BDD | cannot run here: it needs the Compose test stack. `uv run pytest tests/bdd --collect-only -q` proves the features parse; `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` prints a stub for every step with no definition, and nothing when all bind |

- **Install before the first run**, if the worktree has none: `npm --prefix src/frontend ci`
  (never `npm install`, which rewrites the lockfile); `uv run` syncs `.venv` by itself.
  The lint hook skips TypeScript until `node_modules/` exists, so install before writing
  a `.ts` file.
- **Never `scripts/test.sh`.** It rewrites the committed `docs/test-report.md`, which no
  stage writes, and runs whole layers.
- **Integration tests start their own containers** through testcontainers. If Docker is
  unreachable, nothing at that layer has run — not a test failure, and not a pass: stop
  for a human. (BDD is different: it never runs here, by design.)
- **Read the failure, not the count.** A file that fails to load reports its tests as
  failed without running one; `Failed to resolve import` and `ImportError` are load
  failures, `is not a function` and an assertion are the test running. A load failure is
  right only when every test in the file needs the missing module; otherwise it hides
  tests that would really run — import what exists, and let the missing export fail its
  own tests.

## Tests that prove something

Every stage that specifies, writes or reviews a test holds it to these. Each is a test
that once passed, or stayed red, without proving the behaviour it was named for — so for
every test, name the wrong build it must fail, and check that it would:

- **A guard proves its positive too.** "Does not X" passes when nothing ever does X: the
  same test shows the path that *does* X under the neighbouring condition, or asserts
  what happens instead.
- **A negative case passes every earlier guard,** so only the rule under test can stop it.
  A private-channel search test once passed because the user could see no channels at all
  and the code returned before any filter ran. A 404 before a route exists passes a
  "can't see it" test: assert the Problem `detail`.
- **A fixture where two readings coincide proves neither** — the oldest match for the
  newest, a strict bound for an inclusive one, a timer restarted for one kept. Two
  candidates, not one; events spread over time, not all at one instant; a value past the
  boundary as well as on it; state that differs before and after.
- **Each input on its own.** A rule with several inputs gets each flipped alone, the
  others held true; a helper that always changes two together hides a build that listens
  to one. A test named "and nothing is left over" needs something pending when it happens.
- **Both sides of every boundary**, and both directions of a comparison. jsdom has no
  layout — every scroll and size reads 0 — so geometry code needs its dimensions stubbed
  (`MessageList.test.tsx`'s `giveLayout()`), one test per direction; a missing
  `clientHeight` once passed every test there was. In fake time, the instant before and
  the instant after (the 4999 ms and 1 ms pair in `useMessages.test.ts`).
- **Clocks.** Fake only the clock you need (`vi.useFakeTimers({ toFake: [...] })`, as
  `session.test.ts` does), advance with `advanceTimersByTimeAsync` inside `act`, and let
  no timeout or background loop quietly repair what the test pins — a 1-second reclaim
  once hid a missing `XACK`. No `vi.waitFor` under fake timers near a boundary: each
  retry moves the clock on, past the instant pinned.
- **Nothing from a missing module drives the test.** An import that doesn't exist yet is
  `undefined` at red: a clock advanced by an imported constant advances by `NaN`, and the
  half that expects nothing to happen passes for that reason alone. Use the plan's value
  as a literal.
- **Events where the library listens.** Check the installed source for the target and
  whether it expects the event to bubble; an event it never hears makes a "reacts to X"
  half pass or fail for the wrong reason.
- **Races in both orders.** An event arriving during an in-flight fetch is held with a
  deferred response (`holdHistoryFetch()` in `useMessages.test.ts`) and proven to survive;
  a response and its echo give the same state either way round; a path that spends a
  one-time resource is called twice at once. Readiness is the server's ack, not a
  connected socket.
- **Wait on the last effect, not the first.** A negative assertion comes after the thing
  could have happened, anchored to a positive event: "nothing was sent", checked
  synchronously against something recorded asynchronously, can't fail.
- **Pin what the plan pins, and no more.** DOM shape, call order and timing the plan
  leaves open belong to the code; a test that fixes them fails a correct build.
- **The real code, not a copy.** No fixture that restates a production mapping
  (`testkit.search` seeds with the Worker's own handlers for this reason), no mock of the
  unit under test, never a faked database session — pull the rule into a pure function,
  or prove it at integration (CLAUDE.md).
- **Dependency down.** An external call gets its documented fail-open or fail-closed
  answer tested, not only the happy path.
- **One layer per rule** (D32). Grep for an existing test of the same rule: a rule proven
  lower down gets no scenario, and a route's rule gets one integration test.
- **The journey proves the server.** Phrases from
  `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` verbatim, `@bdd` on the Feature line
  only, page-object answers through retrying `expect`. The last `Then` shows what the
  server holds — a reload, the other user's window, the confirmed row, not the optimistic
  one. A recovery scenario breaks something first, or it passes with nothing recovered.

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
