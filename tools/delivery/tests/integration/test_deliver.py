"""A delivery from a GitHub issue, against a real git repo, a fake `gh` and a fake agent.

`.claude/delivery/loop-test.sh` proves the state machine through `scripts/deliver.sh` with the
local backend; this proves what only a remote backend does — the fetch, the issue copy,
`source.json` and every name taken from the key.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from delivery.errors import BackendError
from delivery.github import GitHubBackend
from delivery.resolve import BackendConfig
from delivery.run import deliver

URL = "https://github.com/caw-project/ch09"
BODY = "## Summary\n\nDisplay names are unique.\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 — fixed program, argument list.
        ["git", *args],  # noqa: S607 — git from PATH, as the runner finds it.
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    """A primary checkout with the two plan agents committed on main."""
    root = tmp_path / "caw-project"
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    for stage in ("plan-writer", "plan-reviewer"):
        (agents / f"{stage}.md").write_text(f"---\nname: {stage}\nmodel: opus\n---\n")
    (root / ".env.example").write_text("APP_ORIGIN=\n")
    git(tmp_path, "init", "-q", "-b", "main", str(root))
    git(root, "add", ".")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    return root


class FakeAgent:
    """The plan-writer writes its plan; the plan-reviewer stops for a human."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, args: list[str], cwd: Path) -> str:
        prompt = args[args.index("-p") + 1]
        stage = args[args.index("--agent") + 1]
        self.prompts.append(prompt)
        lines = dict(line.split(": ", 1) for line in prompt.splitlines())
        if stage == "plan-writer":
            (cwd / lines["Plan"]).write_text("# The plan\n")
            out = {"status": "done", "summary": "planned", "files": [], "questions": []}
        else:
            out = {
                "status": "needs_human",
                "summary": "a question",
                "files": [],
                "questions": ["Which?"],
            }
        return json.dumps(
            {
                "subtype": "success",
                "is_error": False,
                "num_turns": 3,
                "total_cost_usd": 0.5,
                "duration_ms": 60000,
                "session_id": "s",
                "structured_output": out,
            }
        )


def run(repo, gh, agent, url=URL):
    return deliver(
        "gh-3",
        restart=False,
        config=BackendConfig(kind="github", url=url),
        backend=GitHubBackend(url, run=gh),
        root=repo,
        env={"DELIVER_RETRY_WAIT": "0"},
        agent=agent,
        which=lambda cmd: f"/usr/bin/{cmd}",
        runs=lambda args: True,
    )


@pytest.fixture
def issue_3(gh, gh_issue):
    gh.answers["issue view"] = gh_issue(number=3, title="Display names", body=BODY)
    return gh


def test_a_github_issue_is_delivered_under_its_key(repo, issue_3):
    agent = FakeAgent()

    code = run(repo, issue_3, agent)

    worktree = repo.parent / "caw-gh-3"
    plans = worktree / "docs" / "plans" / "gh-3"
    assert code == 2
    assert git(worktree, "branch", "--show-current").strip() == "feature/gh-3"
    assert (plans / "00-issue.md").read_text() == f"# Display names\n\n{BODY}"
    assert json.loads((plans / "source.json").read_text()) == {
        "backend": "github",
        "url": URL,
        "number": 3,
    }
    assert (plans / "01-implementation-plan.md").exists()
    assert (plans / "needs-human.md").read_text().startswith("# gh-3 — questions for a human\n")
    assert agent.prompts[0].splitlines()[:3] == [
        "Issue: gh-3",
        "Issue file: docs/plans/gh-3/00-issue.md",
        "Plan dir: docs/plans/gh-3/",
    ]
    assert not any(URL in prompt for prompt in agent.prompts)
    history = (worktree / "build" / "delivery" / "history.log").read_text().splitlines()
    assert [line.split(" [")[0] for line in history] == [
        "01 plan-writer done",
        "02 plan-reviewer needs_human",
    ]


def test_a_rerun_resumes_where_it_stopped_with_the_issue_fetched_again(repo, issue_3, gh_issue):
    run(repo, issue_3, FakeAgent())
    issue_3.answers["issue view"] = gh_issue(
        number=3, title="Display names", body="## Summary\n\nEdited.\n"
    )
    agent = FakeAgent()

    run(repo, issue_3, agent)

    plans = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3"
    assert "Edited." in (plans / "00-issue.md").read_text()
    assert agent.prompts[0].splitlines()[5] == "Stage: plan-reviewer, round 1 of 3"


def test_a_finished_delivery_is_left_as_it_was(repo, issue_3, gh_issue):
    run(repo, issue_3, FakeAgent())
    run_dir = repo.parent / "caw-gh-3" / "build" / "delivery"
    (run_dir / "state.json").write_text(
        (run_dir / "state.json").read_text().replace('"needs_human"', '"done"')
    )
    copy = repo.parent / "caw-gh-3" / "docs" / "plans" / "gh-3" / "00-issue.md"
    before = copy.read_text()
    issue_3.answers["issue view"] = gh_issue(number=3, title="Renamed since", body=BODY)

    code = run(repo, issue_3, FakeAgent())

    assert code == 0
    assert copy.read_text() == before


def test_the_same_key_from_another_repo_is_refused(repo, issue_3, capsys):
    run(repo, issue_3, FakeAgent())
    other = "https://github.com/someone/else"

    code = run(repo, issue_3, FakeAgent(), url=other)

    assert code == 2
    assert "already holds" in capsys.readouterr().err


def test_an_issue_that_cannot_be_fetched_stops_before_any_worktree(repo, gh, capsys):
    gh.answers["issue view"] = BackendError("could not find issue 3")

    code = run(repo, gh, FakeAgent())

    assert code == 1
    assert "could not find issue 3" in capsys.readouterr().err
    assert not (repo.parent / "caw-gh-3").exists()


def test_a_missing_tool_stops_before_the_fetch(repo, gh, capsys):
    code = deliver(
        "gh-3",
        restart=False,
        config=BackendConfig(kind="github", url=URL),
        backend=GitHubBackend(URL, run=gh),
        root=repo,
        env={},
        agent=FakeAgent(),
        which=lambda cmd: None if cmd == "gh" else f"/usr/bin/{cmd}",
        runs=lambda args: True,
    )

    assert code == 1
    assert "'gh' is not on PATH" in capsys.readouterr().err
    assert gh.calls == []
