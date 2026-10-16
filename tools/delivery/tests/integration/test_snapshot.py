"""What a stage wrote, seen against the branch's base rather than what is uncommitted — so the
runner's own checkpoint commits don't make every committed file look changed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from delivery.run.record import snapshot, touched_between

IGNORE = ("build/", "docs/plans/gh-3/run/")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 — fixed program, argument list.
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def branch(tmp_path) -> Path:
    """A repo with `kept.md` and `gone.md` on main, checked out on feature/gh-3."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "kept.md").write_text("main\n")
    (root / "gone.md").write_text("main\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-qm", "init")
    git(root, "switch", "-qc", "feature/gh-3")
    return root


def test_a_change_committed_since_the_base_is_in_the_snapshot(branch):
    (branch / "plan.md").write_text("the plan\n")
    git(branch, "add", ".")
    git(branch, "commit", "-qm", "checkpoint")

    assert set(snapshot(branch, "main", ignore=IGNORE)) == {"plan.md"}


def test_a_commit_on_the_branch_changes_nothing_a_snapshot_sees(branch):
    (branch / "plan.md").write_text("the plan\n")
    before = snapshot(branch, "main", ignore=IGNORE)

    git(branch, "add", ".")
    git(branch, "commit", "-qm", "checkpoint")

    assert touched_between(before, snapshot(branch, "main", ignore=IGNORE)) == []


def test_untracked_modified_and_deleted_paths_all_count(branch):
    (branch / "new.md").write_text("new\n")
    (branch / "kept.md").write_text("changed\n")
    (branch / "gone.md").unlink()

    snap = snapshot(branch, "main", ignore=IGNORE)

    assert set(snap) == {"new.md", "kept.md", "gone.md"}
    assert snap["gone.md"] == "deleted"


def test_a_deletion_committed_since_the_base_counts(branch):
    git(branch, "rm", "-q", "gone.md")
    git(branch, "commit", "-qm", "checkpoint")

    assert snapshot(branch, "main", ignore=IGNORE) == {"gone.md": "deleted"}


def test_the_run_state_and_build_are_never_in_a_snapshot(branch):
    run = branch / "docs" / "plans" / "gh-3" / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text("{}\n")
    git(branch, "add", ".")
    git(branch, "commit", "-qm", "checkpoint")
    (run / "history.log").write_text("01 plan-writer done\n")
    (branch / "build").mkdir()
    (branch / "build" / "x.json").write_text("{}\n")

    assert snapshot(branch, "main", ignore=IGNORE) == {}
