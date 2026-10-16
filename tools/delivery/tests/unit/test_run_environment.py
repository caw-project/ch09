"""What the runner hands an agent and the deploy script: the caller's environment, minus
the virtualenv `uv run` started the runner in — that one is the primary checkout's."""

from __future__ import annotations

import os

from delivery.run.invoke import agent_env


def test_the_runners_own_virtualenv_is_left_behind():
    env = {
        "VIRTUAL_ENV": "/src/caw-project/.venv",
        "PATH": os.pathsep.join(["/src/caw-project/.venv/bin", "/usr/local/bin", "/usr/bin"]),
        "HOME": "/home/me",
    }

    cleaned = agent_env(env)

    assert cleaned == {"PATH": os.pathsep.join(["/usr/local/bin", "/usr/bin"]), "HOME": "/home/me"}


def test_an_environment_without_one_is_unchanged():
    # Not run under uv: nothing comes off PATH, however the runner was installed.
    env = {"PATH": "/usr/bin", "DELIVER_MODEL": "haiku"}

    assert agent_env(env) == env
