# Delivery team — handoff after the test pair

Where `scripts/deliver.sh` stands after its third and fourth agents, and what the sessions
that build the code pair need to know. Read `01-delivery-team-handoff.md` first; this
picks up where it stops.

## Where it stands

- **Merged:** `9681d59` on `feature/test-pair`, merged to main as `fa08be8`.
- **Built:** `test-writer` and `test-reviewer` (`.claude/agents/`), their `allowed_tools`,
  `write_scope` and `writer_output` entries in `scripts/deliver.sh`, and two sections in
  `.claude/delivery/agent-context.md`: *Running tests*, for every stage that runs them,
  and *Tests that prove something* — the one list of how tests here have passed without
  proving anything, which every stage that specifies, writes or reviews a test holds them
  to. The agents point to it rather than restating it; the plan-reviewer's checklist
  items 4–5 predate it and still say part of it in their own words.
- **New:** `.claude/delivery/sketch.sh` — a throwaway copy of the SPA under
  `build/sketch/`, where the test-reviewer runs the failing tests against a sketch of the
  plan's interfaces.
- **Changed:** `write_scope` is now an extended regex, because the test-writer writes in
  four places (`*.test.ts(x)`, `src/frontend/src/test/`, a service's `tests/`, `testkit`,
  `tests/bdd/`) plus its report. The plan pair's entries are anchored prefixes, as before.
- **The red report**, `docs/plans/issue-<N>/02-red-tests.md`, is the test-writer's output
  and reaches every later stage as `Red report:` in the context block.
- **A `tools:` line is an allowlist for every tool, not only `StructuredOutput`.** The
  test-reviewer's first sketching runs had no `Edit` there, so `deliver.sh` allowing it
  made no difference and every sketch was rewritten whole with Write. Check each new
  agent's `tools:` against what its prompt tells it to do.
- **Not built:** `code-writer`, `code-reviewer`. A run pauses with exit 3 at code-writer.
- **Issue 1 is at the gate, approved — and is the code pair's input.** `../caw-issue-1`,
  branch `feature/issue-1`, fast-forwarded to `fa08be8` with no commits of its own. Its
  working tree holds, uncommitted, the approved plan and all six reviews under
  `docs/plans/issue-1/`, and the approved red set from the final end-to-end run (below):
  84 Vitest tests in 9 files, the `read_state.feature` journey and its steps. Its ignored
  `build/delivery/state` says `STAGE=code-writer`, `ROUNDS_test=2`, `STEP=10`, so
  `scripts/deliver.sh docs/issues/001.md` resumes at code-writer (checked: exit 3 until
  the agent exists). The red set came from the prompts before their final clean-up, which
  moved rules without changing them.

## Decisions taken for the pair

1. **The test-writer installs; everyone after uses the worktree's own.** `npm --prefix
   src/frontend ci` (never `npm install`), and `uv run` syncs `.venv` itself. Both are
   gitignored, so the write check never sees them. Symlinking the primary checkout's
   `node_modules` was ruled out: `test.sh` would `npm ci` through the link, and the
   primary may be on another branch.
2. **No stage runs `scripts/test.sh`.** It rewrites the committed `docs/test-report.md`
   and runs whole layers. Stages run one layer and few files, with the commands in
   *Running tests*. The code-writer's final verification will need `test.sh` — decide
   then whether it may write the report, or whether that stays the human's.
3. **BDD can't run headless** — it needs the Compose test stack. The gate proves the
   feature parses (`--collect-only`) and every step binds (`--generate-missing`, which
   prints nothing when all bind), and the writer states each scenario's expected red.
   The scenario's real red is first seen by the code-writer.
4. **The reviewer sketches; the writer doesn't** (the user's call). Two of three writers
   tried a scratch implementation unprompted — one left a probe file it couldn't delete,
   one was refused by the sandbox. The writer is now told not to, and to put any probe of
   library behaviour inside the test that relies on it.

## What the variance runs taught

The plan pair's method, repeated: one approved plan (three rounds, $9.93), then three
independent test-writer runs from it, an independent comparison of the three that never
read the reviews, and the reviewer run over each.

**The red gate can't see a test that is red forever.** 52–54 of ~80 tests fail at import,
so at the gate their bodies have never run. All three writers wrote a 30-second poll test
that *no* correct build could pass (`vi.waitFor` under fake timers moves the clock 50 ms a
retry, past the 29 999 ms boundary). All three reading reviewers missed it, as they missed
a throttle test a debounce passes — and so did the approved loop run. A twenty-line
sketch found each in one run. Hence `sketch.sh`, and the reviewer's *Sketch it* section.

| Defect (runs that had it) | Reviewer v1, reading | Reviewer v2, sketching |
|---|---|---|
| Poll test can never pass (a b c) | 0 of 3 | 3 of 3, critical |
| A debounce passes the throttle tests (a b) | 0 of 2 | 2 of 2 |
| A half claimed to pin a mechanism, doesn't (b c) | 0 of 2 | 2 of 2 |
| Horizon not pinned in the component (a b c) | 3 of 3 | 3 of 3, now by a wrong-build run |
| A plan markup the test can't match (a) | — | found only by sketching |
| Disconnect test with nothing pending (b) | 0 of 1 | 0 of 1 — still reading-only |

Reviewer cost rose from $2.00–2.40 (37–49 turns) to $3.68–4.56 (79–91 turns).

Then the writer's prompt took the patterns the comparison found, stated generically, and
three fresh writers ran, each reviewed by the v2 reviewer:

| | Writers v1 | Writers v2 |
|---|---|---|
| Critical findings | 3 (the poll test, every run) | 0 |
| Major findings | 11 | 6 |
| Verdicts | 3 × changes requested | 2 × changes requested, 1 × approved |
| Stray files | 1 | 0 |
| Writer cost | $4.77–5.16 | $5.13–5.83 |

**The final end-to-end run**, through `scripts/deliver.sh` with the final prompts, from
the same approved plan: approved in round 2, $10.05 in all.

| Stage | Cost | Turns | Time | Result |
|---|---|---|---|---|
| test-writer 1 | $4.99 | 93 | 13m | 84 tests, all red as planned |
| test-reviewer 1 | $3.29 | 64 | 7m | a correct sketch turns all 84 green; a debounce sketch passes the throttle tests — 1 major, 1 minor |
| test-writer 2 | $0.70 | 21 | 1m | the second request moved to mid-window |
| test-reviewer 2 | $1.06 | 32 | 2m | re-sketched the debounce: now caught. Approved, no findings |

The first loop run, before the sketch, approved in round 2 as well ($8.69) — with the
debounce gap still in it.

**What converged, and so is probably the plan's or the tools':**
- All three writers added a test for an interface function the plan defined but never
  tested — the plan-writer should name a test for every function in its interfaces.
- All three hit a guard that passed before any code existed because TanStack notifies
  observers a tick later; all three caught it themselves. The writer's own gate works.
- Two of three noticed an imported constant is `undefined` at red, so a clock advanced by
  it advances by `NaN`. Now a writer rule.
- The plan's own badge JSX (Task 6) leaves no space between the name and the badge, so a
  `^name\b` link query can't match it — a plan defect the plan-reviewer missed, found only
  by a sketch built from the plan's markup.
- Fixtures the plan dictated ("one unread at open") made two readings coincide in every
  run. A plan's test table can bake in a vacuous fixture; the plan-reviewer's checklist
  could look for it.

**What still varies:** a writer claiming a half "pins" a library option (`cancelRefetch`)
recurred in 2 of 3 v2 runs despite the rule; a writer can't check that without a sketch,
so the reviewer is where it's caught. Severity for the same defect still varies a grade
between reviewers (major vs minor).

**After the final clean-up** — the shared rules moved into *Tests that prove something*,
and `Edit` added to the reviewer's `tools:` — one reviewer rerun over writer run c ($3.77,
97 turns) found the plan's markup defect (now critical) and the two-events helper, but
not the debounce the previous run over the same tests caught. It sketched six wrong
builds, all sound, just not that one: "each test you suspect" left the choice to the run.
*Sketch it* now says to sketch **every wrong build the Expectations named**, which the
debounce was. **That change is untested.**

**What the session cost:** about $90 — the plan run ($9.93), both end-to-end test-pair
runs ($8.69, $10.05), six writer runs and nine reviewer runs.

## For the code pair

- **Start from `../caw-issue-1` as it is**, and build the agents in a worktree of their
  own, as this pair did: copy each draft into `../caw-issue-1/.claude/agents/` (and any
  shared change into `.claude/delivery/`) to run it, then delete the copies before
  bringing the branch up to main — `git merge --ff-only` refuses to overwrite them.
- **Snapshot it before the first run — nothing durable does yet.** Tuning needs every run
  to start from the same red set, and a code-writer run changes the tree. This pair's
  snapshot lived in a session scratchpad and is gone. Either a baseline commit of the
  plan and tests on `feature/issue-1` (then `git checkout . && git clean -fd` resets it;
  that is a commit on an issue branch, so the human's call), or a tarball of
  `docs/plans/issue-1/`, the changed tests and `build/delivery/`. Either way, keep
  `build/delivery/state`: it is what makes the run resume at code-writer. `--restart`
  throws it away and starts again at plan-writer.
- **The code-writer's reach is the first real decision.** Its `write_scope` is everything
  *except* the tests and the red report — production code, the docs and ADR the plan's
  record task names, and the plan's *Found while building*. Its `allowed_tools` need
  `npm --prefix src/frontend run build` or `typecheck` and `lint` on top of the test
  pair's, and `generate:api` for an issue that changes a contract.
- **The code-writer reads the red report's *For the code-writer*** and every test review's
  *Left for later stages*. The approved issue-1 set has a list of what the tests pin that
  the plan doesn't spell out (DOM adjacency, synchronous emits, a hold that re-applies to
  every fetch). The reviewer's sketch is deleted before it returns — the code-writer
  builds from the plan.
- **It will run the BDD journey for the first time**, which needs `scripts/test.sh e2e`,
  Docker Compose and Playwright — well beyond any stage's reach so far. Decide whether
  the code-writer gets that, or whether the journey's green is the human's first-real-run
  step (plan Task 8).
- **It will write production code the lint hook checks** (`eslint --max-warnings 0`), and
  `tsc` goes green only at the last GREEN task.
- **The code-reviewer should work as the others do:** expectations from the plan and the
  tests first, written to the file, then the code. It can reuse `sketch.sh`'s idea in
  reverse: mutate the real code in a copy and see the tests catch it.
- **A code-writer must not edit a test.** If a test is wrong, that is `needs_human` or a
  finding for the code-reviewer — otherwise the red gate is undone after the fact.

## Open items

- **Python has no sketch.** A package imports its installed copy, not one under
  `build/`, so the reviewer reasons about Python wrong builds. A first backend issue will
  show whether `PYTHONPATH` over a copied service is enough.
- **Integration tests from a headless stage** start containers through testcontainers.
  Issue 1 has none, so it is untested whether Docker is reachable there; both agents stop
  for a human if it isn't.
- **The issue 1 ambiguities** in handoff 01 still stand — the plan pair settled them in
  decision rows, and the test pair built to those.
- **The variance harness isn't in the repo.** To run one stage several times from one
  input, it did, per run: `git worktree add --detach ../caw-var-<x> main`; copied in the
  approved `docs/plans/issue-1/` and `build/delivery/`, the draft agents and
  `.claude/delivery/*`; then, from that worktree, `claude -p "<the context block
  deliver.sh would print>" --agent <stage> --output-format json --json-schema
  "<RESULT_SCHEMA>" --permission-mode dontAsk --allowedTools <allowed_tools <stage>>
  --max-turns 150`. It took the tool list and schema from `deliver.sh` itself, by
  `eval`-ing its `read_only_bash` … `allowed_tools` functions, so they couldn't drift. A
  `scripts/deliver.sh --stage <name> --worktree <dir>` mode would make that one command.
- **Left for the final pass across all agents:**
  - the plan-reviewer's checklist items 4–5 restate part of *Tests that prove something*;
  - the reviewers share more than the shared file says — expectations written before the
    work is opened, "don't raise the writer's choices", and the review file's skeleton
    (findings, *Left for later stages*, *Checked and sound*). With a third reviewer coming,
    that belongs in `agent-context.md` once;
  - three lessons for the plan pair's exemplar, from *What converged* above: a test for
    every function in the interfaces, fixtures in the test table that make two readings
    coincide, and markup the plan gives that its own tests can't match;
  - `tools:` against each prompt, for every agent.
- **Leftover worktrees:** `../caw-test-pair` (merged) and `../caw-var-a`, `-b`, `-c` (the
  variance runs, detached at `fd87f7e`, their tests and reviews uncommitted) can go.
