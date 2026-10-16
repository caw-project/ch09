"""A delivery is named by its key: the branch, the worktree, the plan folder, and the guard
that stops two backends' issues sharing one."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from delivery.errors import ConfigError
from delivery.model import Issue
from delivery.run.keys import (
    Source,
    branch_for,
    check_key,
    guard_source,
    paths_for,
    render_issue,
    worktree_for,
)


@pytest.mark.parametrize(("key", "backend"), [("issue-8", "local"), ("gh-3", "github")])
def test_a_key_belongs_to_its_backend(key, backend):
    check_key(key, backend)


@pytest.mark.parametrize(
    ("key", "backend", "says"),
    [
        ("gh-3", "local", "gh-3 is a github key, but the backend is local"),
        ("issue-8", "github", "issue-8 is a local key, but the backend is github"),
        ("8", "local", "'8' is not an issue key"),
        ("docs/issues/008.md", "local", "is not an issue key"),
        ("fj-2", "local", "fj-2 is a forgejo key, which is not supported yet"),
        # One issue, one key: issue-08 would be a second delivery of issue-8.
        ("issue-08", "local", "'issue-08' is not an issue key"),
        ("gh-0", "github", "'gh-0' is not an issue key"),
    ],
)
def test_a_key_for_another_backend_is_refused(key, backend, says):
    with pytest.raises(ConfigError, match=re.escape(says)):
        check_key(key, backend)


def test_the_branch_and_worktree_are_named_from_the_key():
    assert branch_for("gh-3", "") == "feature/gh-3"
    assert worktree_for(Path("/src/caw-project"), "gh-3", "") == Path("/src/caw-gh-3")


def test_a_named_run_builds_beside_it():
    assert branch_for("issue-8", "loop") == "feature/issue-8-loop"
    assert worktree_for(Path("/src/caw-project"), "issue-8", "loop") == Path(
        "/src/caw-issue-8-loop"
    )


def test_every_path_an_agent_sees_is_under_the_keys_plan_folder():
    paths = paths_for("gh-3")

    assert paths.plan_dir == "docs/plans/gh-3"
    assert paths.issue_copy == "docs/plans/gh-3/00-issue.md"
    assert paths.plan == "docs/plans/gh-3/01-implementation-plan.md"
    assert paths.red_report == "docs/plans/gh-3/02-red-tests.md"
    assert paths.green_report == "docs/plans/gh-3/03-green-report.md"
    assert paths.proof == "docs/plans/gh-3/04-proof.md"
    assert paths.answers == "docs/plans/gh-3/needs-human.md"
    assert paths.reviews == "docs/plans/gh-3/reviews"
    assert paths.source == "docs/plans/gh-3/source.json"
    assert paths.evidence == "build/acceptance"


def test_the_issue_copy_is_the_same_shape_whatever_the_backend():
    issue = Issue(
        key="gh-3",
        number=3,
        title="Display names",
        body="## Summary\r\n\r\nUnique names.\r\n\r\n",
        url="https://github.com/caw-project/ch09/issues/3",
    )

    assert render_issue(issue) == "# Display names\n\n## Summary\n\nUnique names.\n"


# --- where an issue came from --------------------------------------------------

SOURCE = Source(backend="github", url="https://github.com/caw-project/ch09", number=3)


def test_the_first_fetch_records_the_source(tmp_path):
    path = tmp_path / "source.json"

    guard_source(path, SOURCE)

    assert json.loads(path.read_text()) == {
        "backend": "github",
        "url": "https://github.com/caw-project/ch09",
        "number": 3,
    }


def test_the_same_source_again_passes(tmp_path):
    path = tmp_path / "source.json"
    guard_source(path, SOURCE)

    guard_source(path, SOURCE)


@pytest.mark.parametrize(
    "other",
    [
        Source(backend="github", url="https://github.com/someone/else", number=3),
        Source(backend="local", url=None, number=3),
    ],
)
def test_another_source_for_the_same_key_is_refused(tmp_path, other):
    path = tmp_path / "source.json"
    guard_source(path, SOURCE)

    with pytest.raises(ConfigError, match="already holds"):
        guard_source(path, other)
