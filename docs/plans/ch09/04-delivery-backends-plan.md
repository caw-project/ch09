# Delivery backends — slice 1: the library and the issue-writer

The delivery team's issues are files in `docs/issues/` and `scripts/deliver.sh` runs on a
laptop. The goal is a swappable **backend** — local today, GitHub next, Forgejo or Azure
DevOps later — with the agents unaware of which one is in use. This slice builds the
library of adaptors and moves the `issue-writer` skill onto it, so it can post a GitHub
issue and read it back. `deliver.sh`, the GitHub Actions workflow and the stage labels are
the next slice.

Settled in a grilling session on 2026-10-16.

## Decided

| # | Decision |
|---|---|
| 1 | **Agents stay file-only.** Only the edges use the library: the issue-writer now, `deliver.sh` and the GHA wrapper next slice. The six (now seven) agents keep reading the `Issue file:` copy; no agent prompt changes. |
| 2 | **`tools/delivery/`**, a uv workspace member (`collabhub-delivery`, module `delivery`), dev-only like `testkit`, stdlib only. A CLI, `delivery`, is how bash and the skill drive it. |
| 3 | **Selection:** `--backend`/`--url` arguments, else `DELIVERY_BACKEND`/`DELIVERY_URL`, else `local`. The pair comes from one source: if either argument is given the environment is not read, so a stray env var can't mix into an explicit choice. |
| 4 | **The GitHub adaptor shells out to `gh`**, through an injected runner so unit tests never run it. `--repo` is always `HOST/OWNER/REPO`, so GitHub Enterprise needs nothing extra. |
| 5 | **Keys namespace by backend:** local `issue-N` (unchanged — every existing plan, branch and worktree stays valid), GitHub `gh-N`; `fj-N` and `ado-N` reserved. Next slice builds paths from it: `feature/<key>`, `../caw-<key>`, `docs/plans/<key>/`. |
| 6 | **Local is an adaptor too.** It writes `docs/issues/NNN.md` exactly as today — `Issue: N`, blank, `# Issue N — <title>`, blank, body — so `deliver.sh` reads it unchanged. |
| 7 | **The model holds title and body apart;** each adaptor renders them. GitHub's body has no `Issue:` line and no H1 — the number and title are metadata. |
| 8 | **Operations:** `check`, `issue create`, `issue get`, `issue edit`, `ensure-label`, plus `issue verify` — the read-back comparison as a command, so the skill doesn't judge whitespace by eye. |
| 9 | **Read-back:** title and body compared after normalising (CRLF → LF, trailing whitespace per line, leading/trailing blank lines). A mismatch is fixed with `edit`, never a second `create`. Then the skill's step-5 plan-writer read runs on the *fetched* text. |
| 10 | **Marker label `delivery`** on every remote issue — not the trigger, which stays a human action. `ensure-label` creates it if missing (local: no-op). |
| 11 | **URL rules:** `github.com` infers `github`; `dev.azure.com` infers Azure DevOps, which is refused as not supported yet; any other host needs `--backend`. `--url` with `local` is an error, as is `github` without a URL. |
| 12 | **`check` runs before grilling** — GitHub: repo exists, issues enabled, viewer can write. Local: `docs/issues/` exists. |
| 13 | **Remote posting is confirmed:** the skill names backend and repo and waits for "post it" after the coverage-table sign-off. Local is unchanged. |
| 14 | **A GitHub run ends with the URL and key** and one line saying delivery from GitHub arrives with the GHA slice. No stopgap. |
| 15 | **No live GitHub test.** Unit tests through the runner seam; the first real skill run against `sixeyed/claude-at-work-project` is the check. Revisit when the GHA slice brings `GH_TOKEN` into CI. |

Decided while planning, not in the session: the env/argument pair rule in 3; `issue verify`
as its own command in 8; GitHub's 65,536-character body limit refused before `gh` runs, so
the failure is ours and clear; `check` requires `WRITE`, `MAINTAIN` or `ADMIN`, because
creating a label needs write.

## Out of scope

`deliver.sh` taking a key; the GHA workflow; the stage-label state machine; a guard against
plan-path collisions; Forgejo and Azure DevOps adaptors.

## The wire shapes

```
delivery [--backend B] [--url U] check
delivery [...] issue create --title T --body-file F [--label L ...]   -> Issue JSON
delivery [...] issue get KEY                                          -> Issue JSON
delivery [...] issue edit KEY --title T --body-file F                 -> Issue JSON
delivery [...] issue verify KEY --title T --body-file F               -> exit 0 match / 1 differences
delivery [...] ensure-label NAME [--description D] [--color C]
```

Issue JSON: `{"key", "number", "title", "body", "url", "labels"}`. Exit 0 ok, 1 a backend
failure or a verify mismatch, 2 bad configuration or usage — message on stderr, never a
traceback.

| Operation | `gh` call |
|---|---|
| check | `gh repo view H/O/R --json hasIssuesEnabled,viewerPermission` |
| create | `gh issue create --repo H/O/R --title T --body-file - [--label L]` (body on stdin; prints the URL) then `get` |
| get | `gh issue view N --repo H/O/R --json number,title,body,url,labels` |
| edit | `gh issue edit N --repo H/O/R --title T --body-file -` then `get` |
| ensure-label | `gh label create NAME --repo H/O/R --description D --color C --force` |

## Tasks

### RED

1. **testkit** — `tests/unit/test_plugin.py`: a test under `tools/<pkg>/tests/unit/` is
   selected by `-m unit`, one under `…/integration/` by `-m integration`, and a stray file in
   `tools/<pkg>/tests/` stops the run.
2. **`test_resolve.py`** — precedence, the pair rule, URL inference, every refusal in 11.
3. **`test_local.py`** — numbering after the highest (exemplar ignored), the rendered file
   `deliver.sh` reads, get/edit round trip, reading an existing issue in today's format,
   unknown and foreign keys, `check` without `docs/issues/`.
4. **`test_github.py`** — each row of the `gh` table through a recording runner; the
   `Issue` mapped from `gh`'s JSON; the body limit; permission and issues-disabled refusals;
   a failing `gh` surfaced as a backend error.
5. **`test_readback.py`** — normalisation, and a changed title or body line named.
6. **`test_cli.py`** — each command against the local backend on `tmp_path`, JSON out, exit
   codes 0/1/2, one GitHub path through a fake runner.

Stop at red for review.

### GREEN

7. Workspace wiring: root `pyproject.toml` members `tools/*`, `testpaths` adds `tools`,
   source + dev group `collabhub-delivery`, coverage `source_pkgs` adds `delivery`.
8. `testkit.plugin.layer_of` accepts `tools/<pkg>/tests/<layer>/`.
9. `delivery`: `model`, `resolve`, `local`, `github`, `readback`, `cli`.
10. Rewrite `.claude/skills/issue-writer/SKILL.md`: arguments, `check` first, confirm before
    a remote post, `ensure-label` + `create` + `verify` (+ `edit` on mismatch), step 5 on
    `issue get`, the per-backend ending; frontmatter description backend-neutral.

### Record

11. ADR via `adr-writer`: pluggable delivery backends, agents file-only, keys by backend.
12. `CLAUDE.md`: `tools/delivery/` in the repo layout; the Delivery workflow paragraph on
    backends and keys.
13. `.env.example`: `DELIVERY_BACKEND=local`, `DELIVERY_URL=`.

### Verify

14. `scripts/test.sh lint unit` green; `.claude/delivery/loop-test.sh` still passes (nothing
    in `deliver.sh` changed, so it should).
15. First real run, by hand: `/issue-writer --backend github --url
    https://github.com/sixeyed/claude-at-work-project` on a small issue — `check` passes,
    the issue posts with `delivery`, `verify` matches, the ending shows `gh-<N>`.
