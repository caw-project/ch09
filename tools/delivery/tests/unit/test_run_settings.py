"""The `DELIVER_*` settings — the same names, defaults and refusals as the bash header."""

from __future__ import annotations

import pytest
from delivery.errors import ConfigError
from delivery.run.settings import Settings


def test_the_defaults_are_the_bash_ones():
    s = Settings.from_env({})

    assert (s.max_rounds, s.max_sendbacks, s.max_turns) == (3, 3, None)
    assert (s.rework_max_turns, s.final_max_turns, s.final_effort) == (100, 60, "medium")
    assert (s.base, s.run, s.permission_mode) == ("main", "", "dontAsk")
    assert (s.model, s.rework_model, s.effort, s.rework_effort) == ("", "", "", "")
    assert (s.retry_wait, s.deploy_sh) == (30.0, "scripts/deploy.sh")


def test_a_stages_own_setting_is_read_by_its_name():
    s = Settings.from_env(
        {"DELIVER_MODEL_TEST_WRITER": "opus", "DELIVER_EFFORT_CODE_REVIEWER": "high"}
    )

    assert s.stage_model("test-writer") == "opus"
    assert s.stage_effort("code-reviewer") == "high"
    assert s.stage_model("plan-writer") == ""


@pytest.mark.parametrize(
    ("env", "says"),
    [
        ({"DELIVER_MAX_ROUNDS": "0"}, "DELIVER_MAX_ROUNDS must be a positive number"),
        ({"DELIVER_MAX_SENDBACKS": "x"}, "DELIVER_MAX_SENDBACKS must be a positive number"),
        ({"DELIVER_REWORK_MAX_TURNS": ""}, "DELIVER_REWORK_MAX_TURNS must be a positive number"),
        ({"DELIVER_MAX_TURNS": "-3"}, "DELIVER_MAX_TURNS must be a positive number"),
        ({"DELIVER_RUN": "a b"}, "DELIVER_RUN may hold letters, digits, - and _ only"),
        (
            {"DELIVER_FINAL_EFFORT": "huge"},
            "DELIVER_FINAL_EFFORT must be low, medium, high, xhigh or max",
        ),
    ],
)
def test_a_bad_setting_is_refused(env, says):
    with pytest.raises(ConfigError, match=says):
        Settings.from_env(env)


def test_an_empty_max_turns_means_by_stage():
    assert Settings.from_env({"DELIVER_MAX_TURNS": ""}).max_turns is None
