"""`testkit.plugin` labels each Gherkin scenario in the JUnit file.

The test report groups journeys by feature and orders them as the `.feature`
file does, and pytest-bdd's Cucumber JSON cannot carry that: it leaves out a
scenario that fails in setup, which is every scenario when the stack is down.
So the plugin adds the names as user properties, which pytest writes into
`--junitxml` output under every JUnit family.

Runs pytest in a subprocess, for the reason `test_plugin.py` gives.
"""

from __future__ import annotations

import textwrap
import xml.etree.ElementTree as ET

import pytest

FEATURE = """\
@bdd
Feature: Demo
  Scenario: First thing
    Given nothing

  @pending
  Scenario: Second thing
    Given nothing
"""

STEPS = """
from pytest_bdd import given, scenarios

scenarios("demo.feature")


@given("nothing")
def nothing():
    pass


def test_not_a_scenario():
    pass
"""


@pytest.fixture
def junit(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, str]]:
    """Each test case's properties, by test name, from a run over the demo feature."""
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    pytester.makeini(
        "[pytest]\naddopts = --import-mode=importlib\nmarkers =\n    bdd\n    pending\n"
    )
    (pytester.path / "demo.feature").write_text(FEATURE)
    (pytester.path / "test_demo.py").write_text(textwrap.dedent(STEPS))

    result = pytester.runpytest_subprocess("--junitxml=junit.xml", timeout=60)
    result.assert_outcomes(passed=3)

    # pytest wrote this file a moment ago, in pytester's own temp directory.
    root = ET.parse(pytester.path / "junit.xml").getroot()  # noqa: S314
    return {
        case.get("name", ""): {
            prop.get("name", ""): prop.get("value", "") for prop in case.iter("property")
        }
        for case in root.iter("testcase")
    }


def test_a_scenario_carries_its_feature_name_and_line(junit):
    assert junit["test_first_thing"] == {
        "feature": "Demo",
        "scenario": "First thing",
        "line": "3",
        "tags": "bdd",
    }


def test_a_scenario_carries_its_own_tags_and_its_features_sorted(junit):
    assert junit["test_second_thing"]["tags"] == "bdd pending"
    assert junit["test_second_thing"]["line"] == "7"


def test_a_test_that_is_not_a_scenario_carries_nothing(junit):
    assert junit["test_not_a_scenario"] == {}
