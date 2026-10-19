"""Before a run starts, its branch is brought level with the remote's — tracked, fast-forwarded
or left — and never merged or forced. A person's answer pushed to the branch comes in this way."""

from __future__ import annotations

import pytest
from delivery.run.sync import Sync, decide


@pytest.mark.parametrize(
    ("local", "remote", "ahead", "behind", "dirty", "action"),
    [
        # Nothing anywhere: a new branch from the base.
        (False, False, 0, 0, False, "new"),
        # Only on the remote — another machine ran it: carry on from there.
        (False, True, 0, 0, False, "track"),
        # Only here: the next push creates it.
        (True, False, 0, 0, False, "none"),
        (True, True, 0, 0, False, "none"),
        # Checkpoints not pushed yet: the next push takes them.
        (True, True, 2, 0, False, "none"),
        (True, True, 2, 0, True, "none"),
        # Someone pushed, here is clean: fast-forward.
        (True, True, 0, 1, False, "fast-forward"),
    ],
)
def test_the_branch_is_brought_level_without_a_merge(local, remote, ahead, behind, dirty, action):
    assert decide(local=local, remote=remote, ahead=ahead, behind=behind, dirty=dirty) == Sync(
        action
    )


def test_a_branch_that_has_diverged_stops_the_run():
    sync = decide(local=True, remote=True, ahead=1, behind=2, dirty=False)

    assert sync.action == "stop"
    assert "diverged" in sync.reason
    assert "1 commit" in sync.reason
    assert "2 commits" in sync.reason


def test_uncommitted_work_with_the_remote_ahead_stops_the_run():
    sync = decide(local=True, remote=True, ahead=0, behind=1, dirty=True)

    assert sync.action == "stop"
    assert "uncommitted" in sync.reason
