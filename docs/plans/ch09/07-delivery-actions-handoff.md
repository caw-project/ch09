# Delivery from GitHub Actions — handoff after slice 2

Slice 2 (`06-delivery-runner-plan.md`, ADR `261016-delivery-runner-in-python-by-key`) ported
`scripts/deliver.sh` to Python in `tools/delivery/delivery/run/`. A delivery now takes an
issue by its key and fetches it through the backend, so `gh-3` can already be delivered from a
laptop. The next slice has two goals:

- **A GitHub Actions workflow** runs the same `scripts/deliver.sh` on a hosted runner, with
  `claude` installed there, from a manual trigger.
- **Both modes commit and push**, locally and in the runner, once the acceptance-reviewer
  approves, and on every stop.

The end state: either run `scripts/deliver.sh` locally as today, or trigger the workflow, and
it all happens in GitHub. Opening the PR is the slice after this one.

Settled with the user on 2026-10-16, after slice 2's review. Read `06-…-plan.md` first: its
*Found while building* and *Closed* sections say what the runner does now.

## Decided

| # | Decision |
|---|---|
| 1 | **Push on a stop.** A `needs_human` stop, a crash that stops the run, and the acceptance-reviewer's approval each commit and push the branch. Without that, the run state and `needs-human.md` die with a hosted runner. |
| 2 | **Fetch and reuse the remote branch.** Always fetch before starting. If `origin/feature/<key>` exists and there is no local branch, track it rather than cutting a new one from `main`. If the remote is ahead and the local branch can be fast-forwarded, fast-forward. If they have diverged, or the worktree has uncommitted changes while the remote is ahead, stop with exit 1 and say why. Never merge, never force. |
| 3 | **Remotes:** `DELIVER_REMOTE`, defaulting to `forge` (the local Forgejo remote), with the workflow setting `origin`. `DELIVER_PUSH=0` commits without pushing; `loop-test.sh` sets it and must never push. |
| 4 | **CLAUDE.md gains one exception to *Never commit*:** the delivery workflow — the runner, never an agent — commits and pushes its own branch at a stop and at approval. The check after each stage that HEAD hasn't moved stays: an agent that commits still stops the run. `agent-context.md`'s *Never commit* bullet says the same. |
| 5 | **The code-writer doesn't edit workflows.** **Done in slice 2:** `write_denied` refuses `.github/workflows/`, the fixture row changed with it, and `agent-context.md` makes CI workflows out of scope for every stage. That keeps `GITHUB_TOKEN` able to push every branch a delivery makes. |
| 6 | **Resume state lives in the plan dir, committed:** `docs/plans/<key>/run/` holds `state.json`, `history.log` and the send-back snapshots. Transcripts (each stage's JSON) stay in the ignored `build/delivery/`, and the workflow uploads them as an Actions artifact. The write-scope check ignores `run/` as it ignores `build/`. |
| 7 | **Snapshots against the branch's base,** not "uncommitted": every path changed or added since `git merge-base <base> HEAD`, plus untracked files, each with a content hash. A commit on the branch then doesn't make committed files look changed. The per-stage write check is unchanged in effect. |
| 8 | **Commits:** one per stop and one at approval, covering everything outside `build/`. Messages are `delivery(<key>): needs a human at <stage>, round <R>` and `delivery(<key>): accepted`, with the stage's summary as the body. The author is the developer's git config locally, and `github-actions[bot]` in the runner. |
| 9 | **Same in both modes.** A local stop also commits and pushes (to `forge`), so a stop can be answered from either place. |
| 10 | **Answering a stop on GitHub:** a person edits `docs/plans/<key>/needs-human.md` on the branch, then runs the workflow again with the same key. Decision 2 brings their commit in. |
| 11 | **Preview:** the acceptance-reviewer's preview runs in the job and dies with it. That's accepted for this slice: the proof's *Try it* link is dead once the job ends. The PR slice deploys a fresh preview from a second workflow, triggered by the PR, which stays up until the PR is approved or a timeout. |

## The workflow

- **Trigger:** `workflow_dispatch` with inputs:
  - `key` (`gh-N`, validated);
  - `restart` (boolean);
  - optional `model` (`DELIVER_MODEL`, for a cheap dry run);
  - optional `stub` (boolean): put a stub `claude` first on `PATH`, like the one used to
    prove slice 2 (`06-…-plan.md`, *Verified*), so the workflow proves its plumbing before any
    model spend.
- **Concurrency:** one group per key (`delivery-${{ inputs.key }}`), `cancel-in-progress:
  false`. Each hosted runner has its own k3d, so the old "two deliveries both upgrade KEDA"
  clash goes away; two runs of one issue racing each other doesn't.
- **Permissions:** `contents: write`, `issues: read`. `GH_TOKEN: ${{ github.token }}`, and
  `DELIVERY_URL: ${{ github.server_url }}/${{ github.repository }}`, so the backend is
  inferred from the URL.
- **Checkout:** `actions/checkout` with credentials kept for the push. The worktree goes
  beside it under `/home/runner/work/<repo>/`, exactly as it does locally, so the runner has
  one code path. Fetch `main` and the delivery branch (decision 2).
- **Setup is pre-flight's list** (`delivery/run/preflight.py`):
  - **Installs:** `uv` (`astral-sh/setup-uv`), Node, `claude` (npm), `k3d`, `cloudflared`;
    `helm` and `kubectl` come with the image, but check.
  - **The hooks.** `.claude/settings.json`'s hooks fire in headless runs too. The lint hook
    needs `uv` and the frontend's `node_modules` (for eslint); the security hook runs
    `uvx semgrep` and skips `gitleaks` if it's missing. Install `gitleaks`, or decide to
    let it skip.
  - **Secret:** `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`).
- **After the run,** whatever its exit:
  - upload `build/delivery/` and `build/acceptance/` as artifacts;
  - put the exit status in the job summary, with `history.log` and, on a stop, the
    questions from `needs-human.md`.

## What CI changes about a run

- **No user-level plugins, memory or CLAUDE.md.** The measured runs all had the superpowers
  plugin, so the first CI runs are a new baseline (handoff 03, item 6).
- **Capacity.**
  - **Time:** the longest finished run on disk took about 101 minutes (`caw-issue-1-m3`), well
    inside the 6-hour job limit.
  - **Resources:** a run holds the e2e Compose stack (Elasticsearch included), then a k3d
    cluster with every image. Check the runner's memory and disk for the repo's visibility
    (standard runners are larger for public repos), and set a `timeout-minutes`.
- **The trial repo** is https://github.com/caw-project/ch09. It holds the full code tree as
  well as the issues, which the workflow needs: the code and the issues are in one repo.
  `gh-3` is the first candidate. Fix its D46 tenancy note first (handoff 05, *Known gaps*).

## Tasks, roughly

1. Runner, test first:
   - resume state into `docs/plans/<key>/run/` (decision 6);
   - snapshots against the base (7);
   - fetch, track and fast-forward (2);
   - commit and push at stops and approval (1, 3, 8, 9).

   Unit tests for the message, the paths and the sync decision; integration tests against a
   bare repo as the remote.
2. `loop-test.sh` with `DELIVER_PUSH=0`, plus a scenario that a stop leaves a commit.
3. The workflow and its setup; a stubbed run on `caw-project/ch09` as the first proof.
4. CLAUDE.md's commit exception, `agent-context.md`'s *Never commit* bullet, and the
   `delivery.run` docstring.
5. An ADR for the commit exception and the push-on-stop model.

## Not this slice

Opening the PR, and the PR-triggered preview workflow (decision 11). Stage labels on the issue,
and `needs_human` as issue comments, are both still open from handoff 05. Screenshots in a PR
body (handoff 03, item 3). Forgejo and Azure DevOps adaptors.
