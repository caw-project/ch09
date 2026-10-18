"""What each stage runs on and may do: its model, effort and turns, its tools, where it may
write. The tool and write rules are the safety boundary — `tests/unit/fixtures/
deliver-rules.json` holds them as the bash `deliver.sh` had them, and they must stay equal.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from delivery.run.keys import Paths
from delivery.run.machine import is_final_round, is_rework, writer_output
from delivery.run.settings import Settings
from delivery.run.state import State

__all__ = [
    "allowed_tools",
    "effort_for",
    "first_pass_turns",
    "model_for",
    "ran_with_model",
    "strays",
    "turns_for",
    "write_denied",
    "write_scope",
    "writer_output",
]

# --- model, effort, turns ------------------------------------------------------


def first_pass_turns(stage: str, settings: Settings) -> int:
    """A first pass's cap by stage: the stages that run tests and builds take more turns
    than the ones that read and write. Measured on issue 1: plan pair 58 to 71, test-writer
    93 to 103, test-reviewer 64 to 146, code-writer 108 to 128, code-reviewer 78 to 103."""
    if settings.max_turns is not None:
        return settings.max_turns
    if stage.startswith("plan-"):
        return 150
    if stage in ("test-writer", "acceptance-reviewer"):
        return 200
    return 250


def turns_for(stage: str, state: State, settings: Settings) -> int:
    if is_final_round(stage, state):
        return settings.final_max_turns
    if is_rework(stage, state):
        return settings.rework_max_turns
    return first_pass_turns(stage, settings)


def default_model(stage: str) -> str:
    """The model each stage runs on when nothing is set, or "" for its agent's own.

    Measured on issue 1 (docs/plans/ch08/05-model-effort-handoff.md): Sonnet for the test
    pair and the code-writer is a fifth faster and a third cheaper with no difference a
    blind judge could find; a Sonnet plan-writer builds a weaker design, and the
    code-reviewer is the last code gate. The acceptance-reviewer mostly runs and records,
    like the Sonnet stages — not yet measured. Keep the agents' `model:` lines in step.
    """
    return "sonnet" if stage in SONNET else ""


SONNET = ("test-writer", "test-reviewer", "code-writer", "acceptance-reviewer")


def model_for(stage: str, state: State, settings: Settings) -> str:
    """The model a stage runs on this pass, or "" for its agent's own. A final round is a
    rework pass too, so the rework model reaches it."""
    model = settings.stage_model(stage) or settings.model or default_model(stage)
    if settings.rework_model and (is_rework(stage, state) or is_final_round(stage, state)):
        model = settings.rework_model
    return model


def effort_for(stage: str, state: State, settings: Settings) -> str:
    """The effort a stage runs at this pass, or "" for the model's own. The final round's
    is cut down whatever a rework pass would get."""
    effort = settings.stage_effort(stage) or settings.effort
    if is_final_round(stage, state):
        effort = settings.final_effort
    elif settings.rework_effort and is_rework(stage, state):
        effort = settings.rework_effort
    return effort


def ran_with_model(model: str, agent_file: Path) -> str:
    """The model passed, else the one the agent's file names, else "default"."""
    if model:
        return model
    try:
        for line in agent_file.read_text().splitlines():
            if line.startswith("model:"):
                return line.removeprefix("model:").strip() or "default"
    except OSError:
        pass
    return "default"


# --- tools ---------------------------------------------------------------------
#
# In dontAsk mode a tool not listed is refused, so a stage's list is its whole reach.

BASE = ("Read", "Grep", "Glob", "Write", "Edit", "Skill")

#: Looking around the repo and its history — every stage has these.
READ_ONLY_BASH = (
    "Bash(git log *)",
    "Bash(git show *)",
    "Bash(git diff *)",
    "Bash(git status *)",
    "Bash(git worktree list*)",
    "Bash(git branch *)",
    "Bash(git merge-base *)",
    "Bash(ls *)",
    "Bash(wc *)",
)

#: Running tests one file at a time. Never scripts/test.sh: it rewrites the committed
#: docs/test-report.md, and runs every layer when a stage needs one file. Nothing here
#: can reach the e2e stack.
TEST_BASH = (
    "Bash(npm --prefix src/frontend test*)",
    "Bash(npm --prefix src/frontend run typecheck*)",
    "Bash(npm --prefix src/frontend run lint*)",
    "Bash(uv run pytest *)",
    "Bash(uv sync*)",
)

#: The static checks scripts/test.sh's lint layer runs, one at a time, for a stage that
#: changes or reviews Python, a chart or a script. `ruff format` only with --check for a
#: reviewer: without it, it writes.
CHECK_BASH = (
    "Bash(uv run ruff check *)",
    "Bash(uv run ruff format --check *)",
    "Bash(helm lint *)",
    "Bash(helm template *)",
    "Bash(bash -n *)",
    "Bash(python3 .claude/hooks/checks/conventions.py*)",
)

#: Taking a file out of the tree. The write check sees a deletion as it sees a write, so
#: each writer can only remove what it could have written.
REMOVE_BASH = (
    "Bash(rm src/*)",
    "Bash(rm tests/*)",
    "Bash(rm docs/*)",
    "Bash(rm charts/*)",
    "Bash(rm docker/*)",
    "Bash(rm scripts/*)",
)

TOOLS: dict[str, tuple[str, ...]] = {
    "plan-writer": (*BASE, *READ_ONLY_BASH),
    # Edit is for its own review, written in two goes — expectations, then the rest. The
    # write check holds it to that file.
    "plan-reviewer": (*BASE, *READ_ONLY_BASH),
    # The first stage that runs anything, so the first that installs: a worktree has no
    # node_modules/ or .venv/ until it does (both ignored, so the write check never sees
    # them). `npm ci`, never `npm install`, which rewrites the lockfile. No sketch: proving
    # a test against a throwaway build is the test-reviewer's, which found the gaps anyway
    # and cost the writer ten minutes a run when it did it too.
    "test-writer": (
        *BASE,
        "Bash(npm --prefix src/frontend ci*)",
        "Bash(uv run ruff *)",
        *READ_ONLY_BASH,
        *TEST_BASH,
        *REMOVE_BASH,
    ),
    # Runs the tests to see them fail, and writes only its review. Edit and the sketch are
    # for a throwaway implementation under build/sketch/, which is ignored — the write
    # check still holds it to its review.
    "test-reviewer": (
        *BASE,
        "Bash(.claude/delivery/sketch.sh *)",
        *READ_ONLY_BASH,
        *TEST_BASH,
    ),
    # Builds until the tests pass, then verifies the whole branch: the only stage that
    # runs scripts/test.sh, because its final run writes the committed
    # docs/test-report.md that goes with the code. e2e brings up the Compose test stack,
    # one run per machine at a time. The contract regeneration is here for an issue that
    # changes an API, and the installs for one that adds a dependency.
    "code-writer": (
        *BASE,
        "Bash(npm --prefix src/frontend ci*)",
        "Bash(npm --prefix src/frontend install *)",
        "Bash(npm --prefix src/frontend run build*)",
        "Bash(npm --prefix src/frontend run generate:api*)",
        "Bash(uv run ruff *)",
        "Bash(uv run alembic *)",
        "Bash(uv run python -m *)",
        "Bash(uv add *)",
        "Bash(uv lock*)",
        "Bash(scripts/test.sh *)",
        "Bash(.claude/hooks/security.sh*)",
        *READ_ONLY_BASH,
        *TEST_BASH,
        *CHECK_BASH,
        *REMOVE_BASH,
    ),
    # Runs every check but scripts/test.sh, whose layers it reads from the report the
    # code-writer left, and writes only its review. The sketch is the real code copied
    # under build/sketch/, broken on purpose to see which mistakes the tests would catch.
    "code-reviewer": (
        *BASE,
        "Bash(.claude/delivery/sketch.sh *)",
        "Bash(npm --prefix src/frontend run build*)",
        *READ_ONLY_BASH,
        *TEST_BASH,
        *CHECK_BASH,
    ),
    # Runs the smoke packs against the preview the workflow deployed; its feature pack and
    # screenshots go under build/acceptance/, which the write check never sees. `preview
    # url` only — never up, which the workflow runs, or down, which is the human's. No
    # test runner: the code-writer's report says what ran, and the packs are what it adds.
    "acceptance-reviewer": (
        *BASE,
        "Bash(scripts/deploy.sh preview url)",
        "Bash(scripts/smoke.sh *)",
        *READ_ONLY_BASH,
    ),
}


def allowed_tools(stage: str) -> list[str]:
    try:
        return list(TOOLS[stage])
    except KeyError:
        raise LookupError(
            f"no tools are allowed for {stage} yet — add its entry to TOOLS"
        ) from None


# --- where a stage may write -----------------------------------------------------
#
# Extended regexes over paths relative to the worktree root, checked after the stage
# runs. The strings are the bash ones, quirks included: the fixture holds them.

TESTS = (
    r"src/frontend/src/.*\.test\.tsx?$",
    "src/frontend/src/test/",
    "src/services/[^/]+/tests/",
    "src/services/testkit/",
)


def write_scope(stage: str, paths: Paths) -> str | None:
    """Where a stage may write; None means it is not confined."""
    plans = paths.plan_dir
    if stage == "plan-writer":
        return f"^{plans}/"
    if stage in ("plan-reviewer", "test-reviewer", "code-reviewer"):
        return f"^{plans}/reviews/"
    if stage == "test-writer":
        # Tests wherever each layer keeps them, the helpers they share, and the red report
        # — never production code, config or docs.
        mine = f"{paths.red_report}$|{plans}/reviews/test-writer-sendback-"
        return "^(" + "|".join((*TESTS, "tests/bdd/", mine)) + ")"
    if stage == "acceptance-reviewer":
        # Its proof and a send-back on the branch; everything else under build/.
        return f"^{plans}/(04-proof\\.md$|reviews/acceptance-reviewer-sendback-)"
    if stage == "code-writer":
        # Production code, config and docs anywhere — then write_denied takes the tests
        # back out. Not CLAUDE.md: it records no decision, and is a person's, like .claude/.
        return (
            r"^(src/|docs/|charts/|docker/|scripts/|\.github/|\.env\.example$|docker-compose|"
            r"(pyproject\.toml|uv\.lock|ruff\.toml|README\.md)$)"
        )
    return None


def write_denied(stage: str, paths: Paths) -> str | None:
    """Paths a stage may never write, even inside its scope. The code-writer builds to the
    approved red set: a test changed after the gate undoes the gate. The fixture holds this
    rule as it is now — the workflow line was added to it on purpose, after the port."""
    if stage == "code-writer":
        mine = (
            f"{paths.red_report}$",
            f"{paths.plan_dir}/reviews/[a-z]+-reviewer-",
            f"{paths.proof}$",
        )
        # Nor a workflow: pushing one needs a token the delivery doesn't hold, and it runs
        # with the repo's secrets — a workflow change is a person's, never a delivery's.
        return "^(" + "|".join((*TESTS, "tests/", r"\.github/workflows/", *mine)) + ")"
    return None


def strays(stage: str, paths: Paths, touched: Iterable[str]) -> tuple[list[str], list[str]]:
    """The paths a stage wrote outside its scope, and those it wrote where it may not."""
    touched = list(touched)
    scope, denied = write_scope(stage, paths), write_denied(stage, paths)
    outside = [p for p in touched if scope and not re.search(scope, p)]
    refused = [p for p in touched if denied and re.search(denied, p)]
    return outside, refused
