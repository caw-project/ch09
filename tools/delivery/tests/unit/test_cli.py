"""The `delivery` CLI — what the issue-writer skill and, next, `deliver.sh` call."""

from __future__ import annotations

import json

import pytest
from delivery.cli import main

BODY = "## Summary\n\nPins a message.\n"
GITHUB = ["--backend", "github", "--url", "https://github.com/sixeyed/claude-at-work-project"]


@pytest.fixture
def body_file(tmp_path):
    path = tmp_path / "draft.md"
    path.write_text(BODY)
    return str(path)


def cli(capsys, root, *argv, env=None, run=None):
    """Runs the CLI; returns (exit code, stdout, stderr)."""
    code = main(list(argv), env=env or {}, root=root, run=run)
    out, err = capsys.readouterr()
    return code, out, err


# --- local -----------------------------------------------------------------


def test_check_passes_for_local(capsys, issues_root):
    code, out, _ = cli(capsys, issues_root, "check")

    assert code == 0
    assert "local" in out


def test_create_prints_the_issue_as_json(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys, issues_root, "issue", "create", "--title", "Pin a message", "--body-file", body_file
    )

    assert code == 0
    assert json.loads(out) == {
        "key": "issue-9",
        "number": 9,
        "title": "Pin a message",
        "body": BODY,
        "url": "docs/issues/009.md",
        "labels": [],
    }


def test_get_prints_the_issue_as_json(capsys, issues_root):
    code, out, _ = cli(capsys, issues_root, "issue", "get", "issue-8")

    assert code == 0
    assert json.loads(out)["title"] == "Better mobile experience"


def test_edit_prints_the_edited_issue(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys,
        issues_root,
        "issue",
        "edit",
        "issue-8",
        "--title",
        "Mobile",
        "--body-file",
        body_file,
    )

    assert code == 0
    assert json.loads(out)["title"] == "Mobile"
    assert json.loads(out)["body"] == BODY


def test_verify_exits_0_when_the_issue_matches_the_draft(capsys, issues_root, body_file):
    cli(
        capsys, issues_root, "issue", "create", "--title", "Pin a message", "--body-file", body_file
    )

    code, _, _ = cli(
        capsys, issues_root, "issue", "verify", "issue-9", "--title", "Pin a message",
        "--body-file", body_file,
    )  # fmt: skip

    assert code == 0


def test_verify_exits_1_and_lists_differences_when_it_does_not(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys, issues_root, "issue", "verify", "issue-8", "--title", "Pin a message",
        "--body-file", body_file,
    )  # fmt: skip

    assert code == 1
    assert "title" in out


def test_ensure_label_succeeds_locally(capsys, issues_root):
    code, _, _ = cli(capsys, issues_root, "ensure-label", "delivery")

    assert code == 0


def test_the_environment_selects_the_backend(capsys, issues_root, gh):
    env = {
        "DELIVERY_BACKEND": "github",
        "DELIVERY_URL": "https://github.com/sixeyed/claude-at-work-project",
    }

    code, out, _ = cli(capsys, issues_root, "check", env=env, run=gh)

    assert code == 0
    assert "github" in out
    gh.call("repo view")


# --- github, through the fake gh -------------------------------------------


def test_create_on_github_prints_the_key_and_url(capsys, issues_root, gh, body_file):
    code, out, _ = cli(
        capsys, issues_root, *GITHUB, "issue", "create", "--title", "Pin a message",
        "--body-file", body_file, "--label", "delivery", run=gh,
    )  # fmt: skip

    assert code == 0
    issue = json.loads(out)
    assert issue["key"] == "gh-5"
    assert issue["url"] == "https://github.com/sixeyed/claude-at-work-project/issues/5"
    args, stdin = gh.call("issue create")
    assert args[-2:] == ["--label", "delivery"]
    assert stdin == BODY


def test_ensure_label_on_github_has_a_default_description_and_colour(capsys, issues_root, gh):
    code, _, _ = cli(capsys, issues_root, *GITHUB, "ensure-label", "delivery", run=gh)

    assert code == 0
    args, _ = gh.call("label create")
    assert "--description" in args
    assert "--color" in args


# --- failures --------------------------------------------------------------


def test_bad_configuration_exits_2_with_a_message_and_no_traceback(capsys, issues_root):
    code, _, err = cli(capsys, issues_root, "--backend", "github", "check")

    assert code == 2
    assert "URL" in err
    assert "Traceback" not in err


def test_a_backend_failure_exits_1_with_a_message_and_no_traceback(capsys, issues_root):
    code, _, err = cli(capsys, issues_root, "issue", "get", "issue-42")

    assert code == 1
    assert "issue-42" in err
    assert "Traceback" not in err


def test_check_fails_with_1_when_the_backend_is_not_usable(capsys, tmp_path):
    code, _, err = cli(capsys, tmp_path, "check")

    assert code == 1
    assert "docs/issues" in err
