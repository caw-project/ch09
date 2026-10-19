"""Bringing a delivery's branch level with its remote before a run — the one decision, as a
pure function over what git reports. A person's answer pushed to the branch, or another
machine's checkpoints, come in this way. Nothing is ever merged or forced: a branch that has
diverged is a person's to sort out."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sync:
    #: new · track · fast-forward · none · stop
    action: str
    reason: str = ""


def decide(*, local: bool, remote: bool, ahead: int, behind: int, dirty: bool) -> Sync:
    """`ahead` and `behind` count the local branch's commits against the remote's; `dirty` is
    uncommitted work in the worktree, when there is one."""
    if not local:
        return Sync("track" if remote else "new")
    if not remote or behind == 0:
        # Commits only here are checkpoints not pushed yet: the next push takes them.
        return Sync("none")
    if ahead:
        return Sync(
            "stop",
            f"the branch has diverged from the remote — {commits(ahead)} only here,"
            f" {commits(behind)} only there. Bring them together by hand, then run this again",
        )
    if dirty:
        return Sync(
            "stop",
            f"the remote is {commits(behind)} ahead and the worktree has uncommitted changes"
            " — commit or discard them, then run this again",
        )
    return Sync("fast-forward")


def commits(n: int) -> str:
    return f"{n} commit{'' if n == 1 else 's'}"
