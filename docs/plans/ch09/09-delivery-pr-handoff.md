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
  the job ended. Handoff 07's decision 11 accepted that for slice 3; decision 4 below replaces it.
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
| 3 | **Screenshots live in the branch's history for as long as the PR does.** The runner commits the screenshots the proof cites under `docs/plans/<key>/proof/`, then deletes them in the very next commit, and pushes both. The PR body links each one at the commit that added it (`…/blob/<sha>/…?raw=true`), so they show inline. The PR's diff has no images. A squash merge brings none into `main`; a plain merge keeps them in history but not in the tree. Once the branch is deleted, those commits go with it. No evidence branch, nothing to clean up. |
| 4 | **The preview a reviewer tries runs on a hosted runner, held open for the review.** A new `.github/workflows/preview.yml` deploys the PR's branch with `scripts/deploy.sh preview up`, posts the origin to the PR, and then waits. We assume a PR is reviewed well within a hosted runner's 6 hours. The job ends when the PR is approved or closed, or just before its time limit, whichever comes first. A push to the PR starts a new preview job and cancels the old one (one concurrency group per PR, `cancel-in-progress: true`), so a closed event stops the waiting job the same way. The proof's *Try it* section points at the PR's preview, not the acceptance run's tunnel, which dies with `deliver.yml`. |

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
2. **How the delivery's own PR starts its preview.** GitHub starts no workflow for an event
   caused by `GITHUB_TOKEN`, so it can't recurse: a PR that `deliver.yml` opens with its
   own token fires no `pull_request` workflow. A person's push to the PR still fires one. Two
   ways around it:
   - **`deliver.yml` dispatches the preview itself** (recommended): `gh workflow run
     preview.yml -f pr=<n>` right after it opens the PR. `workflow_dispatch` is the one event
     `GITHUB_TOKEN` may start. No new secret is needed, and `preview.yml` takes both
     triggers.
   - **Open the PR with a GitHub App token**, so `pull_request` fires as it does for a person.
     Cleaner events, but it means an App and its private key in the repo's secrets.
3. **The proof's screenshot links.** Today they are relative (`../../../build/acceptance/…`).
   With decision 3, either the agent names the screenshots it cites and the runner rewrites
   the links in the PR body to the commit's raw URLs (recommended: the agent never knows a
   SHA or a URL), or the proof links `proof/<file>` and the body is lifted as is.
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
3. **Screenshots (decision 3):** the runner's add-then-remove commits after the `accepted`
   one, and the links rewritten to them in the PR body. Test it against a bare repo, as the
   checkpoint tests do: the PR's net diff has no images, and the linked SHA holds each one.
4. **The acceptance-reviewer:** the PR file (or tool), the screenshots it cites, its write scope
   in `rules.py` and the fixture together, and the stub's approved pass writing the file.
5. **`deliver.yml`:** `pull-requests: write` (and `actions: write` to dispatch the preview); the repo
   setting *Allow GitHub Actions to create and approve pull requests* on `ch09`; the PR URL in the
   job summary.
6. **`preview.yml` (decision 4):** the same setup as `deliver.yml`, minus `claude`. It runs
   `preview up`, comments the origin on the PR, polls the PR's review state and stops when
   it is approved or closed, or at about 5¾ hours, then runs `preview down`. Concurrency is
   per PR, so a push replaces the preview. A stub delivery's PR is enough to prove it.
7. **Record:** CLAUDE.md's *Delivery workflow* paragraph ("a tested feature ready for
   review" becomes a PR); the `delivery.run` docstring; an ADR for the PR step and where
   evidence lives.
8. **Proof:** a stub dispatch on `ch09` that opens a PR, whose preview comes up and posts its origin.
   A second dispatch updates the PR. Closing the PR takes the preview down. Then one real run.

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

Merging, and any review agent acting on PR comments. A preview that outlives a hosted
runner's 6 hours (a self-hosted runner or a long-lived cluster). Forgejo and Azure DevOps adaptors
beyond what open item 7 settles. CI checks on the PR — a separate workflow, not the
delivery's.
