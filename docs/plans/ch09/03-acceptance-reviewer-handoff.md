# Acceptance reviewer — handoff

The delivery team gains a seventh agent, the acceptance-reviewer. It deploys the build to
the branch's preview, proves it there in a browser, and writes the proof a human accepts
from. This is what was built, what two real issues showed, and what the next step needs:
moving the workflow to GitHub, where the same agent opens the PR. Read
`01-acceptance-reviewer-design.md` for the design and `ch08/05-model-effort-handoff.md` for
the team before it.

## Where it stands

```
plan-writer → plan-reviewer → test-writer → test-reviewer → code-writer → code-reviewer
  → acceptance-reviewer → done
```

| | |
|---|---|
| Model | Sonnet, default effort, 200 turns on a first pass |
| Returns | `approved`, `send_back` (to the code-writer), `needs_human`. Never `changes_requested`: it has no writer |
| Writes | `docs/plans/issue-<N>/04-proof.md`, and its own send-back file. Nothing else tracked |
| Runs | `scripts/smoke.sh`, `scripts/deploy.sh preview url`, read-only git |
| Leaves | the preview running, for the human |
| Cost | about $0.55–0.90 and 2–6 minutes a pass, on top of a run's ~$12 |

`approved` counts only if `04-proof.md` is non-empty **and** changed during the pass. A
proof left over from an earlier pass does not count.

## What changed

**`scripts/deliver.sh`**
- *The stage.* A pair `acceptance` with no writer. `has_writer()` gates what differs from
  other reviewers. A send-back moves the acceptance pair on a round of its own, so its
  return is a rework pass with a final round ahead.
- *The workflow deploys the preview, not the agent.* Before each pass it runs
  `scripts/deploy.sh preview up` (log in `build/acceptance/preview-up.log`) and retries once
  on failure. It tells the agent how that went in the `Preview:` line of its context block:
  `up at <origin>`, or `failed twice`. A build and a deploy can take longer than any tool
  call an agent makes, and a retry belongs in the script. `DELIVER_DEPLOY_SH` is the seam
  the loop test uses.
- *Write scope.* The acceptance-reviewer may write `04-proof.md` and
  `reviews/acceptance-reviewer-sendback-*`. The code-writer may no longer write `04-proof.md`.
- *Pre-flight* also checks for `cloudflared`, `k3d`, `kubectl` and `curl`.

**`scripts/smoke.sh [--origin URL] [--out DIR] [paths…] [-- pytest args]`**
- Runs the standard pack in `tests/smoke`, plus any feature-pack paths given, against the
  preview's origin. By default it reads `APP_ORIGIN` from `deploy.sh preview url`. Results
  and screenshots go to `--out`. Its exit status is pytest's.
- It never writes `docs/test-report.md`. Smoke runs are evidence for one deploy, not the
  repo's test record.

**`tests/smoke/`**
- `test_platform.py` is the standard pack. It has six tests: the app loads, the JWKS is
  published, `/api/v1/internal/` is not routed, Ada signs in, a message survives a reload,
  and an image round-trips through object storage. It ran 6/6 on every preview in the
  trials.
- `fixtures.py` holds what a feature pack builds on: `origin`, `out_dir`, `run_id`, `api`,
  `ada` (a `ChatPage`), `shot(page, name)`, a visible test PNG. The page objects are reused
  from `tests/bdd`.

**`scripts/lib/preview.sh`** — an image built from uncommitted work is tagged
`<sha>-<namespace>-dirty`, not `<sha>-dirty`. Two previews of uncommitted work no longer
overwrite each other's images.

**Docs and prompts**
- `.claude/agents/acceptance-reviewer.md` holds only the agent's own role. What every agent
  shares stays in `agent-context.md`, which now names seven agents and says where the
  acceptance-reviewer records its assumptions.
- `CLAUDE.md` describes the seventh stage, `tests/smoke` and `smoke.sh`.
- `docs/issues/exemplar-issue.md` gained a *Why* note for acceptance checks. The
  `issue-writer` skill asks, for each check, what makes it fail on `main`.

**Proven by**
- `.claude/delivery/loop-test.sh` has nine new scenarios. They cover approving without a
  proof, approving with a stale proof, asking for changes (refused), a send-back, the
  send-back bound, a stop for a human, a stray write, a deploy retried and a deploy that
  fails twice. All scenarios pass.
- Unit tests: 465 passed, including 12 for `smoke.sh` and 3 for the preview image tag.

## The trials

| Trial | Setup | Result | Time | Cost |
|---|---|---|---|---|
| Issue 5, acceptance only | stage seeded on a finished delivery | approved: 7 visible criteria passed, 8 internal ones mapped to tests | 5.7m | $0.86 |
| Issue 7, full run | all 7 stages, from the issue | 11 steps, no stop for a human | ~40m | ~$12.50 |
| Issue 7, acceptance v1 | the full run's own stage | approved, all 3 checks "passed" | 3m | $0.64 |
| Issue 7, acceptance v2 | after the prompt fix, fresh preview | approved: 2 proven, 1 regression check | 1.9m | $0.54 |

**How each acceptance pass was graded: rerun its feature pack against a preview of `main`.**
A test that passes there proves nothing about the branch.
- **v1:** 1 of 3 tests failed on `main`. The checks for the DM list and for reconnect passed
  there too, because Grace was already known to Ada's page by the time they ran. The proof
  marked all three "passed", and only its *For the human* hinted otherwise.
- **v2:** the agent rebuilt the DM check around Alan's first-ever sign-in. It labelled the
  reconnect check a **regression check** and named the Vitest tests that do discriminate.
  On `main`, both tests marked proven failed (Ada saw `01a14042` where "grace" should be),
  and the regression check passed. Every label was right.

**What fixed it.** The prompt now says that each feature test names the build it must fail
on, and is arranged so only the change decides the outcome. A test that can't be arranged
that way is labelled a regression check, with the test that does discriminate named. The
Result column is `proven / regression check / failed`. The same pass removed what the agent
file had copied from `agent-context.md`.

**What the issue should have said.** Issue 7's own acceptance checks couldn't discriminate
as written. That is now a rule in the exemplar issue and the issue-writer skill. A check
states the starting state that leaves only the change to decide it. If running the check
spends that state, each check that needs it gets a different user, because a preview keeps
its data between runs.

## Decisions

| Decision | Why |
|---|---|
| `04-proof.md` is tracked, beside the plan. Everything in `build/acceptance/` is disposable | The proof is the record of acceptance and the PR body's source. Screenshots are evidence for one run |
| The preview stays up after a run | A human tries the feature on it |
| The acceptance lens, not a second code review | The code-reviewer reviews the code. This stage checks behaviour, the record and the issue's checks |
| It sends back to the code-writer only | It sees symptoms in a browser, not causes. The code-writer, with the code open, can send on to the test-writer, and that one to the plan-writer. Every hop counts against `DELIVER_MAX_SENDBACKS` |
| Sonnet | It follows a script and writes Playwright, and the trials found no case for Opus |
| No superpowers skills named in any prompt | The plugin is installed per user, so CI won't have it, and its skills' rules conflict with the team's. Locally the agents invoke them unprompted (`writing-plans`, `test-driven-development` in the issue-7 run) without harm. Turning it off is one `--settings` line in `invoke_agent` |

## Known gaps

- `--out` resolves against the repo root, but pack paths resolve against the directory it
  was called from.
- `smoke.sh` has no `--no-standard`. A feature pack always runs beside the standard one.
- `DELIVER_MAX_ROUNDS=1` makes the first acceptance pass a final round.
- No loop-test scenario covers the exit-3 pause.
- The page-load test catches `pageerror` only, not console errors.
- `test_smoke_script.py` writes `build/smoke-unit-test` inside the repo.
- Every smoke run leaves channels behind (`smoke-<timestamp>-…`). They fill a preview's
  sidebar, and archiving them is not built.
- The proof reports open code-review minors but nothing fixes them. They are the human's.

## Next: the workflow on GitHub, and the PR

The next step runs `deliver.sh` on GitHub, and the acceptance-reviewer opens the PR there
with `gh`. These are what that step has to decide first.

1. **Who commits and pushes.** The repo's rule is that no session commits, but a PR needs a
   pushed branch. Something must be given that exception. The workflow is the better place
   for it, the same way it already owns the deploy. The script commits and pushes after
   `approved`, and the agent's new tool is `gh pr create --body-file` only, with no
   `git push`. Either way, `CLAUDE.md`'s *Never commit* gains a stated exception.
2. **Where the preview runs.** A GitHub-hosted runner is gone when the job ends, and its
   k3d cluster and quick tunnel go with it. "Leave it up" then means nothing. The options
   are a self-hosted runner with k3d, a long-lived cluster the job deploys to, or tearing
   the preview down and relying on screenshots. The proof's *Try it* section depends on
   the answer.
3. **Screenshots in the PR.** Links relative to the worktree don't resolve in a PR body, and
   GitHub has no API for the image attachments its web editor makes. The options:
   - push them to a branch and link the raw URLs;
   - upload `build/acceptance/` as an Actions artifact and link it, which works but
     doesn't show images inline;
   - commit them under the issue's docs.

   The proof's *Screenshots* section and the agent's link rule change with the choice.
4. **The PR body.** The proof is already laid out as a PR body: summary, try it, the
   criteria table, then *For the human*. The PR step probably lifts it whole, with the
   screenshot links rewritten. `## The run` might be better as a collapsed section.
5. **One delivery at a time.** Two `preview up`s at once both upgrade KEDA, so the
   GitHub workflow needs a `concurrency:` group.
6. **What CI changes about a run.**
   - No superpowers plugin. The measured runs all had it, so the first CI runs are a new
     baseline, not a repeat.
   - Secrets: an Anthropic key. `cloudflared` quick tunnels need no account.
   - Pre-flight's tool list becomes the runner's setup.
7. **The forge.** PRs so far went to Forgejo with `tea`. Moving to GitHub means `gh`, and
   the memory note on `tea` stops applying to this workflow.

Open from before: the issue-7 preview (`preview-feature-issue-7`) is still up. Take it down
with `BRANCH=feature/issue-7 scripts/deploy.sh preview down`.
