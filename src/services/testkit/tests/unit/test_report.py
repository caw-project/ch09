"""The test report `scripts/test.sh` writes to `docs/test-report.md`.

Every test lays results out in `tmp_path` the way a run of `scripts/test.sh`
leaves them in `build/test-results/`: a `<layer>.json` from `record`, and the
JUnit and coverage XML each tool writes. The XML here is cut down from real
output — pytest's and Vitest's JUnit, coverage.py's XML and Vitest's Cobertura.
See docs/plans/ch07/10-test-report-implementation-plan.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pytest

from testkit import report

REV = "e4d3396abcde"


# --- laying out results ------------------------------------------------------


@pytest.fixture
def results(tmp_path: Path) -> Path:
    path = tmp_path / "test-results"
    path.mkdir()
    return path


def recorded(
    results: Path, layer: str, exit_status: int = 0, revision: str = REV, args: tuple[str, ...] = ()
) -> None:
    command = ["record", layer, str(exit_status), revision, "--results", str(results)]
    if args:
        command += ["--", *args]
    assert report.main(command) == 0


def case(
    classname: str,
    name: str,
    outcome: str = "passed",
    message: str = "",
    properties: dict[str, str] | None = None,
) -> str:
    body = ""
    if properties:
        body += "<properties>"
        body += "".join(
            f"<property name={quoteattr(k)} value={quoteattr(v)} />" for k, v in properties.items()
        )
        body += "</properties>"
    if outcome in ("failure", "error"):
        body += f"<{outcome} message={quoteattr(message)}>{escape(message)}</{outcome}>"
    elif outcome == "skipped":
        body += f'<skipped type="pytest.skip" message={quoteattr(message)} />'
    return (
        f'<testcase classname={quoteattr(classname)} name={quoteattr(name)} time="0.0241">'
        f"{body}</testcase>"
    )


def junit(path: Path, *cases: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="6.590"'
        ' timestamp="2026-09-17T08:25:02.865068+01:00" hostname="build-host-7">'
        + "".join(cases)
        + "</testsuite></testsuites>"
    )


Line = tuple[int, str | None]  # hits, condition-coverage


def coverage(path: Path, packages: dict[str, list[Line]]) -> None:
    """Coverage XML with its totals in the header, as both tools write them."""
    body = ""
    totals = {"lines-valid": 0, "lines-covered": 0, "branches-valid": 0, "branches-covered": 0}
    for package, lines in packages.items():
        rows = ""
        for number, (hits, condition) in enumerate(lines, start=1):
            totals["lines-valid"] += 1
            totals["lines-covered"] += hits > 0
            branch = ""
            if condition:
                branch = f' branch="true" condition-coverage="{condition}"'
                covered, valid = condition.split("(")[1].rstrip(")").split("/")
                totals["branches-covered"] += int(covered)
                totals["branches-valid"] += int(valid)
            rows += f'<line number="{number}" hits="{hits}"{branch}/>'
        body += (
            f'<package name="{package}" line-rate="0" branch-rate="0" complexity="0"><classes>'
            f'<class name="a.py" filename="a.py" line-rate="0" branch-rate="0" complexity="0">'
            f"<methods/><lines>{rows}</lines></class></classes></package>"
        )
    header = " ".join(f'{name}="{value}"' for name, value in totals.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0" ?><coverage version="7.16.1" timestamp="1789629942722" {header}'
        f' line-rate="0" branch-rate="0" complexity="0"><packages>{body}</packages></coverage>'
    )


def unit(service: str, module: str = "test_a") -> str:
    return f"src.services.{service}.tests.unit.{module}"


def integration(service: str, module: str = "test_a") -> str:
    return f"src.services.{service}.tests.integration.{module}"


def journey(feature: str, scenario: str, line: int, tags: str = "bdd") -> dict[str, str]:
    return {"feature": feature, "scenario": scenario, "line": str(line), "tags": tags}


def section(text: str, heading: str) -> str:
    """The body of `## heading`, up to the next `## `."""
    _, found, rest = text.partition(f"\n## {heading}\n")
    assert found, f"no '## {heading}' section in:\n{text}"
    return rest.split("\n## ", 1)[0]


# --- layers ------------------------------------------------------------------


def test_the_report_names_itself_and_the_revision_it_describes(results):
    text = report.render(results, REV)

    assert text.startswith("# Test report\n")
    assert f"`{REV}`" in text.split("\n## ", 1)[0]


def test_a_layer_with_no_record_is_not_run(results):
    layers = section(report.render(results, REV), "Layers")

    rows = [line for line in layers.splitlines() if line.startswith("| ") and "---" not in line]
    assert rows == [
        "| Layer | Result | Passed | Failed | Skipped | Revision |",
        "| Lint | ⚪ not run | | | | |",
        "| Unit | ⚪ not run | | | | |",
        "| Integration | ⚪ not run | | | | |",
        "| End-to-end | ⚪ not run | | | | |",
    ]


def test_lint_has_a_result_and_no_counts(results):
    recorded(results, "lint")

    assert f"| Lint | ✅ passed | | | | `{REV}` |" in report.render(results, REV)


def test_a_passing_layer_counts_the_cases_of_every_tool_in_it(results):
    """Unit is pytest and Vitest together."""
    recorded(results, "unit")
    junit(
        results / "unit-python.xml",
        case(unit("auth"), "test_one"),
        case(unit("auth"), "test_two"),
        case(unit("messaging"), "test_three"),
        case(unit("messaging"), "test_four", "skipped", "not today"),
    )
    junit(
        results / "unit-frontend.xml",
        case("src/App.test.tsx", "App > renders"),
        case("src/App.test.tsx", "App > signs in"),
    )

    assert f"| Unit | ✅ passed | 5 | 0 | 1 | `{REV}` |" in report.render(results, REV)


def test_failures_and_errors_both_count_as_failed(results):
    recorded(results, "integration", exit_status=1)
    junit(
        results / "integration.xml",
        case(integration("auth"), "test_passes"),
        case(integration("auth"), "test_fails", "failure", "assert 1 == 2"),
        case(integration("auth"), "test_errors", "error", "failed on setup"),
    )

    assert f"| Integration | ❌ failed | 1 | 2 | 0 | `{REV}` |" in report.render(results, REV)


def test_a_layer_that_failed_before_writing_results_says_so(results):
    """Docker down, or `compose up` failing: a status and no XML."""
    recorded(results, "e2e", exit_status=1)

    text = report.render(results, REV)

    assert f"| End-to-end | ❌ failed | | | | `{REV}` |" in text
    assert "> End-to-end failed before it wrote any results." in section(text, "Layers")


def test_a_layer_recorded_at_another_revision_is_flagged(results):
    recorded(results, "lint", revision=REV)
    recorded(results, "unit", revision="a1b2c3d4e5f6")
    junit(results / "unit-python.xml", case(unit("auth"), "test_one"))

    layers = section(report.render(results, REV), "Layers")

    assert f"| Lint | ✅ passed | | | | `{REV}` |" in layers
    assert "| Unit | ✅ passed | 1 | 0 | 0 | ⚠️ `a1b2c3d4e5f6` |" in layers
    assert "> ⚠️ Unit was recorded at another revision." in layers
    assert "Lint was recorded" not in layers


def test_a_filtered_run_is_shown_against_its_layer(results):
    recorded(results, "unit", args=("-k", "auth and not slow"))
    junit(results / "unit-python.xml", case(unit("auth"), "test_one"))

    layers = section(report.render(results, REV), "Layers")

    assert "> Unit ran with `-k auth and not slow`, so it is not the whole layer." in layers


def test_record_keeps_the_exit_status_as_passed_or_failed(results):
    recorded(results, "lint", exit_status=0)
    recorded(results, "unit", exit_status=2)

    assert json.loads((results / "lint.json").read_text())["status"] == "passed"
    assert json.loads((results / "unit.json").read_text())["status"] == "failed"


# --- by service --------------------------------------------------------------


def test_cases_are_counted_per_service_and_layer(results):
    recorded(results, "unit", exit_status=1)
    recorded(results, "integration")
    junit(
        results / "unit-python.xml",
        case(unit("messaging"), "test_one"),
        case(unit("messaging"), "test_two"),
        case(unit("messaging"), "test_three", "failure", "boom"),
        case(unit("auth"), "test_one"),
        case(unit("auth"), "test_two", "skipped", "later"),
    )
    junit(results / "unit-frontend.xml", case("src/App.test.tsx", "App > renders"))
    junit(results / "integration.xml", case(integration("messaging"), "test_one"))

    rows = [
        line
        for line in section(report.render(results, REV), "By service").splitlines()
        if line.startswith("| ") and "---" not in line
    ]

    assert rows == [
        "| Service | Unit | Integration |",
        "| auth | ✅ 1 passed, 1 skipped | — |",
        "| messaging | ❌ 1 of 3 failed | ✅ 1 passed |",
        "| frontend | ✅ 1 passed | — |",
    ]


# --- coverage ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("covered", "total", "expected"),
    [
        (0, 4, "`░░░░░░░░░░` 0%"),
        (3, 4, "`███████░░░` 75%"),
        (999, 1000, "`█████████░` 99%"),
        (4, 4, "`██████████` 100%"),
        (0, 0, "—"),
    ],
)
def test_a_bar_never_rounds_up(covered, total, expected):
    """99.9% is not 100%: a full bar has to mean every line."""
    assert report.bar(covered, total) == expected


def test_coverage_is_per_service_from_coverage_py_and_cobertura(results):
    recorded(results, "unit")
    coverage(
        results / "unit-python-coverage.xml",
        {
            # Two packages in one service are summed: 3 of 4 lines, 1 of 2 branches.
            "src.services.worker.worker": [(1, None), (0, None), (2, "50% (1/2)")],
            "src.services.worker.worker.handlers": [(5, None)],
            "src.services.auth.auth": [(1, None), (1, "100% (2/2)")],
        },
    )
    coverage(
        results / "unit-frontend-coverage" / "cobertura-coverage.xml",
        {"src.features.channels": [(1, None)], "src.lib": [(0, None)]},
    )

    rows = [
        line
        for line in section(report.render(results, REV), "Coverage").splitlines()
        if line.startswith("| ") and "---" not in line
    ]

    assert rows == [
        "| Package | Lines | Branches |",
        "| auth | `██████████` 100% | `██████████` 100% |",
        "| worker | `███████░░░` 75% | `█████░░░░░` 50% |",
        "| frontend | `█████░░░░░` 50% | — |",
    ]


def test_a_line_repeated_under_its_method_counts_once(results):
    """Vitest's Cobertura lists a function's lines under its class and again
    under `<methods>`; coverage.py leaves `<methods/>` empty. Counting both
    made 622 frontend lines 909."""
    recorded(results, "unit")
    path = results / "unit-frontend-coverage" / "cobertura-coverage.xml"
    path.parent.mkdir(parents=True)
    path.write_text(
        '<?xml version="1.0" ?><coverage lines-valid="2" lines-covered="1"><packages>'
        '<package name="src.lib"><classes><class name="a.ts" filename="src/lib/a.ts">'
        '<methods><method name="f" hits="1"><lines><line number="1" hits="1"/></lines></method>'
        "</methods>"
        '<lines><line number="1" hits="1"/><line number="2" hits="0"/></lines>'
        "</class></classes></package></packages></coverage>"
    )

    assert "| frontend | `█████░░░░░` 50% | — |" in report.render(results, REV)


def test_frontend_coverage_is_the_cobertura_totals(results):
    """Istanbul can attach several branches to one line, so the per-line
    `condition-coverage` undercounts them — 211/278 against Vitest's own 309/397.
    The file is all frontend, so its totals are the figure Vitest prints."""
    recorded(results, "unit")
    path = results / "unit-frontend-coverage" / "cobertura-coverage.xml"
    path.parent.mkdir(parents=True)
    path.write_text(
        '<?xml version="1.0" ?><coverage lines-valid="4" lines-covered="3"'
        ' branches-valid="4" branches-covered="3"><packages>'
        '<package name="src.lib"><classes><class name="a.ts" filename="src/lib/a.ts"><lines>'
        '<line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/>'
        '<line number="2" hits="0"/>'
        "</lines></class></classes></package></packages></coverage>"
    )

    assert "| frontend | `███████░░░` 75% | `███████░░░` 75% |" in report.render(results, REV)


def test_no_coverage_files_say_so(results):
    assert "No coverage recorded." in section(report.render(results, REV), "Coverage")


# --- journeys ----------------------------------------------------------------


def test_journeys_group_by_feature_and_keep_file_order(results):
    recorded(results, "e2e")
    junit(
        results / "e2e.xml",
        case("tests.bdd.steps.test_r", "test_b", properties=journey("Reactions", "Later", 30)),
        case("tests.bdd.steps.test_r", "test_a", properties=journey("Reactions", "Earlier", 10)),
        case("tests.bdd.steps.test_c", "test_c", properties=journey("Channels", "Create", 5)),
    )

    journeys = section(report.render(results, REV), "Journeys")

    assert journeys.index("### Channels") < journeys.index("### Reactions")
    reactions = journeys.split("### Reactions", 1)[1]
    assert reactions.index("| Earlier |") < reactions.index("| Later |")


def test_a_journey_shows_what_became_of_it(results):
    recorded(results, "e2e", exit_status=1)
    junit(
        results / "e2e.xml",
        case("t", "test_1", properties=journey("F", "Passes", 1)),
        case("t", "test_2", "failure", "no", properties=journey("F", "Fails", 2)),
        case("t", "test_3", "error", "setup", properties=journey("F", "Errors", 3)),
        case(
            "t", "test_4", "skipped", "@pending", properties=journey("F", "Waits", 4, "bdd pending")
        ),
        case("t", "test_5", "skipped", "why", properties=journey("F", "Skips", 5)),
    )

    journeys = section(report.render(results, REV), "Journeys")

    assert "| Passes | ✅ passed |" in journeys
    assert "| Fails | ❌ failed |" in journeys
    assert "| Errors | ❌ failed |" in journeys
    assert "| Waits | ⏸️ pending |" in journeys
    assert "| Skips | ⏭️ skipped |" in journeys


def test_a_pipe_in_a_cell_is_escaped(results):
    recorded(results, "e2e")
    junit(results / "e2e.xml", case("t", "test_1", properties=journey("F", "this | that", 1)))

    assert "| this \\| that | ✅ passed |" in report.render(results, REV)


def test_no_journey_results_say_so(results):
    assert "No journeys recorded." in section(report.render(results, REV), "Journeys")


# --- failures ----------------------------------------------------------------


def test_a_failure_is_listed_with_its_message(results):
    recorded(results, "unit", exit_status=1)
    junit(
        results / "unit-python.xml",
        case(unit("messaging", "test_x"), "test_y", "failure", "AssertionError: assert 1 == 2"),
    )

    failures = section(report.render(results, REV), "Failures")

    assert (
        "### Unit · messaging · `src.services.messaging.tests.unit.test_x::test_y`\n\n"
        "```text\nAssertionError: assert 1 == 2\n```"
    ) in failures


def test_a_journey_failure_is_named_by_feature_and_scenario(results):
    recorded(results, "e2e", exit_status=1)
    junit(
        results / "e2e.xml",
        case(
            "t", "test_1", "error", "stack down", properties=journey("Reactions", "Ada reacts", 1)
        ),
    )

    failures = section(report.render(results, REV), "Failures")

    assert "### End-to-end · Reactions · Ada reacts\n\n```text\nstack down\n```" in failures


def test_a_failure_with_no_message_attribute_uses_its_text(results):
    """Vitest puts the assertion in the element's text."""
    recorded(results, "unit", exit_status=1)
    (results / "unit-frontend.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8" ?><testsuites><testsuite name="s">'
        '<testcase classname="src/App.test.tsx" name="App &gt; renders">'
        "<failure>expected true to be false</failure></testcase></testsuite></testsuites>"
    )

    failures = section(report.render(results, REV), "Failures")

    assert "### Unit · frontend · `src/App.test.tsx::App > renders`" in failures
    assert "```text\nexpected true to be false\n```" in failures


def test_a_long_message_is_cut_to_twenty_lines(results):
    recorded(results, "unit", exit_status=1)
    message = "\n".join(f"line {n}" for n in range(1, 31))
    junit(results / "unit-python.xml", case(unit("auth"), "test_y", "failure", message))

    failures = section(report.render(results, REV), "Failures")

    assert "line 20\n… 10 more lines\n```" in failures
    assert "line 21" not in failures


def test_failures_sort_by_layer_then_service_then_test(results):
    recorded(results, "unit", exit_status=1)
    recorded(results, "integration", exit_status=1)
    junit(
        results / "integration.xml",
        case(integration("auth"), "test_a", "failure", "x"),
    )
    junit(
        results / "unit-python.xml",
        case(unit("messaging"), "test_b", "failure", "x"),
        case(unit("auth"), "test_z", "failure", "x"),
        case(unit("auth"), "test_a", "failure", "x"),
    )

    headings = [
        line
        for line in section(report.render(results, REV), "Failures").splitlines()
        if line.startswith("### ")
    ]

    assert headings == [
        f"### Unit · auth · `{unit('auth')}::test_a`",
        f"### Unit · auth · `{unit('auth')}::test_z`",
        f"### Unit · messaging · `{unit('messaging')}::test_b`",
        f"### Integration · auth · `{integration('auth')}::test_a`",
    ]


def test_no_failures_say_none(results):
    recorded(results, "lint")

    assert section(report.render(results, REV), "Failures").strip() == "None."


# --- the diff is the news ----------------------------------------------------


def test_nothing_about_the_run_environment_reaches_the_report(results):
    """No timestamps, hostnames or durations: a rerun with the same results
    writes the same file, so the report changes only when a result does."""
    recorded(results, "unit")
    junit(results / "unit-python.xml", case(unit("auth"), "test_one"))
    coverage(results / "unit-python-coverage.xml", {"src.services.auth.auth": [(1, None)]})

    first = report.render(results, REV)

    for leaked in ("2026-09-17", "build-host-7", "6.59", "0.0241", "1789629942722"):
        assert leaked not in first
    assert report.render(results, REV) == first


def test_main_records_then_renders_to_a_file(results, tmp_path):
    out = tmp_path / "docs" / "test-report.md"
    junit(results / "unit-python.xml", case(unit("auth"), "test_one", "failure", "boom"))

    assert report.main(["record", "unit", "1", REV, "--results", str(results)]) == 0
    assert (
        report.main(["render", "--results", str(results), "--out", str(out), "--revision", REV])
        == 0
    )

    assert out.read_text() == report.render(results, REV)
    assert f"| Unit | ❌ failed | 0 | 1 | 0 | `{REV}` |" in out.read_text()
