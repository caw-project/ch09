"""`delivery deliver KEY` — what `scripts/deliver.sh` runs. Refusals that need no machine."""

from __future__ import annotations

import pytest
from delivery.cli import main, parser

GITHUB = ["--backend", "github", "--url", "https://github.com/caw-project/ch09"]


def test_deliver_takes_a_key_and_restart():
    args = parser().parse_args([*GITHUB, "deliver", "gh-3", "--restart"])

    assert (args.command, args.key, args.restart) == ("deliver", "gh-3", True)


def test_deliver_needs_a_key():
    with pytest.raises(SystemExit) as stopped:
        parser().parse_args(["deliver"])

    assert stopped.value.code == 2


def test_a_github_key_on_the_local_backend_exits_2(capsys, issues_root):
    code = main(["deliver", "gh-3"], env={}, root=issues_root)

    assert code == 2
    assert "gh-3 is a github key, but the backend is local" in capsys.readouterr().err


def test_a_local_key_on_github_exits_2(capsys, issues_root):
    code = main([*GITHUB, "deliver", "issue-8"], env={}, root=issues_root)

    assert code == 2
    assert "issue-8 is a local key, but the backend is github" in capsys.readouterr().err


def test_the_backend_comes_from_the_environment_as_for_every_command(capsys, issues_root):
    env = {"DELIVERY_BACKEND": "github", "DELIVERY_URL": "https://github.com/caw-project/ch09"}

    code = main(["deliver", "issue-8"], env=env, root=issues_root)

    assert code == 2
    assert "but the backend is github" in capsys.readouterr().err


def test_a_bad_setting_exits_2_before_anything_runs(capsys, issues_root):
    code = main(["deliver", "issue-8"], env={"DELIVER_MAX_ROUNDS": "0"}, root=issues_root)

    assert code == 2
    assert "DELIVER_MAX_ROUNDS must be a positive number" in capsys.readouterr().err
