"""The runner's per-stage rules, against the golden fixture captured from the bash `deliver.sh`.

`fixtures/deliver-rules.json` was printed once by the bash functions — `model_for`,
`effort_for`, `turns_for`, `is_rework`, `is_final_round`, `allowed_tools`, `write_scope`,
`write_denied`, `writer_output`, `earlier_pair` — over every stage, situation and override.
The tool and write rules are the safety boundary, so the port is held to it row by row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from delivery.run.keys import paths_for
from delivery.run.machine import earlier_pair, is_final_round, is_rework, pair_of
from delivery.run.rules import (
    allowed_tools,
    effort_for,
    model_for,
    strays,
    turns_for,
    write_denied,
    write_scope,
    writer_output,
)
from delivery.run.settings import Settings
from delivery.run.state import State

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "deliver-rules.json").read_text())
PATHS = paths_for("issue-999")


def situated(situation: str, stage: str) -> State:
    """The state the capture script set up for a situation — see the fixture's `situations`."""
    state = State.fresh(max_rounds=3)
    pair = pair_of(stage)
    if situation == "review" and stage.endswith("-writer"):
        state.review = "x.md"
    elif situation == "round2":
        state.rounds[pair] = 2
    elif situation == "final":
        state.rounds[pair] = 3
    elif situation == "past-final":
        state.rounds[pair] = 4
    elif situation == "moved-final":
        state.rounds[pair] = 3
        state.final[pair] = 4
    elif situation == "other-sendback":
        sender = "acceptance-reviewer" if stage == "code-reviewer" else "code-reviewer"
        state.open_sendbacks[sender] = "y.md"
    elif situation == "own-sendback" and stage != "plan-writer" and stage != "plan-reviewer":
        state.open_sendbacks[stage] = "y.md"
    return state


def settings_for(env: str, stage: str) -> Settings:
    upper = stage.upper().replace("-", "_")
    values = {k.replace("<STAGE>", upper): v for k, v in FIXTURE["envs"][env].items()}
    return Settings.from_env(values)


@pytest.mark.parametrize(
    "row", FIXTURE["passes"], ids=lambda r: f"{r['stage']}-{r['situation']}-{r['env']}"
)
def test_a_pass_runs_as_the_bash_ran_it(row):
    state = situated(row["situation"], row["stage"])
    settings = settings_for(row["env"], row["stage"])
    stage = row["stage"]

    assert {
        "model": model_for(stage, state, settings),
        "effort": effort_for(stage, state, settings),
        "turns": turns_for(stage, state, settings),
        "rework": is_rework(stage, state),
        "final": is_final_round(stage, state),
    } == {k: row[k] for k in ("model", "effort", "turns", "rework", "final")}


@pytest.mark.parametrize("stage", FIXTURE["stages"])
def test_a_stage_may_do_what_the_bash_let_it(stage):
    expected = FIXTURE["stages"][stage]

    assert {
        "allowed_tools": allowed_tools(stage),
        "write_scope": write_scope(stage, PATHS),
        "write_denied": write_denied(stage, PATHS),
        "writer_output": writer_output(stage, PATHS),
        "earlier_pair": earlier_pair(stage),
    } == expected


def test_the_rules_follow_the_key():
    paths = paths_for("gh-3")

    assert write_scope("plan-writer", paths) == "^docs/plans/gh-3/"
    assert writer_output("test-writer", paths) == "docs/plans/gh-3/02-red-tests.md"


# --- what a stage wrote, against its rules -----------------------------------


def test_a_stage_inside_its_scope_wrote_nothing_stray():
    assert strays("plan-reviewer", PATHS, ["docs/plans/issue-999/reviews/plan-reviewer-1.md"]) == (
        [],
        [],
    )


def test_a_write_outside_the_scope_is_named():
    outside, denied = strays("plan-writer", PATHS, ["docs/plans/issue-999/01-plan.md", "src/x.py"])

    assert (outside, denied) == (["src/x.py"], [])


def test_a_code_writer_may_not_touch_a_test_inside_its_scope():
    touched = ["src/services/auth/auth/app.py", "src/services/auth/tests/unit/test_app.py"]

    assert strays("code-writer", PATHS, touched) == (
        [],
        ["src/services/auth/tests/unit/test_app.py"],
    )


def test_a_code_writer_may_not_touch_a_workflow():
    # A pushed workflow change needs a token the delivery's runner doesn't hold, and runs
    # with the repo's secrets: it is a person's change, never a delivery's.
    touched = [".github/workflows/ci.yml", ".github/dependabot.yml"]

    assert strays("code-writer", PATHS, touched) == ([], [".github/workflows/ci.yml"])


def test_a_code_writer_may_not_edit_claude_md():
    # CLAUDE.md states how to work and records no decision, so no slice has cause to edit
    # it; like .claude/, it is a person's. A CLAUDE.md under src/ is a service's docs.
    touched = ["CLAUDE.md", ".claude/agents/code-writer.md", "src/frontend/CLAUDE.md"]

    assert strays("code-writer", PATHS, touched) == (
        ["CLAUDE.md", ".claude/agents/code-writer.md"],
        [],
    )


def test_an_unconfined_stage_has_no_strays():
    # Every stage has a scope today; the rule for one without is "anything goes".
    assert write_scope("no-such-stage", PATHS) is None
