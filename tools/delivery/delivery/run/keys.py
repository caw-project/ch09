"""A delivery is named by its issue's key: `issue-8` locally, `gh-3` on GitHub.

The branch, the worktree and the plan folder all come from it, and every path an
agent sees is under that folder — so no agent knows which backend the issue came from.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from delivery.errors import ConfigError
from delivery.model import Issue
from delivery.resolve import GITHUB, LOCAL

#: Each key prefix, and the backend it belongs to. `fj-` and `ado-` are reserved.
PREFIXES = {"issue": LOCAL, "gh": GITHUB, "fj": "forgejo", "ado": "azure-devops"}
#: No leading zero: `issue-08` would name a second delivery of `issue-8`.
KEY = re.compile(r"([a-z]+)-([1-9][0-9]*)")


@dataclass(frozen=True)
class Paths:
    """Every path a delivery uses, relative to the worktree root."""

    key: str
    plan_dir: str
    issue_copy: str
    plan: str
    red_report: str
    green_report: str
    proof: str
    answers: str
    reviews: str
    #: Where the issue came from — read by the workflow only, never named to an agent.
    source: str
    #: The acceptance-reviewer's screenshots, packs and results: disposable, under the
    #: ignored build/, outside every snapshot.
    evidence: str = "build/acceptance"


def paths_for(key: str) -> Paths:
    plans = f"docs/plans/{key}"
    return Paths(
        key=key,
        plan_dir=plans,
        issue_copy=f"{plans}/00-issue.md",
        plan=f"{plans}/01-implementation-plan.md",
        red_report=f"{plans}/02-red-tests.md",
        green_report=f"{plans}/03-green-report.md",
        proof=f"{plans}/04-proof.md",
        answers=f"{plans}/needs-human.md",
        reviews=f"{plans}/reviews",
        source=f"{plans}/source.json",
    )


def check_key(key: str, backend: str) -> None:
    """Refuses a key that isn't one, or belongs to another backend than the one in use."""
    match = KEY.fullmatch(key)
    owner = PREFIXES.get(match.group(1)) if match else None
    if owner is None:
        raise ConfigError(f"'{key}' is not an issue key — they look like issue-8 or gh-3")
    if owner not in (LOCAL, GITHUB):
        raise ConfigError(f"{key} is a {owner} key, which is not supported yet")
    if owner != backend:
        raise ConfigError(f"{key} is a {owner} key, but the backend is {backend}")


def branch_for(key: str, run: str) -> str:
    return f"feature/{key}{f'-{run}' if run else ''}"


def worktree_for(root: Path, key: str, run: str) -> Path:
    """Beside the primary checkout: `../caw-<key>[-<run>]`."""
    return root.parent / f"caw-{key}{f'-{run}' if run else ''}"


def render_issue(issue: Issue) -> str:
    """The agents' copy of the issue: the title as a heading, then the body. One shape for
    every backend — no `Issue:` line, no number; the key is in the context block."""
    body = "\n".join(line.rstrip() for line in issue.body.replace("\r\n", "\n").split("\n"))
    return f"# {issue.title.strip()}\n\n{body.strip(chr(10))}\n"


@dataclass(frozen=True)
class Source:
    backend: str
    url: str | None
    number: int


def guard_source(path: Path, source: Source) -> None:
    """Records where a key's issue came from, and refuses another source for it later.

    Keys are only unique within a backend: two GitHub repos both have a `gh-3`. The record
    is committed with the plan, so the guard still holds after the plan merges.
    """
    if path.is_file():
        held = json.loads(path.read_text())
        if held != asdict(source):
            raise ConfigError(
                f"{path.parent.name} already holds the plan for {describe(held)};"
                f" this run's issue is {describe(asdict(source))}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(source), indent=2) + "\n")


def describe(source: dict) -> str:
    where = source.get("url") or "this repo"
    return f"{source.get('backend')} issue {source.get('number')} at {where}"
