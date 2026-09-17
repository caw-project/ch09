"""The test report: every layer's results, merged into one Markdown file.

`scripts/test.sh` calls this after each layer it runs::

    python -m testkit.report record <layer> <exit status> <revision> --results DIR [-- args]
    python -m testkit.report render --results DIR --out docs/test-report.md --revision REV

`record` writes `<layer>.json` beside the JUnit and coverage XML the layer's
tools wrote into the results directory, and `render` merges whatever is there.
A layer that did not run this time keeps its last result, flagged when it was
recorded at another revision.

The report is committed, so it leaves out anything that changes from one run
to the next without a result changing — timestamps, hostnames, durations. Its
diff is then the news. See
docs/plans/ch07/10-test-report-implementation-plan.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Layers in the order `scripts/test.sh all` runs them, with their headings.
LAYERS = {"lint": "Lint", "unit": "Unit", "integration": "Integration", "e2e": "End-to-end"}

#: Each layer's JUnit files, and the service a file's cases belong to when the
#: classname cannot say — Vitest's classname is a file path.
JUNIT: dict[str, tuple[tuple[str, str | None], ...]] = {
    "unit": (("unit-python.xml", None), ("unit-frontend.xml", "frontend")),
    "integration": (("integration.xml", None),),
    "e2e": (("e2e.xml", None),),
}

#: Unit coverage: coverage.py's XML, then Vitest's Cobertura, which has the same shape.
COVERAGE = (
    ("unit-python-coverage.xml", None),
    ("unit-frontend-coverage/cobertura-coverage.xml", "frontend"),
)

FRONTEND = "frontend"
#: Where a case with no service lands — none should, but a row beats a lost result.
OTHER = "other"
MESSAGE_LINES = 20
BAR_WIDTH = 10

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"

_BRANCHES = re.compile(r"\((\d+)/(\d+)\)")


@dataclass(frozen=True)
class Record:
    layer: str
    status: str
    revision: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Case:
    layer: str
    service: str
    classname: str
    name: str
    outcome: str
    message: str = ""
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def test_id(self) -> str:
        return f"{self.classname}::{self.name}"


@dataclass
class Covered:
    lines: int = 0
    lines_total: int = 0
    branches: int = 0
    branches_total: int = 0


# --- reading -----------------------------------------------------------------


def _parse(path: Path) -> ET.Element:
    # Written moments ago by pytest, Vitest or coverage.py on this machine —
    # never input from anyone else.
    return ET.parse(path).getroot()  # noqa: S314


def read_record(results: Path, layer: str) -> Record | None:
    path = results / f"{layer}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return Record(layer, data["status"], data["revision"], tuple(data.get("args", ())))


def service_of(classname: str) -> str:
    """`src.services.<service>…` → `<service>`; anything else has none.

    Takes a pytest classname or a coverage.py package name.
    """
    parts = classname.split(".")
    return parts[2] if len(parts) >= 3 and parts[:2] == ["src", "services"] else ""


def read_junit(path: Path, layer: str, service: str | None) -> list[Case]:
    cases = []
    for element in _parse(path).iter("testcase"):
        classname = element.get("classname", "")
        outcome, message = PASSED, ""
        for tag in ("failure", "error", "skipped"):
            found = element.find(tag)
            if found is not None:
                outcome = SKIPPED if tag == "skipped" else FAILED
                message = (found.get("message") or found.text or "").strip()
                break
        cases.append(
            Case(
                layer=layer,
                service=service or service_of(classname),
                classname=classname,
                name=element.get("name", ""),
                outcome=outcome,
                message=message,
                properties={
                    prop.get("name", ""): prop.get("value", "") for prop in element.iter("property")
                },
            )
        )
    return cases


def read_coverage(path: Path, service: str | None, into: dict[str, Covered]) -> None:
    root = _parse(path)
    if service and root.get("lines-valid") is not None:
        # The whole file is one service, so its totals are exact. Summed from the
        # lines instead, Istanbul's branches undercount: it can attach several
        # to one line, and `condition-coverage` shows only some of them.
        covered = into.setdefault(service, Covered())
        covered.lines += int(root.get("lines-covered", "0"))
        covered.lines_total += int(root.get("lines-valid", "0"))
        covered.branches += int(root.get("branches-covered", "0"))
        covered.branches_total += int(root.get("branches-valid", "0"))
        return
    for package in root.iter("package"):
        name = service or service_of(package.get("name", ""))
        if not name:
            continue
        covered = into.setdefault(name, Covered())
        # A class's own <lines>, not iter("line"): Vitest's Cobertura repeats a
        # function's lines under <methods>, and those would count twice.
        for line in package.iterfind("classes/class/lines/line"):
            covered.lines_total += 1
            covered.lines += int(line.get("hits", "0")) > 0
            branches = _BRANCHES.search(line.get("condition-coverage", ""))
            if line.get("branch") == "true" and branches:
                covered.branches += int(branches.group(1))
                covered.branches_total += int(branches.group(2))


# --- rendering -----------------------------------------------------------------


def bar(covered: int, total: int) -> str:
    """A ten-block bar and a percentage, both rounded down: full means every one."""
    if total == 0:
        return "—"
    blocks = covered * BAR_WIDTH // total
    return f"`{'█' * blocks}{'░' * (BAR_WIDTH - blocks)}` {covered * 100 // total}%"


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _service_order(service: str) -> tuple[bool, str]:
    return (service == FRONTEND, service)


def _counts(cases: Iterable[Case]) -> dict[str, int]:
    counts = {PASSED: 0, FAILED: 0, SKIPPED: 0}
    for case in cases:
        counts[case.outcome] += 1
    return counts


def _layers(records: dict[str, Record], cases: dict[str, list[Case]], revision: str) -> list[str]:
    rows = [
        "| Layer | Result | Passed | Failed | Skipped | Revision |",
        "|---|---|--:|--:|--:|---|",
    ]
    notes = []
    for layer, label in LAYERS.items():
        record = records.get(layer)
        if record is None:
            rows.append(f"| {label} | ⚪ not run | | | | |")
            continue
        result = "✅ passed" if record.status == PASSED else "❌ failed"
        counts = "| |"
        if layer in cases:
            c = _counts(cases[layer])
            counts = f"{c[PASSED]} | {c[FAILED]} | {c[SKIPPED]}"
        elif layer in JUNIT and record.status != PASSED:
            notes.append(f"> {label} failed before it wrote any results.")
        stale = record.revision != revision
        flag = "⚠️ " if stale else ""
        rows.append(f"| {label} | {result} | {counts} | {flag}`{record.revision}` |")
        if stale:
            notes.append(f"> ⚠️ {label} was recorded at another revision.")
        if record.args:
            notes.append(
                f"> {label} ran with `{' '.join(record.args)}`, so it is not the whole layer."
            )
    return rows + [line for note in notes for line in ("", note)]


def _failures(cases: dict[str, list[Case]]) -> list[str]:
    order = list(LAYERS)
    failed = sorted(
        (case for layer_cases in cases.values() for case in layer_cases if case.outcome == FAILED),
        key=lambda case: (order.index(case.layer), case.service, case.test_id),
    )
    if not failed:
        return ["None."]
    lines = []
    for case in failed:
        label = LAYERS[case.layer]
        if "scenario" in case.properties:
            heading = f"### {label} · {case.properties.get('feature', '')} · {case.properties['scenario']}"
        else:
            heading = f"### {label} · {case.service or OTHER} · `{case.test_id}`"
        message = case.message.splitlines() or ["(no message)"]
        if len(message) > MESSAGE_LINES:
            message = [*message[:MESSAGE_LINES], f"… {len(message) - MESSAGE_LINES} more lines"]
        fence = "~~~~" if any("```" in line for line in message) else "```"
        lines += [heading, "", f"{fence}text", *message, fence, ""]
    return lines[:-1]


def _journey_result(case: Case) -> str:
    if case.outcome == FAILED:
        return "❌ failed"
    if case.outcome == SKIPPED:
        return "⏸️ pending" if "pending" in case.properties.get("tags", "").split() else "⏭️ skipped"
    return "✅ passed"


def _journeys(cases: Sequence[Case]) -> list[str]:
    features: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        if "scenario" in case.properties:
            features[case.properties.get("feature", "")].append(case)
    if not features:
        return ["No journeys recorded."]
    lines = []
    for feature in sorted(features):
        scenarios = sorted(
            features[feature],
            key=lambda case: (int(case.properties.get("line") or 0), case.properties["scenario"]),
        )
        c = _counts(scenarios)
        pending = sum(_journey_result(case) == "⏸️ pending" for case in scenarios)
        summary = [f"{c[PASSED]} of {len(scenarios)} passed"]
        if c[FAILED]:
            summary.append(f"{c[FAILED]} failed")
        if pending:
            summary.append(f"{pending} pending")
        if c[SKIPPED] - pending:
            summary.append(f"{c[SKIPPED] - pending} skipped")
        lines += [f"### {cell(feature)}", "", ", ".join(summary) + ".", ""]
        lines += ["| Scenario | Result |", "|---|---|"]
        lines += [
            f"| {cell(case.properties['scenario'])} | {_journey_result(case)} |"
            for case in scenarios
        ]
        lines.append("")
    return lines[:-1]


def _by_service(cases: dict[str, list[Case]]) -> list[str]:
    grouped: dict[str, dict[str, list[Case]]] = defaultdict(lambda: defaultdict(list))
    for layer in ("unit", "integration"):
        for case in cases.get(layer, ()):
            grouped[case.service or OTHER][layer].append(case)
    if not grouped:
        return ["No unit or integration results recorded."]

    def summary(layer_cases: list[Case]) -> str:
        if not layer_cases:
            return "—"
        c = _counts(layer_cases)
        if c[FAILED]:
            return f"❌ {c[FAILED]} of {len(layer_cases)} failed"
        return f"✅ {c[PASSED]} passed" + (f", {c[SKIPPED]} skipped" if c[SKIPPED] else "")

    rows = ["| Service | Unit | Integration |", "|---|---|---|"]
    for service in sorted(grouped, key=_service_order):
        layers = grouped[service]
        rows.append(f"| {service} | {summary(layers['unit'])} | {summary(layers['integration'])} |")
    return rows


def _coverage(covered: dict[str, Covered]) -> list[str]:
    if not covered:
        return ["No coverage recorded."]
    rows = ["Unit tests only.", "", "| Package | Lines | Branches |", "|---|---|---|"]
    for service in sorted(covered, key=_service_order):
        c = covered[service]
        rows.append(
            f"| {service} | {bar(c.lines, c.lines_total)} | {bar(c.branches, c.branches_total)} |"
        )
    return rows


def render(results: Path, revision: str) -> str:
    """The report for everything recorded in `results`, as of `revision`."""
    records = {
        layer: record for layer in LAYERS if (record := read_record(results, layer)) is not None
    }
    cases: dict[str, list[Case]] = {}
    for layer, files in JUNIT.items():
        if layer not in records:
            continue
        for name, service in files:
            if (results / name).is_file():
                cases.setdefault(layer, []).extend(read_junit(results / name, layer, service))
    covered: dict[str, Covered] = {}
    if "unit" in records:
        for name, service in COVERAGE:
            if (results / name).is_file():
                read_coverage(results / name, service, covered)

    sections = {
        "Layers": _layers(records, cases, revision),
        "Failures": _failures(cases),
        "Journeys": _journeys(cases.get("e2e", [])),
        "By service": _by_service(cases),
        "Coverage": _coverage(covered),
    }
    lines = [
        "# Test report",
        "",
        (
            "Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost."
            f" Revision `{revision}`."
        ),
    ]
    for heading, body in sections.items():
        lines += ["", f"## {heading}", "", *body]
    return "\n".join(lines) + "\n"


# --- command line ------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    passthrough: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, passthrough = argv[:split], argv[split + 1 :]

    parser = argparse.ArgumentParser(prog="python -m testkit.report")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="save a layer's outcome beside its results")
    record.add_argument("layer", choices=list(LAYERS))
    record.add_argument("exit_status", type=int)
    record.add_argument("revision")
    record.add_argument("--results", type=Path, required=True)
    write = commands.add_parser("render", help="merge every recorded layer into the report")
    write.add_argument("--results", type=Path, required=True)
    write.add_argument("--out", type=Path, required=True)
    write.add_argument("--revision", required=True)
    options = parser.parse_args(argv)

    if options.command == "record":
        options.results.mkdir(parents=True, exist_ok=True)
        status = PASSED if options.exit_status == 0 else FAILED
        (options.results / f"{options.layer}.json").write_text(
            json.dumps(
                {
                    "layer": options.layer,
                    "status": status,
                    "revision": options.revision,
                    "args": passthrough,
                },
                indent=2,
            )
            + "\n"
        )
    else:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(render(options.results, options.revision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
