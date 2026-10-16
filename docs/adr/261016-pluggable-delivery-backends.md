# Delivery issues live behind a pluggable backend, and the agents never see which

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

The delivery team (`scripts/deliver.sh` and its agents in `.claude/agents/`) was built
entirely local: an issue is a file in `docs/issues/`, written by the `issue-writer` skill,
and a developer runs `deliver.sh` on their own machine. The next step is to run it from
GitHub: an issue is a real GitHub issue, a label on it starts a GitHub Actions workflow that
runs the delivery, and the workflow moves the label along as the stages progress. Forgejo,
where this repo's pull requests are merged today, and Azure DevOps are likely to follow, so
GitHub can't be wired in as a special case.

Three facts shaped the design. The agents already read the issue from a file: `deliver.sh`
copies it into the worktree on every run and names it in each agent's context block, so the
agents never touch a tracker. Everything downstream is named after the issue number:
`feature/issue-N`, `../caw-issue-N` and `docs/plans/issue-N/`. And GitHub's numbering doesn't
line up with the local issues. Pull requests share the same sequence, so the repo's first
GitHub issue will be #5, while local issues 1–8 and their plan folders already exist.

## Decision

We will put every issue operation behind a **delivery backend**: a Python package with a CLI,
`tools/delivery/` (`collabhub-delivery`, command `delivery`). It has one adaptor per backend
behind a single interface (`check`, `create`, `get`, `edit`, `ensure_label`). The **local**
adaptor writes `docs/issues/NNN.md` in exactly today's format. The **GitHub** adaptor shells
out to the `gh` CLI. Forgejo and Azure DevOps will be added as further adaptors.

Only the edges of the workflow call it. The `issue-writer` skill creates the issue and reads
it back through the CLI now. In the next slice, `deliver.sh` and the GitHub Actions workflow
will fetch the issue and update its stage label. The agents keep reading the issue-file copy
and never know which backend is in use.

An issue is identified by a **key** namespaced by backend. Local keys stay `issue-N`, so every
existing plan, branch and worktree keeps its name. GitHub keys are `gh-N`, and `fj-N` and
`ado-N` are reserved. The backend is chosen by `--backend`/`--url`, else by
`DELIVERY_BACKEND`/`DELIVERY_URL`, else it is local. The backend and URL are taken as a pair
from one source, so a URL left in the shell can't get mixed into an explicit choice.

## Consequences

Agent prompts and `.claude/delivery/loop-test.sh` don't change, and adding a backend means
writing an adaptor, not reworking a team. The issue model keeps the title and body separate,
so each backend renders them natively. GitHub gets a real title and a body without the
`Issue: N` line `deliver.sh` reads locally.

The library is dev tooling, so it's a workspace member that no image installs, like
`testkit`. testkit's directory-decides-the-layer rule now covers `tools/<pkg>/tests/` too,
so its tests get the unit layer's socket guard. The GitHub adaptor is unit-tested through an
injected command runner. Nothing tests it against real GitHub yet, so `gh` changing its
`--json` output would show up on first use rather than in CI. That gap should be revisited
when the GitHub Actions slice brings a `GH_TOKEN` into CI.

Posting to a remote backend publishes the issue, so the skill confirms with the user first
and then reads it back with `delivery issue verify`. A mismatch is fixed with `edit`, never a
second `create`. GitHub's 65,536-character body limit is enforced before `gh` runs.

Until the next slice, `deliver.sh` still takes only a local issue file. A GitHub issue can be
written, but it can't be delivered yet. Branches, worktrees and plan folders will be named by
key once that slice lands. Until then nothing guards against a key's paths colliding.

## Alternatives Considered

### Agents call the backend themselves

Agents could fetch the issue, post review comments or move labels directly. That would change
every agent prompt, make `loop-test.sh` depend on a backend, and spread tracker knowledge
across seven roles. The file copy already gives the agents everything they need.

### The GitHub REST API, or PyGithub

Calling the API directly means handling tokens and pagination ourselves. `gh` is already
signed in on developers' machines, takes `GH_TOKEN` in Actions, and handles GitHub
Enterprise through `HOST/OWNER/REPO`. Azure DevOps may still need direct HTTP, and the
interface allows that.

### Infer the backend from the git remote

This repo has both a GitHub remote (`origin`) and a Forgejo one (`forge`), so a remote
doesn't say where issues live. Inference is kept only for URLs whose host is unambiguous
(`github.com`, `dev.azure.com`).

### One number sequence, by burning GitHub numbers up to the local ones

Creating and closing placeholder issues until GitHub reaches #9 would keep `issue-N` paths
for everything. It would only work until both backends are used at once, and then the
sequences would collide again. Namespacing the key solves this for good, at the cost of one
prefix.
