# Acceptance reviewer — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A seventh `scripts/deliver.sh` stage, `acceptance-reviewer`, that deploys the
branch to a preview, runs a standard and a feature smoke pack against it, and writes
`docs/plans/issue-<N>/04-proof.md` for a human to accept from.

**Architecture:** The stage is a reviewer with no writer of its own (pair `acceptance`)
appended to the state machine. It sends back to the code-writer. A new `scripts/smoke.sh`
runs pytest + Playwright packs against an origin, loading `tests/smoke/fixtures.py` as a
plugin so a disposable pack under `build/acceptance/` gets the same fixtures as the standard
pack in `tests/smoke/`.

**Tech Stack:** bash 3.2 · pytest + pytest-playwright (sync) · the `bdd.pages` page objects ·
`claude -p` headless agents.

**Spec:** `docs/plans/ch09/01-acceptance-reviewer-design.md`

## Global Constraints

- Work in `../caw-acceptance-reviewer` on `feature/acceptance-reviewer`. **Never commit,
  never stage** (CLAUDE.md) — there are no commit steps in this plan.
- **Stop at red** (D32, interactive session): Tasks 1 and 3 write failing tests. After
  each one's red run, stop for the user to review the tests before any production change.
- Scripts are bash 3.2: no associative arrays, and an empty array is
  `${arr[@]+"${arr[@]}"}`.
- The lint hook blocks on ruff/eslint findings — fix them, whatever the task.
- `04-proof.md` is tracked. Screenshots, the feature pack and JUnit go under `build/acceptance/`.
- The preview is left up when the stage finishes.
- The acceptance-reviewer's model is `sonnet`, in both `default_model` and the agent's `model:` line.
- A smoke pack reaches the app **only through its origin**. It never touches a database,
  never truncates, and never creates anything without the `run_id` prefix.
- After any change to `deliver.sh`, run `.claude/delivery/loop-test.sh`.

## Review Focus

1. **The fake can't see uncommitted agents.** `loop-test.sh` builds its worktree from
   `HEAD`, and `deliver.sh` pauses (exit 3) at a stage whose agent file isn't in that
   worktree. An uncommitted `acceptance-reviewer.md` would pause every scenario. Task 1
   pre-creates the worktree and copies the working copy's `.claude/agents` and
   `.claude/delivery` into it.
2. **`changes_requested` from a stage with no writer** must stop the run, not loop
   back to `acceptance-writer`, which doesn't exist. Task 1, scenario
   `acceptance-may-not-ask-for-changes`.
3. **An approval with no proof** must not count as done. Task 1, scenario
   `acceptance-approves-without-proof`.
4. **No live preview when `smoke.sh` runs without `--origin`.** It must fail naming
   `preview up`, not run pytest against an empty origin. Task 3, the
   `test_no_preview_*` tests.
5. **A relative extra-pack path** must resolve against the caller's directory after
   `smoke.sh` changes to the repo root. Task 3, `test_extra_paths_are_made_absolute`.

---

## File map

| File | Change | Responsibility |
|---|---|---|
| `.claude/delivery/loop-test.sh` | modify | Fake-`claude` proof of the state machine, with the 7th stage |
| `scripts/deliver.sh` | modify | The stage: state, tools, scope, context, verdicts, pre-flight, header |
| `src/services/testkit/tests/unit/test_smoke_script.py` | create | Unit tests of `smoke.sh`'s arguments and origin |
| `scripts/smoke.sh` | create | Runs smoke packs against an origin |
| `pyproject.toml` | modify | `testpaths` stops collecting `tests/smoke` |
| `tests/smoke/__init__.py`, `tests/smoke/fixtures.py` | create | The smoke fixtures plugin |
| `tests/smoke/test_platform.py` | create | The standard pack |
| `.claude/agents/acceptance-reviewer.md` | create | The agent's role |
| `.claude/delivery/agent-context.md` | modify | The team table, context lines, send-back routes |
| `CLAUDE.md` | modify | The delivery workflow, the repo layout, testing |

---

### Task 1: The state machine's red set — `loop-test.sh`

**Files:**
- Modify: `.claude/delivery/loop-test.sh`

**Interfaces:**
- Produces, for Task 2's `deliver.sh` to satisfy:
  - the context-block lines `Proof: docs/plans/issue-<N>/04-proof.md` and `Evidence: build/acceptance/`
  - the send-back file `reviews/acceptance-reviewer-sendback-<R>.md`
  - first-pass turns of 200
  - the model `sonnet`
- The fake's new verdicts:
  - `approved_bare` — approves and writes nothing
  - `stray` — approves after writing `src/stray.txt`

- [ ] **Step 1: Seed the loop worktree from the working copy.** Uncommitted agents
  and delivery files must reach it (Review Focus 1). In `scenario()`, replace the
  `cleanup` line with:

```bash
    cleanup
    # deliver.sh pauses at a stage whose agent isn't in the worktree, and the
    # worktree is built from HEAD — so an agent not yet committed would pause every
    # scenario. Seed it from the working copy; deliver.sh reuses a worktree it finds.
    git -C "$ROOT" worktree add -q -b "$BRANCH" "$WORKTREE" HEAD >/dev/null 2>&1
    cp -R "$ROOT/.claude/agents" "$ROOT/.claude/delivery" "$WORKTREE/.claude/"
```

- [ ] **Step 2: Teach the fake the proof and the two new verdicts.** In the `FAKE`
  heredoc, replace the `out=` line and the `approved | changes_requested)` arm.

  The `out=` line becomes:

```bash
status="$verdict"
case "$verdict" in approved_bare | stray) status=approved ;; esac
out='{"status":"'"$status"'","summary":"fake","files":[],"questions":["what?"]}'
```

  The `approved | changes_requested)` arm becomes:

```bash
    approved | changes_requested)
        # A reviewer with no writer of its own writes a proof, not a review.
        f="$(field 'Write your review to')"
        [ -n "$f" ] || f="$(field Proof)"
        [ -z "$f" ] || leave "$f"
        ;;
    approved_bare) ;;
    stray) leave src/stray.txt ;;
```

- [ ] **Step 3: Every scenario that reached `done` now takes a seventh verdict.**
  - Append `approved` to these scenarios' verdict lists:
    - `straight-through`
    - `approved-in-round-two`
    - `reviewer-sendback`
    - `writer-sendback`
    - `code-reviewer-sendback`
    - `sendback-after-three-rounds`
    - `nested-sendbacks`
    - `out-of-turns-resumed`
    - `crash-then-rerun`
    - `model-and-effort-by-stage`
    - `one-model-for-every-stage`
    - `rework-model`
    - `out-of-turns-keeps-its-flags`
  - Append `acceptance-reviewer` to every `ran` line in them.
  - Then extend `straight-through`:

```bash
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer
told 7 'Stage: acceptance-reviewer, round 1 of 3'
told 7 'Turns: 200'
told 7 'Red report: docs/plans/issue-999/02-red-tests.md'
told 7 'Green report: docs/plans/issue-999/03-green-report.md'
told 7 'Proof: docs/plans/issue-999/04-proof.md'
told 7 'Evidence: build/acceptance/'
told 7 "Send-back file, if you send work back: $REVIEWS/acceptance-reviewer-sendback-2.md"
not_told 7 'Write your review to'
flags 7 sonnet ''
history_has '^07 acceptance-reviewer approved \[1m 3 turns \$0.5 · sonnet · default\]'
exists 04-proof.md
```

  - and `one-model-for-every-stage`: `flags 7 haiku ''`.

- [ ] **Step 4: Add the acceptance scenarios**, before the `# A stage's model and effort`
  block:

```bash
# The acceptance-reviewer approves only with its proof written.
scenario acceptance-approves-without-proof 1 done approved done approved done approved approved_bare
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer

# It has no writer to ask for changes: that is a stop, never a loop.
scenario acceptance-may-not-ask-for-changes 1 done approved done approved done approved changes_requested

# It sends back to the code-writer, and the flow comes forward through the
# code-reviewer to it again — a rework pass in a new round of its own.
scenario acceptance-sendback 0 done approved done approved done approved send_back done approved approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer \
    code-writer code-reviewer acceptance-reviewer
told 8 "Review to address: $REVIEWS/acceptance-reviewer-sendback-2.md"
told 8 'Stage: code-writer, round 2 of 3'
told 8 'Rework pass'
told 9 'After a send-back by acceptance-reviewer'
told 9 "Write your review to: $REVIEWS/code-reviewer-2.md"
told 10 'Stage: acceptance-reviewer, round 2 of 3'
told 10 'Rework pass'
told 10 'After a send-back by acceptance-reviewer'
not_told 10 'Write your review to'
exists reviews/acceptance-reviewer-sendback-2.md
exists 04-proof.md

# The code pair takes three of its send-backs; a human sees the fourth.
scenario acceptance-sendbacks-bounded 2 done approved done approved done approved send_back \
    done approved send_back done approved send_back done approved send_back
exists needs-human.md

scenario acceptance-needs-human 2 done approved done approved done approved needs_human
exists needs-human.md

# It writes its proof and its send-back file on the branch, and nothing else.
scenario acceptance-stray-write 1 done approved done approved done approved stray
```

- [ ] **Step 5: Run it and record the red.**

  Run: `.claude/delivery/loop-test.sh`

  Expected: FAIL. Every scenario that now ends at the seventh stage exits 3, with
  `Paused: acceptance-reviewer has no agent` — `deliver.sh` doesn't know the stage. The
  original scenarios with no seventh verdict pass: `three-rounds-then-a-human`,
  `too-many-sendbacks`, `out-of-turns-twice`, `crash-twice`, `asks-a-human`,
  `final-round-effort-over-rework`. Record each failing scenario's first FAIL line.

- [ ] **Step 6: STOP at red** for the user to review the scenarios.

---

### Task 2: The stage in `scripts/deliver.sh`

**Files:**
- Modify: `scripts/deliver.sh` (header lines 14–19 and 90–92, `STAGES` at 98, state at
  241–275, helpers at 289–423, `allowed_tools`, `write_scope`, `write_denied`,
  `context_block`, `preflight`, the `case` in the state machine, the closing logs)

**Interfaces:**
- Consumes: Task 1's scenarios.
- Produces:
  - `PROOF="$PLAN_DIR/04-proof.md"`
  - `EVIDENCE=build/acceptance`
  - `has_writer <stage>` — true unless the stage's pair is `acceptance`

- [ ] **Step 1: Stages, paths, state.**

```bash
STAGES=(plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer)
```

  After `GREEN_REPORT=`:

```bash
PROOF="$PLAN_DIR/04-proof.md"
# The acceptance-reviewer's screenshots, smoke packs and results: disposable, so
# under the ignored build/, outside every snapshot.
EVIDENCE=build/acceptance
```

  State defaults, replacing the matching lines:

```bash
ROUNDS_plan=1 ROUNDS_test=1 ROUNDS_code=1 ROUNDS_acceptance=1
FINAL_plan="$DELIVER_MAX_ROUNDS" FINAL_test="$DELIVER_MAX_ROUNDS" FINAL_code="$DELIVER_MAX_ROUNDS" FINAL_acceptance="$DELIVER_MAX_ROUNDS"
SENDBACKS_plan=0 SENDBACKS_test=0 SENDBACKS_code=0
SB_test_writer="" SB_test_reviewer="" SB_code_writer="" SB_code_reviewer="" SB_acceptance_reviewer=""
```

  `save_state`'s lines become:

```bash
        printf 'ROUNDS_plan=%q ROUNDS_test=%q ROUNDS_code=%q ROUNDS_acceptance=%q\n' \
            "$ROUNDS_plan" "$ROUNDS_test" "$ROUNDS_code" "$ROUNDS_acceptance"
        printf 'FINAL_plan=%q FINAL_test=%q FINAL_code=%q FINAL_acceptance=%q\n' \
            "$FINAL_plan" "$FINAL_test" "$FINAL_code" "$FINAL_acceptance"
        printf 'SENDBACKS_plan=%q SENDBACKS_test=%q SENDBACKS_code=%q\n' \
            "$SENDBACKS_plan" "$SENDBACKS_test" "$SENDBACKS_code"
        printf 'SB_test_writer=%q SB_test_reviewer=%q SB_code_writer=%q SB_code_reviewer=%q SB_acceptance_reviewer=%q\n' \
            "$SB_test_writer" "$SB_test_reviewer" "$SB_code_writer" "$SB_code_reviewer" "$SB_acceptance_reviewer"
```

- [ ] **Step 2: Helpers.**

```bash
SENDERS=(test-writer test-reviewer code-writer code-reviewer acceptance-reviewer)

# Every pair but acceptance has a writer. The acceptance-reviewer's findings are
# the code pair's to fix, so it sends back rather than asking for changes.
has_writer() { [ "$(pair_of "$1")" != acceptance ]; }
```

  `first_pass_turns`'s case:

```bash
        plan-*) printf 150 ;;
        test-writer | acceptance-reviewer) printf 200 ;;
        *) printf 250 ;;
```

  `default_model`'s case:

```bash
        test-writer | test-reviewer | code-writer | acceptance-reviewer) printf sonnet ;;
```

  `earlier_pair`'s case gains `acceptance) printf code ;;`.

- [ ] **Step 3: Reach and scope.** Add to `allowed_tools`, before `*)`:

```bash
        # Deploys the branch's preview and runs the smoke packs against it; its
        # feature pack and screenshots go under build/acceptance/, which the
        # write check never sees. No test runner: the code-writer's report says
        # what ran, and the packs are what it adds.
        acceptance-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(scripts/deploy.sh preview *)' 'Bash(scripts/smoke.sh *)'
            read_only_bash
            ;;
```

  Add to `write_scope`:

```bash
        acceptance-reviewer)
            printf '^%s/(04-proof\.md$|reviews/acceptance-reviewer-sendback-)' "$PLAN_DIR"
            ;;
```

  In `write_denied`, add `"$PROOF\$"` to the code-writer's alternatives, so the format
  becomes `'^(%s|%s|%s|%s|%s|%s|%s|%s)'` with the eight patterns.

- [ ] **Step 4: The context block.**
  - The red-report case becomes `test | code | acceptance)`.
  - The green-report line becomes:

```bash
    case "$pair" in
        code | acceptance) printf 'Green report: %s\n' "$GREEN_REPORT" ;;
    esac
```

  - The reviewer line becomes:

```bash
    if [ "$(role_of "$stage")" = reviewer ]; then
        if has_writer "$stage"; then
            printf 'Write your review to: %s\n' "$(review_path "$stage")"
        else
            printf 'Proof: %s\n' "$PROOF"
            printf 'Evidence: %s/\n' "$EVIDENCE"
        fi
    fi
```

- [ ] **Step 5: The verdicts.**
  - `reviewer:approved`'s check becomes:

```bash
            if has_writer "$STAGE"; then
                [ -s "$WORKTREE/$(review_path "$STAGE")" ] ||
                    die "$STAGE approved but wrote no $(review_path "$STAGE")"
            else
                [ -s "$WORKTREE/$PROOF" ] || die "$STAGE approved but wrote no $PROOF"
            fi
```

  - `reviewer:changes_requested` gains a first line:

```bash
            has_writer "$STAGE" || die "$STAGE has no writer to take changes — it sends back instead"
```

  - In `*:send_back`, the reviewer block's condition becomes
    `if [ "$(role_of "$STAGE")" = reviewer ] && has_writer "$STAGE"; then`, followed by:

```bash
            elif [ "$(role_of "$STAGE")" = reviewer ]; then
                # No writer to hand a review to; its own round still moves on,
                # so its return is a rework pass with a final round ahead.
                rounds=$(($(rounds_of "$pair") + 1))
                set_rounds "$pair" "$rounds"
                [ "$(final_of "$pair")" -gt "$rounds" ] || set_var "FINAL_$pair" $((rounds + 1))
```

  (it replaces the block's closing `fi`, and ends with its own `fi`).

- [ ] **Step 6: Pre-flight, closing logs, header.**
  - `preflight`'s list becomes
    `claude git jq uv node npm python3 helm docker cloudflared k3d kubectl curl`, with
    the comment line extended:
    `# … the acceptance-reviewer's preview (cloudflared, k3d, kubectl, curl).`
  - The closing logs become:

```bash
log "Issue #$ISSUE is ready for review: $WORKTREE, branch $BRANCH. Nothing is committed"
log "Start with $PROOF. Its preview is still up: BRANCH=$BRANCH scripts/deploy.sh preview url, and preview down when you're done"
```

  - Header changes:
    - "Six stages" becomes "Seven stages: a writer and a reviewer for each of plan,
      tests and code, then the acceptance-reviewer, which deploys the branch's preview
      and proves it there".
    - The diagram gains `-> acceptance-reviewer`.
    - Add: "The acceptance-reviewer has no writer: it approves, sends back to the
      code-writer, or stops. It leaves the preview running, and two deliveries at once
      are unsupported — both `preview up`s upgrade KEDA."
    - "Default: by stage" gains "and the acceptance-reviewer".
    - The `history.log` line adds "the proof in docs/plans/issue-<N>/04-proof.md, its
      evidence in build/acceptance/".

- [ ] **Step 7: Run the checks.**
  - Run: `bash -n scripts/deliver.sh && .claude/delivery/loop-test.sh`
  - Expected: `Every scenario passed.` — except that the scenarios ending at the seventh
    stage still pause with exit 3 until Task 5 writes the agent. To prove the state
    machine now, before Task 5, create a throwaway `.claude/agents/acceptance-reviewer.md`
    holding only its front matter (`name`, `description`, `tools: … StructuredOutput`,
    `model: sonnet`). Task 5 overwrites it.
  - Run: `.claude/delivery/loop-test.sh` → Expected: `Every scenario passed.`

---

### Task 3: `smoke.sh`'s red set

**Files:**
- Create: `src/services/testkit/tests/unit/test_smoke_script.py`

**Interfaces:**
- Produces the contract Task 4 builds:
  - `scripts/smoke.sh [--origin URL] [--out DIR] [paths…] [-- pytest args]`
  - It runs `uv run pytest -p smoke.fixtures tests/smoke <abs paths…>
    --junitxml=<out>/junit.xml <pytest args>` from the repo root.
  - The environment it passes: `SMOKE_ORIGIN`, `SMOKE_OUT` (absolute) and `PYTHONPATH`
    (starts with `<repo>/tests`).
  - Its exit status is pytest's.
  - With no `--origin`, it takes `APP_ORIGIN=` from `"${SMOKE_DEPLOY_SH:-scripts/deploy.sh}" preview url`.

- [ ] **Step 1: Write the failing tests.**

```python
"""`scripts/smoke.sh` — its arguments, and where it finds the origin.

Each test runs the real script under `/bin/bash` (3.2 on macOS) with an environment built
from nothing, a fake `uv` on `PATH` that records what it was run with, and — for the
default origin — a fake `deploy.sh` through `SMOKE_DEPLOY_SH`. Nothing reaches the network,
a browser or a cluster: what pytest would do with the pack is the pack's own business.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
SCRIPT = REPO / "scripts" / "smoke.sh"
BASH = "/bin/bash"

# Records its arguments, one per line, its working directory and the three variables
# smoke.sh passes, then exits FAKE_UV_EXIT.
FAKE_UV = """#!/bin/bash
printf '%s\\n' "$@" >"$FAKE_UV_LOG.args"
printf '{"cwd": "%s", "origin": "%s", "out": "%s", "pythonpath": "%s"}\\n' \\
    "$PWD" "$SMOKE_ORIGIN" "$SMOKE_OUT" "$PYTHONPATH" >"$FAKE_UV_LOG.env"
exit "${FAKE_UV_EXIT:-0}"
"""

FAKE_DEPLOY = """#!/bin/bash
printf '%s\\n' "$*" >>"$FAKE_DEPLOY_LOG"
[ "${FAKE_DEPLOY_EXIT:-0}" = 0 ] || { echo "preview's tunnels are not running" >&2; exit 1; }
printf 'APP_ORIGIN=https://quick-fake-tunnel.trycloudflare.com\\n'
printf 'OBJECT_STORE_ORIGIN=https://other-fake-tunnel.trycloudflare.com\\n'
"""


class Run:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for name, body in (("uv", FAKE_UV), ("deploy.sh", FAKE_DEPLOY)):
            path = bin_dir / name
            path.write_text(body)
            path.chmod(0o755)
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp),
            "FAKE_UV_LOG": str(tmp / "uv"),
            "FAKE_DEPLOY_LOG": str(tmp / "deploy.log"),
            "SMOKE_DEPLOY_SH": str(bin_dir / "deploy.sh"),
        }

    def __call__(self, *args: str, cwd: Path = REPO, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            cwd=cwd,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def uv_args(self) -> list[str]:
        return (self.tmp / "uv.args").read_text().splitlines()

    def uv_env(self) -> dict[str, str]:
        return json.loads((self.tmp / "uv.env").read_text())

    def uv_ran(self) -> bool:
        return (self.tmp / "uv.args").exists()


@pytest.fixture
def run(tmp_path: Path) -> Run:
    return Run(tmp_path)


def test_runs_the_standard_pack_against_the_origin(run: Run, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = run("--origin", "https://example.test", "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert run.uv_args() == [
        "run", "pytest", "-p", "smoke.fixtures", "tests/smoke", f"--junitxml={out}/junit.xml",
    ]
    env = run.uv_env()
    assert env["cwd"] == str(REPO)
    assert env["origin"] == "https://example.test"
    assert env["out"] == str(out)
    assert env["pythonpath"].split(":")[0] == str(REPO / "tests")
    assert out.is_dir()


def test_a_trailing_slash_is_dropped(run: Run, tmp_path: Path) -> None:
    run("--origin", "http://localhost:8080/", "--out", str(tmp_path / "o"))
    assert run.uv_env()["origin"] == "http://localhost:8080"


@pytest.mark.parametrize("origin", ["localhost:8080", "ftp://example.test", "https://"])
def test_an_origin_that_is_not_http_is_refused(run: Run, tmp_path: Path, origin: str) -> None:
    result = run("--origin", origin, "--out", str(tmp_path / "o"))
    assert result.returncode != 0
    assert "http" in result.stderr
    assert not run.uv_ran()


def test_extra_paths_are_made_absolute(run: Run, tmp_path: Path) -> None:
    caller = tmp_path / "caller"
    (caller / "pack").mkdir(parents=True)
    run("--origin", "https://example.test", "--out", str(tmp_path / "o"), "pack", cwd=caller)
    args = run.uv_args()
    assert args[4:6] == ["tests/smoke", str(caller / "pack")]


def test_a_relative_out_is_under_the_repo(run: Run) -> None:
    run("--origin", "https://example.test", "--out", "build/smoke-unit-test")
    try:
        assert run.uv_env()["out"] == str(REPO / "build" / "smoke-unit-test")
    finally:
        (REPO / "build" / "smoke-unit-test").rmdir()


def test_arguments_after_a_double_dash_go_to_pytest(run: Run, tmp_path: Path) -> None:
    run("--origin", "https://example.test", "--out", str(tmp_path / "o"), "--", "-k", "sign_in")
    assert run.uv_args()[-2:] == ["-k", "sign_in"]


def test_exits_with_pytest_status(run: Run, tmp_path: Path) -> None:
    result = run("--origin", "https://example.test", "--out", str(tmp_path / "o"), FAKE_UV_EXIT="1")
    assert result.returncode == 1
    assert "junit.xml" in result.stderr


def test_no_origin_takes_this_branch_preview(run: Run, tmp_path: Path) -> None:
    result = run("--out", str(tmp_path / "o"))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "deploy.log").read_text().strip() == "preview url"
    assert run.uv_env()["origin"] == "https://quick-fake-tunnel.trycloudflare.com"


def test_no_preview_names_preview_up_and_runs_nothing(run: Run, tmp_path: Path) -> None:
    result = run("--out", str(tmp_path / "o"), FAKE_DEPLOY_EXIT="1")
    assert result.returncode != 0
    assert "preview up" in result.stderr
    assert not run.uv_ran()


def test_an_unknown_option_is_refused(run: Run) -> None:
    result = run("--origni", "https://example.test")
    assert result.returncode != 0
    assert "--origni" in result.stderr
    assert not run.uv_ran()
```

- [ ] **Step 2: Run it and record the red.**

  Run: `uv run pytest src/services/testkit/tests/unit/test_smoke_script.py -q`

  Expected: every test FAILs. `/bin/bash` can't open `scripts/smoke.sh`, so each one
  fails on its own exit status, or on `FileNotFoundError` for `uv.args`. None of them
  fails at load.

- [ ] **Step 3: STOP at red** for the user to review the tests.

---

### Task 4: `smoke.sh`, the fixtures plugin and the standard pack

**Files:**
- Create: `scripts/smoke.sh` (executable)
- Create: `tests/smoke/__init__.py` (empty)
- Create: `tests/smoke/fixtures.py`
- Create: `tests/smoke/test_platform.py`
- Modify: `pyproject.toml` — `testpaths`

**Interfaces:**
- Consumes: Task 3's contract.
- Produces the fixtures a pack may use:
  - `origin: str`
  - `out_dir: Path`
  - `run_id: str` — `smoke-YYYYMMDD-HHMMSS`, UTC
  - `ada: ChatPage` — signed in, in the shared workspace, app open
  - `shot(page: Page, name: str) -> Path`
  - `api: APIRequestContext` — unauthenticated, rooted at the origin
  - `ADA`, `SHARED_WORKSPACE`, and `PNG`, a 1×1 image's bytes

- [ ] **Step 1: `scripts/smoke.sh`.**

```bash
#!/usr/bin/env bash
# Smoke-test a running CollabHub through its public origin, and nothing else.
#
#   scripts/smoke.sh                               this branch's preview
#   scripts/smoke.sh --origin http://localhost:8080   k3d, or any deploy
#   scripts/smoke.sh --out build/acceptance/feature build/acceptance/smoke
#                                                  another pack, run beside tests/smoke
#   scripts/smoke.sh -- -k sign_in                 anything after -- goes to pytest
#
# The packs are pytest + Playwright, with the fixtures in tests/smoke/fixtures.py
# loaded as a plugin, so a pack anywhere gets them. They are non-destructive: they
# reach the app only through the origin, and name anything they create with the
# run's id — safe against a preview someone is using.
#
#   --origin  default: APP_ORIGIN from `scripts/deploy.sh preview url`
#   --out     JUnit XML and screenshots/. Default: build/smoke. Never
#             docs/test-report.md, which is scripts/test.sh's.
#
# Exit status: pytest's.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

origin=""
out=build/smoke
paths=()
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --origin)
            [ $# -ge 2 ] || die "--origin needs a URL"
            origin="$2"
            shift
            ;;
        --out)
            [ $# -ge 2 ] || die "--out needs a directory"
            out="$2"
            shift
            ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) die "unknown option '$1'" ;;
        *)
            # Absolute now: pytest runs from the repo root, not from here.
            case "$1" in
                /*) paths+=("$1") ;;
                *) paths+=("$PWD/$1") ;;
            esac
            ;;
    esac
    shift
done

if [ -z "$origin" ]; then
    # A seam for the unit tests; nothing else sets it.
    preview="$("${SMOKE_DEPLOY_SH:-$REPO_ROOT/scripts/deploy.sh}" preview url)" ||
        die "no live preview for this branch — run scripts/deploy.sh preview up, or pass --origin"
    origin="$(printf '%s\n' "$preview" | sed -n 's/^APP_ORIGIN=//p')"
    [ -n "$origin" ] || die "scripts/deploy.sh preview url printed no APP_ORIGIN"
fi
origin="${origin%/}"
case "$origin" in
    http://?* | https://?*) ;;
    *) die "--origin must be an http:// or https:// URL, got '$origin'" ;;
esac

case "$out" in
    /*) ;;
    *) out="$REPO_ROOT/$out" ;;
esac
mkdir -p "$out"

log "smoke packs against $origin"
status=0
(cd "$REPO_ROOT" &&
    SMOKE_ORIGIN="$origin" SMOKE_OUT="$out" PYTHONPATH="$REPO_ROOT/tests${PYTHONPATH:+:$PYTHONPATH}" \
        uv run pytest -p smoke.fixtures tests/smoke ${paths[@]+"${paths[@]}"} \
        --junitxml="$out/junit.xml" ${pytest_args[@]+"${pytest_args[@]}"}) || status=$?
if [ "$status" = 0 ]; then
    log "smoke packs passed — $out/junit.xml, screenshots in $out/screenshots/"
else
    log "smoke packs failed (pytest exit $status) — $out/junit.xml, screenshots in $out/screenshots/"
fi
exit "$status"
```

  Run: `chmod +x scripts/smoke.sh && uv run pytest src/services/testkit/tests/unit/test_smoke_script.py -q`
  Expected: PASS, all of them.

- [ ] **Step 2: Stop a plain `uv run pytest` collecting the packs.** In `pyproject.toml`:

```toml
# `tests/bdd` is the Gherkin suite at the repo root; without it here the .feature
# files are simply not collected. `tests/smoke` is left out on purpose: it needs
# a running deploy's origin, and scripts/smoke.sh names it.
testpaths = ["src/services", "tests/bdd"]
```

- [ ] **Step 3: `tests/smoke/fixtures.py`.**

```python
"""Fixtures for the smoke packs: a running CollabHub, reached only through its origin.

`scripts/smoke.sh` loads this with `-p smoke.fixtures`, so a pack anywhere — the standard
one beside it, or a feature's under `build/acceptance/` — gets the same fixtures. It sets
`SMOKE_ORIGIN` and `SMOKE_OUT`; run any other way, the session stops at once.

**Non-destructive, by rule.** Unlike `tests/bdd`, nothing here reaches a database, a
Compose port or anything but the origin, and nothing is truncated. A test creates only
what it names with `run_id`, so a pack is safe against a preview someone is using.

Sign-in goes through the real flow with the `bdd.pages` page objects, once per session
into a context that stays alive — `tests/bdd/conftest.py` explains why a saved
`storage_state` would sign the user out.
"""

from __future__ import annotations

import base64
import os
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import APIRequestContext, Browser, BrowserContext, Page, Playwright

from bdd.pages.chat_page import ChatPage
from bdd.pages.sign_in_page import SignInPage

ADA = "ada@collabhub.dev"
SHARED_WORKSPACE = os.environ.get("AUTH_DEMO_WORKSPACE_NAME", "CollabHub Demo")

#: A 1×1 transparent PNG, for a pack that uploads an image.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture(scope="session")
def origin() -> str:
    value = os.environ.get("SMOKE_ORIGIN", "").rstrip("/")
    if not value:
        pytest.exit("SMOKE_ORIGIN is not set — run the smoke packs with scripts/smoke.sh", returncode=4)
    return value


@pytest.fixture(scope="session")
def out_dir() -> Path:
    path = Path(os.environ.get("SMOKE_OUT", "build/smoke"))
    (path / "screenshots").mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def run_id() -> str:
    """A prefix for everything a run creates — a channel name is a letter, then letters, digits and dashes."""
    return time.strftime("smoke-%Y%m%d-%H%M%S", time.gmtime())


@pytest.fixture(scope="session")
def api(playwright: Playwright, origin: str) -> Iterator[APIRequestContext]:
    """Unauthenticated requests to the origin, as anyone on the internet could make them."""
    context = playwright.request.new_context(base_url=origin)
    yield context
    context.dispose()


@pytest.fixture(scope="session")
def ada_context(browser: Browser, origin: str) -> Iterator[BrowserContext]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    sign_in = SignInPage(page, origin)
    sign_in.sign_in(ADA)
    sign_in.use_workspace(SHARED_WORKSPACE)
    page.close()
    yield context
    context.close()


@pytest.fixture
def ada(ada_context: BrowserContext, origin: str) -> Iterator[ChatPage]:
    page = ada_context.new_page()
    chat = ChatPage(page, origin)
    chat.open()
    yield chat
    page.close()


@pytest.fixture
def shot(request: pytest.FixtureRequest, out_dir: Path) -> Callable[[Page, str], Path]:
    """Save a full-page screenshot, named after the test, to `<out>/screenshots/`."""

    def take(page: Page, name: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{request.node.name}-{name}".lower()).strip("-")
        path = out_dir / "screenshots" / f"{slug}.png"
        page.screenshot(path=str(path), full_page=True)
        return path

    return take
```

- [ ] **Step 4: `tests/smoke/test_platform.py`, the standard pack.**

```python
"""The standard smoke pack: what every deploy of CollabHub must do, seen from outside.

Run after any deploy with `scripts/smoke.sh`. It proves the routing, the identity flow,
the real-time path to Messaging's database and back, and object storage's own origin —
what a new environment most often gets wrong — and leaves a screenshot of each.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import APIRequestContext, Browser, Page, expect
from smoke.fixtures import PNG, SHARED_WORKSPACE

from bdd.pages.chat_page import ChatPage

Shot = Callable[[Page, str], Path]


def test_the_app_loads_without_errors(browser: Browser, origin: str, shot: Shot) -> None:
    context = browser.new_context()
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(origin)
        expect(page.get_by_test_id("sign-in")).to_be_visible()
        shot(page, "signed-out")
        assert errors == []
    finally:
        context.close()


def test_the_signing_keys_are_published(api: APIRequestContext) -> None:
    response = api.get("/.well-known/jwks.json")
    assert response.ok, response.status
    keys = response.json()["keys"]
    assert keys
    assert all(key["kty"] == "RSA" for key in keys)


def test_the_internal_api_is_not_routed(api: APIRequestContext) -> None:
    """D40: the Ingress's allow-list sends /api/v1/internal/ to the SPA, never a service."""
    response = api.get("/api/v1/internal/channels")
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/html"), content_type


def test_ada_signs_in_to_the_shared_workspace(ada: ChatPage, shot: Shot) -> None:
    assert ada.workspace_name() == SHARED_WORKSPACE
    shot(ada.page, "workspace")


def test_a_message_survives_a_reload(ada: ChatPage, run_id: str, shot: Shot) -> None:
    channel, text = f"{run_id}-chat", f"{run_id} hello from the smoke pack"
    ada.create_channel_and_wait(channel)
    ada.send_message_and_wait(text)

    ada.open()
    ada.open_channel(channel)
    assert ada.has_message(text)
    shot(ada.page, "after-reload")


def test_an_image_round_trips_through_object_storage(ada: ChatPage, run_id: str, shot: Shot) -> None:
    channel, text = f"{run_id}-files", f"{run_id} an image"
    ada.create_channel_and_wait(channel)
    ada.attach_files([{"name": "smoke.png", "mimeType": "image/png", "buffer": PNG}])
    ada.send_message_and_wait(text)
    assert ada.has_inline_image(text, "smoke.png")
    shot(ada.page, "image")
```

- [ ] **Step 5: Prove the pack fails when it should.** Nothing listens on port 9.
  - Run: `scripts/smoke.sh --origin http://localhost:9 --out build/smoke-red`
  - Expected: exit 1. Every test fails or errors with a connection refusal; none passes.
  - Then: `rm -r build/smoke-red`

- [ ] **Step 6: Prove the pack passes on k3d.**
  - Run: `scripts/deploy.sh up` (if k3d isn't already up), then
    `scripts/smoke.sh --origin http://localhost:8080 --out build/smoke-k3d`
  - Expected: `6 passed`, and four PNGs in `build/smoke-k3d/screenshots/`. Open one to
    check it shows the app.
  - If `ada.workspace_name()` differs, read the actual name from the screenshot and the
    Auth chart's values. Fix the default, not the test.

- [ ] **Step 7: Prove the pack passes on a preview.**
  - Run: `scripts/deploy.sh preview up`, then `scripts/smoke.sh --out build/smoke-preview`
  - Expected: `6 passed`. Then `scripts/deploy.sh preview down`.

- [ ] **Step 8:** `uv run ruff check tests/smoke src/services/testkit/tests/unit/test_smoke_script.py`
  and `uv run ruff format --check` on the same paths → clean.

---

### Task 5: The agent — `.claude/agents/acceptance-reviewer.md`

**Files:**
- Create (or overwrite Task 2's stub): `.claude/agents/acceptance-reviewer.md`

**Interfaces:**
- Consumes:
  - the context-block lines from Task 2
  - `scripts/smoke.sh` and the fixtures from Task 4
  - `scripts/deploy.sh preview up|url`

- [ ] **Step 1: Write the agent.** Full content:

````markdown
---
name: acceptance-reviewer
description: Deploys the approved build to this branch's preview environment, proves it there with the standard smoke pack and a feature pack it writes, checks the issue's acceptance criteria and the delivery's record, and writes docs/plans/issue-<N>/04-proof.md for a human to accept from. Last stage of scripts/deliver.sh, after code-reviewer. Approves, sends back to the code-writer, or stops for a human. Never edits code, tests or docs but its proof.
tools: Read, Grep, Glob, Write, Edit, Skill, Bash, StructuredOutput
model: sonnet
---

You are the **acceptance-reviewer** on CollabHub's delivery team: the last stage. Three
reviewers have already read the plan, the tests and the code. You are the first to see the
feature **running**, and what you write is what a person reads to accept the branch — and,
later, what its pull request is made from. Your job is to show them, with evidence, that
the issue is met where it can be seen, and to hand them everything the team left for a human.

Not a fourth code review. You don't re-review the code, re-run the unit or integration
suites, or mutate anything: the green report and the code review say what ran.

**Read `.claude/delivery/agent-context.md` first.** It is the team's shared context: how
you are run, what you may touch, sending work back, stopping for a human, and the
`StructuredOutput` result.

**You write one tracked file: the proof, at the `Proof:` path** — and, if you send work
back, the `Send-back file`. Everything else you make — the feature pack, screenshots,
results — goes under the `Evidence:` directory, `build/acceptance/`, which git ignores and
the workflow never checks. Write there with Write, not Bash.

## What you may run

- `scripts/deploy.sh preview up` — builds, pushes and deploys this branch to its own
  namespace on k3d, behind two cloudflared quick tunnels, and checks the SPA and the JWKS
  answer through the Ingress. It prints `APP_ORIGIN=` and `OBJECT_STORE_ORIGIN=` last.
  It takes minutes; run it once, in the foreground.
- `scripts/deploy.sh preview url` — the live origins again.
- `scripts/smoke.sh --out <dir> [pack paths…] [-- pytest args]` — the smoke packs against
  this branch's preview. `tests/smoke` always runs; a path you give runs beside it.
- The read-only git commands every stage has.

Never `preview down`: the preview is left up for the human.

## 1. The record

Read, all at once: the issue (its acceptance criteria, its *Decided already*), the plan's
decisions table, the red and green reports, and every file under `Earlier reviews:`.
Collect, each with where it came from:

- every **assumed** decision in the plan;
- every *Departures from the plan* in the red and green reports;
- every *Left for the human* and *Left for later stages* in a review, still open;
- anything the record contradicts itself on — a report claiming a test the branch doesn't
  have, a decision the code went the other way on.

Then list the issue's acceptance criteria, one line each, and mark each **visible** (a
person could see it in the running app or at its public API) or **internal** (a stored
column, a log line, a job — only a test can show it). For an internal one, find the test in
the branch that proves it, by file and name.

## 2. The preview

Run `scripts/deploy.sh preview up`. Take `APP_ORIGIN` from its last lines.

- **It fails on something the branch changed** — a chart, a Dockerfile, a migration, a
  service that won't start — that is the code pair's: **send back**, with the output.
- **It fails on something outside the branch** — Docker, k3d, cloudflared, Cloudflare —
  run it once more. Failing again, **stop for a human**: the environment is broken.

## 3. The standard pack

`scripts/smoke.sh --out build/acceptance/standard`. Six tests: the app loads, the keys
are published, the internal API isn't routed, Ada signs in, a message survives a reload,
an image round-trips through object storage. A failure the branch could have caused is a
send-back; one it can't (a step that failed on `main` too) goes in the proof as such.

## 4. The feature pack

Write `build/acceptance/smoke/test_issue_<N>.py`: **one test per visible criterion**, named
after it, ending with `shot(page, "<what it shows>")` on the state that proves it. Use the
fixtures in `tests/smoke/fixtures.py` and the page objects in `tests/bdd/pages/` — read
both first. A page object without the method you need: drive the `Page` directly in your
test, by `data-testid`. Two users: open a second context from `browser` and sign in with
`SignInPage` as `grace@collabhub.dev`.

- **Non-destructive.** Through the origin only; name everything you create with `run_id`.
- **Prove the server.** The last check after a write is a reload, or the other user's
  window — not the optimistic row.
- **Screenshots a person can read.** The feature in view, nothing cut off.

Run it: `scripts/smoke.sh --out build/acceptance/feature build/acceptance/smoke`. A test
that fails: read the screenshot and the error before deciding. Your test wrong — fix it and
rerun. The feature wrong — that criterion fails.

## 5. The verdict

- **`approved`** — every visible criterion passed on the preview, every internal one has
  its test, and the standard pack passed. Anything else you found goes in the proof under
  *For the human*: approval means "ready for a person to accept", not "nothing to say".
- **`send_back`** — a criterion fails on the preview, or the standard pack fails, because
  of the branch. Write the send-back file: the criterion, what you did, what you saw (the
  error, the screenshot's path), and the smallest fix you'd expect. Write the proof too,
  verdict *sent back*, so the next pass has your evidence. The code-writer gets it; if the
  fault is in a test or the plan, it carries it back.
- **`needs_human`** — only what the shared context lists: the preview broken outside the
  branch twice, or a criterion that can't be judged without a 🔴 decision.

A finding that isn't a failure — a rough edge, an inconsistency in the record, a criterion
met in a way a person might not expect — is never a send-back. It goes under *For the human*.

## A rework pass

After your own send-back, the code pair has changed the branch. Run `preview up` again (it
reuses live tunnels), rerun both packs, check the criterion you sent back for, and rewrite
the proof. Don't rewrite tests for criteria the change can't reach.

## The proof

At the `Proof:` path, in this shape — sections a pull request can lift whole. Screenshot
links are relative to the proof's own directory, so `../../../build/acceptance/…`.

```markdown
# Issue #<N> — acceptance proof: <accepted | sent back | needs a human>

## Summary
3–5 bullets: what the feature does, as seen running. Written for a reviewer, not the team.

## Try it
- Origin: <APP_ORIGIN> — sign in as ada@collabhub.dev / collabhub (grace@collabhub.dev too)
- Quick-tunnel URLs die with cloudflared: `BRANCH=<branch> scripts/deploy.sh preview url`, or `preview up` for new ones
- Take it down: `BRANCH=<branch> scripts/deploy.sh preview down`

## Acceptance criteria
| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|

## Preview
Branch, commit (`git log -1 --format=%h`), namespace, deploy outcome, origin checks.

## Standard smoke pack
Passed / failed / skipped; each failure and what it printed.

## Feature smoke pack
Each test: what it does, what it shows, its result.

## Screenshots
[build/acceptance/](../../../build/acceptance/) — listed by test. Disposable: the PR uploads them.

## For the human
Assumed decisions, departures, and every open *Left for the human* / *Left for later
stages*, each with where it came from. Then anything you found.

## The run
Each stage's line from build/delivery/history.log.
```

## What you return

`StructuredOutput`, as the shared context says. `status`: `approved`, `send_back` or
`needs_human` — never `changes_requested`, which the workflow refuses from you. `summary`:
the verdict, the origin, and visible criteria proven out of the total. `files`: the proof,
and the send-back file if you wrote one.
````

- [ ] **Step 2:** Run `.claude/delivery/loop-test.sh` → `Every scenario passed.` (it reads
  the agent's front matter for `ran_with`).

---

### Task 6: The shared context and `CLAUDE.md`

**Files:**
- Modify: `.claude/delivery/agent-context.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: `agent-context.md`.**
  - "One issue goes through six stages, a writer and a reviewer for each of plan, tests
    and code:" becomes "One issue goes through seven stages: a writer and a reviewer for
    each of plan, tests and code, then the acceptance-reviewer:".
  - The team table gains a row:

```markdown
| **acceptance-reviewer** | deploys the branch's preview, runs the smoke packs, checks the issue's criteria and the record | `docs/plans/issue-<N>/04-proof.md`, and its evidence under the ignored `build/acceptance/` |
```

  - The context-block list gains:

```markdown
- `Proof:`, `Evidence:` — the acceptance-reviewer: where its proof goes, and the ignored
  directory for everything else it makes.
```

    and `Green report:`'s line changes "the code pair" to "the code pair and the
    acceptance-reviewer".
  - In *Sending work back*, "Code stages send back to the test-writer, test stages to the
    plan-writer." becomes "The acceptance-reviewer sends back to the code-writer, code
    stages to the test-writer, test stages to the plan-writer."
  - In *What you return*, the status bullet gains "the acceptance-reviewer returns
    `approved`, `send_back` or `needs_human` — it has no writer to take
    `changes_requested`".

- [ ] **Step 2: `CLAUDE.md`.**
  - *Delivery workflow*'s first paragraph: "through six agents … plan-writer →
    plan-reviewer → test-writer → test-reviewer → code-writer → code-reviewer" becomes
    "through seven agents … → code-reviewer → acceptance-reviewer".
  - After "…with its reasons in a send-back file under `reviews/`;", add: "the
    acceptance-reviewer deploys the branch's preview, runs `scripts/smoke.sh` against it,
    and writes `docs/plans/issue-<N>/04-proof.md` — the record a person accepts from —
    leaving the preview up;".
  - The model line becomes "The plan pair and the code-reviewer run on Opus, the test
    pair, the code-writer and the acceptance-reviewer on Sonnet".
  - *Repo layout*: under `tests/bdd/`, add
    `tests/smoke/             # smoke packs against a running deploy's origin — scripts/smoke.sh`.
    The `scripts/` line becomes "build.sh, test.sh, deploy.sh, smoke.sh".
  - *Testing*: after the `scripts/test.sh all` line in the code block, add:

```bash
scripts/smoke.sh --origin http://localhost:8080   # smoke packs against a running deploy
scripts/smoke.sh                 # …against this branch's preview
```

    and after the BDD paragraphs, add: "**`tests/smoke` is not a test layer.** It proves
    a deploy, not a rule: non-destructive, through the origin only, and never collected
    by `scripts/test.sh` or a plain `uv run pytest`. A feature's own pack is written by
    the acceptance-reviewer under `build/acceptance/` and thrown away."

---

### Task 7: The first real run — with the user

**Files:**
- Create: `docs/plans/ch09/03-acceptance-reviewer-handoff.md`

This spends money and takes about 80 minutes. **Ask the user before starting it.**

- [ ] **Step 1:** In the primary checkout, with this branch's delivery files copied over
  a fresh worktree (as `docs/plans/ch08/04-team-review-handoff.md` describes), run
  `scripts/deliver.sh docs/issues/007.md`.
- [ ] **Step 2:** Read the resulting `04-proof.md` and `build/acceptance/`. Open the
  preview's origin.
- [ ] **Step 3:** Write the handoff: the run's `history.log` lines, the acceptance stage's
  time, turns and cost; what the proof got right and wrong; whether Sonnet was enough;
  what the PR step should lift.
