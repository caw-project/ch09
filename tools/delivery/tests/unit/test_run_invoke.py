"""Running a stage's agent: the `claude` command line, a crash rerun once, a turn-capped pass
resumed once, and the result checked rather than trusted."""

from __future__ import annotations

import json
import re

import pytest
from delivery.errors import RunError
from delivery.run.invoke import (
    RESULT_SCHEMA,
    Pass,
    claude_args,
    finish_outputs,
    result_of,
    run_agent,
)

TOOLS = ["Read", "Bash(git log *)"]


def a_pass(**kw) -> Pass:
    values = {
        "stage": "plan-writer",
        "prompt": "Issue: gh-3",
        "turns": 150,
        "tools": TOOLS,
        "model": "",
        "effort": "",
        "permission_mode": "dontAsk",
    }
    return Pass(**{**values, **kw})


def output(subtype="success", is_error=False, structured=None, session="s-1") -> str:
    return json.dumps(
        {
            "subtype": subtype,
            "is_error": is_error,
            "num_turns": 3,
            "total_cost_usd": 0.5,
            "duration_ms": 60000,
            "session_id": session,
            "structured_output": structured,
        }
    )


DONE = {"status": "done", "summary": "planned", "files": [], "questions": []}


class FakeClaude:
    """Answers each run with the next of `answers`; records each argument list."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd):
        self.calls.append(list(args))
        return self.answers.pop(0)


def test_a_pass_is_one_headless_claude_run_with_the_stages_reach():
    assert claude_args(a_pass(model="sonnet", effort="high")) == [
        "-p",
        "Issue: gh-3",
        "--agent",
        "plan-writer",
        "--max-turns",
        "150",
        "--allowedTools",
        "Read",
        "Bash(git log *)",
        "--model",
        "sonnet",
        "--effort",
        "high",
        "--output-format",
        "json",
        "--json-schema",
        RESULT_SCHEMA,
        "--permission-mode",
        "dontAsk",
    ]


def test_no_model_or_effort_leaves_the_agents_own():
    args = claude_args(a_pass())

    assert "--model" not in args
    assert "--effort" not in args


def test_the_result_schema_offers_every_status():
    schema = json.loads(RESULT_SCHEMA)

    assert schema["properties"]["status"]["enum"] == [
        "done",
        "approved",
        "changes_requested",
        "send_back",
        "needs_human",
    ]


def run(tmp_path, claude, **kw):
    return run_agent(
        a_pass(**kw),
        cwd=tmp_path,
        base=tmp_path / "01-plan-writer",
        run=claude,
        sleep=lambda _: None,
    )


def test_a_pass_that_finishes_leaves_its_transcript(tmp_path):
    claude = FakeClaude(output(structured=DONE))

    ran = run(tmp_path, claude)

    assert ran.subtype == "success"
    assert json.loads((tmp_path / "01-plan-writer.json").read_text())["structured_output"] == DONE
    assert len(claude.calls) == 1


def test_a_crash_runs_once_more_from_the_top(tmp_path):
    claude = FakeClaude("", output(structured=DONE))

    ran = run(tmp_path, claude)

    assert ran.subtype == "success"
    assert claude.calls[0] == claude.calls[1]
    assert (tmp_path / "01-plan-writer.failed.json").exists()


def test_two_crashes_stop_the_run(tmp_path):
    with pytest.raises(RunError, match="plan-writer failed twice"):
        run(tmp_path, FakeClaude("", "not json"))


def test_out_of_turns_is_resumed_once_in_the_same_session(tmp_path):
    claude = FakeClaude(output("error_max_turns", True, session="s-9"), output(structured=DONE))

    ran = run(tmp_path, claude, turns=150, model="sonnet")

    resumed = claude.calls[1]
    assert ran.subtype == "success"
    assert resumed[resumed.index("--resume") + 1] == "s-9"
    assert resumed[resumed.index("--max-turns") + 1] == "75"
    assert resumed[resumed.index("--model") + 1] == "sonnet"
    assert "You have 75 more turns" in resumed[1]
    assert (tmp_path / "01-plan-writer.out-of-turns.json").exists()


def test_a_resume_gets_at_least_thirty_turns(tmp_path):
    claude = FakeClaude(output("error_max_turns", True), output(structured=DONE))

    run(tmp_path, claude, turns=40)

    assert claude.calls[1][claude.calls[1].index("--max-turns") + 1] == "30"


def test_out_of_turns_twice_is_a_question_for_a_human(tmp_path):
    claude = FakeClaude(output("error_max_turns", True), output("error_max_turns", True))
    ran = run(tmp_path, claude)

    found = result_of(
        ran,
        stage="plan-writer",
        turns=150,
        round_=1,
        transcript="build/delivery/01-plan-writer.json",
    )

    assert found["status"] == "needs_human"
    assert "used all 150 turns in round 1" in found["summary"]
    assert found["questions"][0].startswith("plan-writer ran out of turns twice.")


def test_a_finished_pass_returns_its_structured_result(tmp_path):
    ran = run(tmp_path, FakeClaude(output(structured=DONE)))

    assert result_of(ran, stage="plan-writer", turns=150, round_=1, transcript="t") == DONE


def test_a_pass_with_no_structured_result_is_an_error(tmp_path):
    ran = run(tmp_path, FakeClaude(output(structured=None)))

    with pytest.raises(RunError, match="returned no structured result"):
        result_of(ran, stage="plan-writer", turns=150, round_=1, transcript="t")


def test_a_pass_that_ended_in_error_is_an_error(tmp_path):
    ran = run(
        tmp_path,
        FakeClaude(output("error_during_execution", True), output("error_during_execution", True)),
    )

    with pytest.raises(RunError, match=re.escape("ended in error (error_during_execution)")):
        result_of(ran, stage="plan-writer", turns=150, round_=1, transcript="t")


# --- a verdict returned without its file ----------------------------------------


def test_a_missing_file_is_asked_for_in_the_same_session(tmp_path):
    claude = FakeClaude(output(structured=DONE))

    ran = finish_outputs(
        a_pass(stage="test-reviewer", model="sonnet"),
        session="s-7",
        status="approved",
        missing=["docs/plans/gh-3/reviews/test-reviewer-2.md"],
        cwd=tmp_path,
        base=tmp_path / "08-test-reviewer",
        run=claude,
    )

    asked = claude.calls[0]
    assert ran.subtype == "success"
    assert asked[asked.index("--resume") + 1] == "s-7"
    assert asked[asked.index("--agent") + 1] == "test-reviewer"
    assert asked[asked.index("--max-turns") + 1] == "20"
    assert "returned approved" in asked[1]
    assert "docs/plans/gh-3/reviews/test-reviewer-2.md" in asked[1]
    assert (tmp_path / "08-test-reviewer.missing.json").exists()


def test_asking_for_a_missing_file_with_no_answer_stops_the_run(tmp_path):
    with pytest.raises(RunError, match="test-reviewer failed when asked for"):
        finish_outputs(
            a_pass(stage="test-reviewer"),
            session="s-7",
            status="approved",
            missing=["x.md"],
            cwd=tmp_path,
            base=tmp_path / "08-test-reviewer",
            run=FakeClaude(""),
        )
