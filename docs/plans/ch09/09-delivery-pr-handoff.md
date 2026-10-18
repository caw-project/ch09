# Delivery opens its PR — handoff after slice 3

Slice 3 (`08-delivery-actions-plan.md`, ADR `261016-delivery-commits-its-own-branch`) made the
runner commit and push `feature/<key>` after every stage, and added `.github/workflows/deliver.yml`,
which runs the same `scripts/deliver.sh` on a hosted runner. A delivery now ends at a pushed
branch whose last commit is `delivery(<key>): accepted`, with `docs/plans/<key>/04-proof.md`
on it, and a person still has to open the PR by hand, from the proof. The next slice has one
goal:

- **The acceptance-reviewer's approval ends in a pull request.** It writes the PR, with the
  proof attached and the run's evidence uploaded, so the person reviewing has everything in
  one place: what was built, how it was proven, screenshots, a link to try it, and the run.

Asked for by the user on 2026-10-18, after three real runs of `gh-3` on `caw-project/ch09`.
Read `08-…-plan.md` first: its *Found while building* and *Verified* sections say what the
runner and the workflow do now.

## Where things stand

- **Three accepted runs of gh-3.** `feature/gh-3-run1` (~99 min, one code-review send-back to
  the test pair), `feature/gh-3-run2` (107 min, no send-backs, $26.14) and `feature/gh-3`
  (`8f50f81`, ~96 min including a failed attempt and its resume; the code-reviewer approved first time).
  Any of them is a ready-made input for building the PR step: an accepted branch with a proof.
- **The proof is already shaped as a PR body** (`acceptance-reviewer.md`, *The proof*):
  summary, try it, the criteria table, the packs, screenshots, *For the human*, the run.
  Its screenshot links are relative (`../../../build/acceptance/…`) and resolve only in a
  worktree, and its *Screenshots* section already says "the PR uploads them".
- **`build/acceptance/` is uploaded as the `<key>-acceptance` artifact** (14 days), and the
  branch as a bundle. Transcripts are uploaded only from a private repo: `ch09` is public.
- **The preview dies with the job.** Run 3's proof links a quick tunnel that was gone when
  the job ended (handoff 07, decision 11, accepted that for slice 3).
- **No CI runs on a PR.** `deliver.yml` is the repo's only workflow; `docs/test-report.md`,
  committed by the code-writer's final verification, is the test evidence.
- **Backends:** `tools/delivery/delivery/model.py`'s `Backend` has `check`, `create`, `get`,
  `edit` and `ensure_label`, and nothing for PRs. `github.py` shells out to `gh`; `local.py`
  is files. Forge PRs have so far been opened by a person with `tea`.

## Decided

| # | Decision |
|---|---|
| 1 | **The approval opens the PR.** An `approved` acceptance pass ends with a PR from `feature/<key>` into `main`, opened in the same run, after the `accepted` commit is pushed. |
| 2 | **The acceptance-reviewer writes it.** The PR's title and body are the acceptance-reviewer's, built from its proof, with the proof's evidence attached and the run's artifacts linked. |

## Open — put these to the user

1. **Who calls `gh`.** Today no agent calls `delivery` or `gh`, or reads a URL (handoff 05's
   three rules), and the runner, not an agent, commits and pushes (ADR). Two readings of
   decision 2:
   - **The agent writes, the runner opens** (recommended): the acceptance-reviewer writes
     `docs/plans/<key>/05-pr.md` (title line, then body) beside its proof, and the runner
     opens or updates the PR through the backend after the push. The agent keeps no
     network tools, the write check keeps holding it to its files, and the same file
     opens a forge PR. This is handoff 03 item 1's recommendation.
   - **The agent opens it**: `Bash(gh pr create --body-file *)` in its tools. Simpler on
     GitHub, but the agent needs `GH_TOKEN`, knows the backend, and a locally run delivery
     against forge needs `tea` in its tools too.
2. **Screenshots inline.** GitHub has no API for the image attachments its web editor makes
   (handoff 03 item 3). Options:
   - commit the cited screenshots under `docs/plans/<key>/proof/` on the branch and link
     them by commit SHA: they render in the PR body, but they stay in `main`'s history after the merge;
   - push them to a separate evidence branch (one orphan branch, a folder per key) and link
     those: inline, out of `main`, but a second branch the runner pushes;
   - no inline images: link the `<key>-acceptance` artifact (`actions/upload-artifact`'s
     `artifact-url` output). Cheapest, but a zip download, gone after 14 days, and Actions-only.

   Recommended: the evidence branch, with the artifact linked as well. The proof's
   *Screenshots* section and the agent's link rule change with the choice.
3. **The preview a reviewer tries.** Handoff 07 decision 11 planned a second workflow,
   triggered by the PR, that deploys a fresh preview and keeps it up until the PR is approved
   or a timeout. Two facts change that plan:
   - **A PR opened with `GITHUB_TOKEN` triggers no `pull_request` workflow**, so a
     PR-triggered preview never runs for the delivery's own PR. `workflow_dispatch` is the
     exception: `deliver.yml` can dispatch the preview workflow itself, or the PR is opened
     with a GitHub App token.
   - **"Stays up" on a hosted runner is a job held open** — up to 6 hours, billed while it
     waits — with a quick tunnel whose URL changes each time.

   Choose between: a dispatched preview job with a timeout that posts its URL to the PR; a long-lived
   cluster the job deploys to; or no live preview, so the PR relies on screenshots and *Try it* says how to
   bring one up locally. This could also be its own slice, after the PR.
4. **When the PR opens, and as what.** Only at `approved`, as a ready PR (recommended), or a draft
   PR from the first checkpoint that each stage updates, ready at approval. A draft
   from the start shows progress on GitHub, but it means a PR body for every stage to keep up.
5. **A rerun with a PR already open.** Update its title and body (recommended), never open a
   second one; a send-back after acceptance can't happen today, because accepted ends the run.
6. **The body's shape.** Lift the proof whole, with the links rewritten and `## The run` collapsed in
   `<details>` (handoff 03 item 4), or a shorter body that links the proof on the branch.
   `Closes #N` for a `gh-` key, so the merge closes the issue.
7. **Forge.** `issue-` keys deliver locally and push to `forge` (Forgejo). Does the PR
   step open forge PRs too, through `tea` in a `local` adaptor, or is it GitHub-only for now
   with the body file left for a person?
8. **Stage labels and `needs_human` on the issue** (handoff 05, open items 1–2) are the same
   kind of work — the runner telling GitHub where a run is. They could come in this slice,
   or stay out of it.

## What it will need, roughly

1. **Backend, test first:** `open_pull_request` / `update_pull_request` (and `find` by head
   branch) on the `Backend` protocol; `github.py` through `gh pr create|edit|list --json`;
   `local.py` a no-op, or `tea` (open item 7). Unit tests against a fake runner, as the
   existing adaptor tests do.
2. **Runner:** after the `accepted` push, open or update the PR from the agent's file;
   a PR failure after a good push is reported but isn't a failed delivery. `DELIVER_PR=0` to
   turn it off; `loop-test.sh` sets it, as it sets `DELIVER_PUSH=0`.
3. **The acceptance-reviewer:** the PR file (or tool), the screenshot rule, its write scope
   in `rules.py` and the fixture together, and the stub's approved pass writing the file.
4. **The workflow:** `pull-requests: write`; the repo setting *Allow GitHub Actions to create
   and approve pull requests* on `ch09`; the evidence push and the artifact link; the PR URL in the
   job summary.
5. **Record:** CLAUDE.md's *Delivery workflow* paragraph ("a tested feature ready for
   review" becomes a PR); the `delivery.run` docstring; an ADR for the PR step and where
   evidence lives.
6. **Proof:** a stub dispatch on `ch09` that opens a PR, a second that updates it, then one real
   run.

## Carried over

- **The turn caps don't bite as configured.** `--max-turns` counts something different from
  the result's `num_turns`: the test-writer reported 294 and 310 turns against a cap of 200.
  Worth measuring before any cap is relied on.
- **Agent sketching is the test-reviewer's alone again** (slice 3, after run 3): the
  test-writer's proving pass cost about ten minutes a run, and the test-reviewer found the gaps anyway.
- **Actions annotations from every run:** the v4 actions target Node 20 and are forced onto
  Node 24, and `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19. Bump `checkout`,
  `setup-node`, `upload-artifact` and `setup-uv` to their Node 24 majors.
- **Housekeeping on `ch09`:** issue #4 and `feature/gh-4` from the stub runs, and the backup
  branches `feature/gh-3-run1` and `-run2`. Locally, the review worktree
  `../caw-gh-3-review`.
- **A delivery's branch never takes a later `main`** (slice 3, *Verified*). A long-open
  delivery PR can fall behind `main`; the PR shows that, and the runner still never merges.

## Not this slice

Merging, and any review agent acting on PR comments. Forgejo and Azure DevOps adaptors
beyond what open item 7 settles. CI checks on the PR — a separate workflow, not the
delivery's.
