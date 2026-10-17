# Delivery from GitHub Actions — slice 3: the runner commits, the workflow runs it

Slice 2 (`06-delivery-runner-plan.md`) ported `deliver.sh` to Python and made it take a key.
This slice makes the runner commit and push its own branch, so a delivery survives the
machine it ran on, and adds a GitHub Actions workflow that runs the same `scripts/deliver.sh`
on a hosted runner from a manual trigger. Opening the PR is the next slice.

Settled in a grilling session on 2026-10-16, building on handoff 07. Handoff 07's
*Decided* table still stands except where a decision here overrides it — 1 and 8 (commit
at every stage, not only at stops), 3 and 9 (the remote follows the backend).

## Decided

| # | Decision |
|---|---|
| 1 | **The remote follows the backend.** `issue-N` pushes to `forge`, `gh-N` to `origin`; `DELIVER_REMOTE` overrides both. A `gh-N` stop can then be answered from a laptop or from GitHub. `caw-project/ch09`'s `main` is kept current by a manual push from the forge checkout. |
| 2 | **A checkpoint after every stage,** committed and pushed, in both modes: `delivery(<key>): <stage> <result>, round <R>`, the stage's summary as the body. A stop and approval keep handoff 07's messages — `needs a human at <stage>, round <R>` and `accepted`. Each covers everything outside `build/`. `DELIVER_PUSH=0` commits without pushing. |
| 3 | **A deadline, not the kill.** `DELIVER_DEADLINE` (epoch seconds) and `DELIVER_DEADLINE_MARGIN` (minutes, default 75 — the longest stage plus a deploy): the runner starts no stage with less than the margin left; it checkpoints and exits **4**, "out of time — run again to continue". Unset, there is no deadline. |
| 4 | **A rejected push exits 1,** naming the local and remote commits. Never merge, never force (handoff 07, decision 2). The workflow uploads a `git bundle` of the branch so stranded checkpoints can be recovered. |
| 5 | **`restart`** forgets `docs/plans/<key>/run/` and starts at plan-writer **on the existing branch**, on top of its history. A clean branch means deleting it first; the summary says so. A plain rerun resumes. |
| 6 | **Job result:** exit 0 green; 2, 3 and 4 green with a ⚠️ banner and what to do next; 1 red. The workflow validates its inputs itself, so a bad-config 2 never reaches the runner. |
| 7 | **Inputs:** `key` (`^gh-[1-9][0-9]*$`), `restart` (boolean), `model` (choice: `default`, `haiku`, `sonnet` → `DELIVER_MODEL`, unset for `default`), `stub` (boolean). |
| 8 | **Timeouts:** `DELIVER_DEADLINE` is the job's start + 5½ h; the deliver step's `timeout-minutes` sits just under the job's 360 as a backstop. A backstop kill commits nothing partial — the next run reruns that stage from the last checkpoint. |
| 9 | **Disk:** a step frees the preinstalled toolchains (.NET, Android, GHC); `df -h` goes in the job summary before and after the run. Measured on the first stubbed run. |
| 10 | **Claude auth:** `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`, whichever is set; neither fails before setup. The summary names which was used. |
| 11 | **Hooks run as they do locally:** setup runs `npm ci` in `src/frontend` (eslint) and installs `gitleaks`. |
| 12 | **Pinned tools,** in the workflow's `env:` — `CLAUDE_VERSION` (native installer: `curl -fsSL https://claude.ai/install.sh \| bash -s "$CLAUDE_VERSION"`), `K3D_VERSION`, `CLOUDFLARED_VERSION`, `GITLEAKS_VERSION`. |
| 13 | **No transcripts from a public repo.** `build/delivery/` is uploaded only when `github.event.repository.private`; Actions masks secrets in logs but not in files. `build/acceptance/` and the bundle are always uploaded. The summary carries `history.log` and, on a stop, the questions from `needs-human.md`. |
| 14 | **A committed stub,** `.claude/delivery/stub-claude`, shared with `loop-test.sh` where their behaviour matches. The `stub` input puts it first on `PATH`; the deploy stays **real**, so the stubbed run proves k3d, image builds, tunnels and disk before any model spend. |
| 15 | **`actionlint`** joins the lint layer of `scripts/test.sh` (with `shellcheck` over `run:` blocks). The stubbed run on `caw-project/ch09` is the end-to-end proof. |
| 16 | **Any repo may run it** — dispatch needs write access and the Claude secret, and pre-flight says which is missing. |
| 17 | **One ADR:** *Delivery commits its own branch* — the CLAUDE.md exception, checkpoints, push on stop, the remote by backend, the deadline, never forcing. |

Handoff 07 decisions carried as they are: 2 (fetch, track, fast-forward, stop on divergence),
4 (CLAUDE.md exception; the HEAD-moved check stays, against the runner's own last commit),
5 (done in slice 2), 6 (resume state in `docs/plans/<key>/run/`, committed), 7 (snapshots
against the merge base), 10 (answering a stop on GitHub), 11 (the preview dies with the job).

## Out of scope

Opening the PR and the PR-triggered preview. Stage labels and `needs_human` as issue
comments. The workflow dispatching itself on exit 4. Fixing `gh-3`'s D46 note — a separate
session. Forgejo and Azure DevOps adaptors.

## Shapes

```
docs/plans/<key>/run/state.json        # was build/delivery/state.json — committed
docs/plans/<key>/run/history.log       # committed
docs/plans/<key>/run/sendback-*.snapshot
build/delivery/<stage>-*.json          # transcripts, ignored, uploaded only from a private repo
.github/workflows/deliver.yml
.claude/delivery/stub-claude
```

```
DELIVER_REMOTE          where to push. Default: forge for issue-N, origin for gh-N
DELIVER_PUSH            0 commits without pushing. Default: 1
DELIVER_DEADLINE        epoch seconds; no stage starts with less than the margin left
DELIVER_DEADLINE_MARGIN minutes. Default: 75
exit 4                  out of time — run the same command again to continue
```

Workflow, in order: validate inputs → free disk, `df -h` → checkout (credentials kept) →
setup-uv, Node, `npm ci`, native `claude`, k3d, cloudflared, gitleaks; check helm, kubectl →
stub on `PATH` if asked → git identity `github-actions[bot]` → `scripts/deliver.sh <key>`
with `DELIVERY_URL`, `GH_TOKEN`, `DELIVER_REMOTE=origin`, `DELIVER_DEADLINE` → *always:*
exit status, `df -h`, `history.log`, questions → summary; bundle and acceptance output
uploaded; transcripts if private. `concurrency: delivery-${{ inputs.key }}`,
`cancel-in-progress: false`; `permissions: contents: write, issues: read`.

## Tasks

### RED

1. **`test_run_keys.py` / `test_run_settings.py`** — `DELIVER_REMOTE` default by backend,
   override; `DELIVER_PUSH`; `DELIVER_DEADLINE` and its margin, bad values exit 2; the run
   dir is `docs/plans/<key>/run/`.
2. **`test_run_record.py`** — snapshots against the merge base: a committed change since the
   base counts, a commit on the branch doesn't make a path look changed, untracked files
   count; the write-scope check ignores `run/` as it does `build/`.
3. **A commit module's unit tests** — the message for each of checkpoint, stop and approval,
   with the summary as body; the paths it stages (everything but `build/`).
4. **The sync decision as a pure function** over (local exists, remote exists, ahead/behind,
   worktree dirty): track, fast-forward, nothing, or stop with its reason.
5. **The deadline as a pure function** — start the next stage or exit 4.
6. **`test_run_state.py`** — state loads from and saves to the run dir; `--restart` clears it
   and keeps the branch.
7. **Integration, `tests/integration/test_deliver.py`** against a bare repo as the remote:
   a new branch tracks an existing remote one; fast-forward; divergence exits 1; dirty with
   the remote ahead exits 1; a checkpoint per stage reaches the remote; a stop and approval
   leave their commits; a rejected push exits 1 naming both commits; `DELIVER_PUSH=0` pushes
   nothing; the deadline exits 4 after a checkpoint; the HEAD-moved check still stops an
   agent that commits.
8. **`loop-test.sh`** — sets `DELIVER_PUSH=0`; a scenario that a stop leaves a commit and that
   each stage leaves a checkpoint.

Stop at red for review.

### GREEN

9. Runner: run dir move, base snapshots, sync, commit and push, deadline and exit 4, the
   HEAD check against the runner's own commit. `.claude/delivery/stub-claude`.
10. `.github/workflows/deliver.yml` as in *Shapes*; `actionlint` in the lint layer of
    `scripts/test.sh`.

### Record

11. `CLAUDE.md`: the commit exception under *Never commit*; *Delivery workflow* — commits per
    stage, the remote, exit 4, the workflow. `agent-context.md`'s *Never commit* bullet.
    `delivery.run` docstring: the new settings, exit 4, "Nothing is committed" goes.
12. ADR via `adr-writer` (decision 17).
13. `.env.example`: the new `DELIVER_*` variables, commented.

### Verify

14. `scripts/test.sh lint unit`, the integration tests for `tools/delivery`, and
    `.claude/delivery/loop-test.sh`, all green.
15. Push `main` to `caw-project/ch09`; set its Claude secret; dispatch with `stub: true` on a
    throwaway `gh-N`. It runs seven stub stages with a real preview, leaves a checkpoint per
    stage on `origin`, exits 0, and its summary shows the disk before and after. A second
    dispatch of the same key reports it done.

## Red

Settled to run on to green without a stop, at the user's word. What each failed with:

- `test_run_commit.py`, `test_run_sync.py`, `test_run_clock.py` — `ModuleNotFoundError`;
  `test_run_keys.py` — `remote_for` missing; `test_run_settings.py` — the new fields missing.
- `test_snapshot.py`, five — `snapshot()` took no base.
- `test_deliver.py`, fourteen — no commits on the remote, the run dir still in `build/`, no
  sync, no exit 4. `test_an_agent_that_commits_still_stops_the_run` passed from the start: a
  regression guard for decision 4 of handoff 07.
- `loop-test.sh` — no commits on the loop branch, `history.log` not in `run/`.

## Found while building

- **`git add` refuses an exclude pathspec naming an ignored directory.** The runner adds
  everything, then `git rm --cached` takes `build/` back out, so it holds even where `build/`
  isn't ignored.
- **The snapshot base is resolved to a commit once, in the primary checkout.** The loop test's
  `DELIVER_BASE=HEAD`, read in the worktree, would move with every checkpoint.
- **A pause (exit 3) and out of time (exit 4) add no commit:** the checkpoint before them holds
  everything. A failure commits `failed at <stage>`, unless it is the rejected push itself.
- **`DELIVER_PUSH=0` skips the fetch too**, so a machine with no remote can run.
- **An unfinished run from before the move** has its `build/delivery/` state, history and
  snapshots carried into `run/` on its next open.
- **`run/` is outside every snapshot**, so the write check can't see an agent write there;
  `agent-context.md`'s *Never commit* bullet says it is the workflow's own.
- **The stub is the loop test's fake, moved:** `.claude/delivery/stub-claude`. With no
  `FAKE_SCRIPT`, writers are done and reviewers approve. `sed -i ''` went — GNU sed on the
  runner reads it differently.
- **actionlint and shellcheck come from PyPI wheels through `uvx`**
  (`actionlint-py==1.7.12.25`, `shellcheck-py==0.11.0.1`): nothing to install for the lint
  layer.
- **Pins:** `claude` 2.1.301, k3d v5.9.0, cloudflared 2026.9.3 (2026.10.1 was a day old),
  gitleaks 8.30.1.
- **The empty secret is never exported:** the workflow passes only the Claude secret that is
  set.
- **The test-writer sketches its own tests.** Mining the send-backs of eight deliveries put
  about twenty findings down to tests a correct build couldn't pass or a wrong one passed —
  every one found by a sketch, a round late. The test-writer now gets `sketch.sh` (fixture and
  rule together) and proves each new test green against a correct sketch and red against a
  named wrong build, reported under *Sketch runs*; the test-reviewer treats those as the
  writer's claim and sketches from the plan itself. The runner removes `build/sketch/` when
  every stage ends, test first, so the code-writer never builds from the test pair's probe
  and a stage that forgot `sketch.sh clean` leaves nothing for the next.
- **The second gh-3 run (39038184921) went to `accepted` with no send-back** — the test pair
  approved first time, the code-reviewer found only stale D28 docs — in 107 minutes against
  run 1's 99 (its failed pass included), at $26.14. Sketching every test cost the test-writer
  ten minutes for two short rounds saved, and the docs-only code rework spent 7.6 minutes
  rerunning every layer. So the test-writer now sketches only tests at risk (timers, races,
  library events, import-failing files, pure rules), and a rework reruns only the layers
  whose inputs it changed — Markdown or comments alone rerun lint.
- **Run 3 (39050054052) failed at the test-reviewer's round 2:** a 9-turn rework pass approved
  and wrote no review. The machine refused it rightly, but a forgotten file cost a person and
  a resume. Now, test first, the runner asks first: a verdict missing a file it owes is
  resumed once in its session, 20 turns, with the files named (`<NN-stage>.missing.json`
  beside the transcript), and the machine fails as before if it is still missing. The loop
  test's proof scenarios ask once before they stop, and one now writes its proof when asked.

## Verified

- `scripts/test.sh lint unit` — green (1248 pytest, 503 Vitest; actionlint clean).
- `scripts/test.sh integration -- tools/delivery` — 26 passed.
- `.claude/delivery/loop-test.sh` — every scenario passed.
- Task 15, the stubbed dispatch on `caw-project/ch09` (`4ef9d61` pushed to its `main`, issue
  #4, run 38930381295): green in 2m51s. Seven stages, a `github-actions[bot]` commit for each
  and `accepted` last, all on `origin`'s `feature/gh-4`; the bundle and acceptance artifacts
  uploaded, the transcripts not (public repo). Two things it found:
  - **`history.log` was never committed** — the repo ignores `*.log`, and the integration
    fixture's own `.gitignore` hid it. The fixture now copies the repo's `.gitignore`, which
    went red, and `.gitignore` un-ignores `docs/plans/*/run/history.log`.
  - **The preview failed both tries, and every service image fails to build on `main`:**
    slice 1 (`a8da719`) made `tools/*` a uv workspace member, and the service Dockerfiles copy
    only `src/services/`, so `uv sync --locked` can't find `collabhub-delivery`. It breaks the
    e2e stack and every preview, locally too — not this slice's, but it stops the stub run
    proving k3d and disk. The stub approved regardless, as a stub does.
    Fixed here, test first: `testkit`'s `test_dockerfiles.py` holds each Python service's
    Dockerfile to copying every workspace member root from the root `pyproject.toml` (red on all
    five), and each now copies `tools/` too. All five images build.
- A `restart` run (38936214228) failed its preview the same way, rightly: `restart` keeps the
  branch, and `feature/gh-4` was cut before the fix. **A delivery's branch never takes a later
  `main`** — nothing is merged in — so a fix on `main` reaches it only by deleting the branch
  or merging by hand. With the branch deleted, run 38936722276 went green in 5m37s: the preview
  came up on its first try, seven checkpoints and `accepted` reached `feature/gh-4`, and
  `run/history.log` is committed. A stub runs no tests, so the e2e Compose stack's disk and
  memory are first measured by a real run.
- The first real run, gh-3 (38948278868), took the plan and test pairs to approval in two rounds
  each (48 minutes, $15.35), then failed at the code-writer after 18.6 minutes: it wrote
  `CLAUDE.md`, as the issue's record section asks, and the code-writer's write scope had no
  room for it. The first fix let the scope take the root `CLAUDE.md` (`4422c67`), so the run
  could resume — the runner is `main`'s, not the branch's, so a rules fix reaches a run without
  touching its branch. **Reversed after review:** the real fault was that `CLAUDE.md` restated
  decisions (D13, D16, D28, the Auth types, the soft-delete exceptions), and the issue-writer
  told issues to list it under *Record in this slice* for that reason. `CLAUDE.md` now states no
  decision — each was already in the register or a design doc — and says a decision's
  exception to a convention is recorded in the conventions doc; the issue-writer never puts
  `CLAUDE.md` or `.claude/` in an issue's record; and the code-writer's scope is back without it.
- The failure commit kept the write the check had refused (`f45e31d` holds the code-writer's
  `CLAUDE.md` edit), and the resumed pass built on it. Fixed test first: a refused write is set
  aside into `build/delivery/refused/<NN-stage>/` and its path put back as the last checkpoint
  had it — deleted if new — before the failure is committed.
- The resume (38957055605) started at the code-writer and went green in 30m40s: the
  code-reviewer sent one critical back (migration 0002's `str.lower()` against the index's
  Postgres `lower()`), the test pair added its red test, and the second code round and the
  acceptance-reviewer approved — the e2e suite ran on the runner (25 passed), the preview came
  up on its first try, and `feature/gh-3` ends at `accepted`. Fifteen recorded stages: 73 minutes
  of agent time, $22.44, plus the failed first code-writer pass, which `history.log` doesn't
  record.
