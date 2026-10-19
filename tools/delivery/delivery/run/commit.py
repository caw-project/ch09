"""The runner commits its own branch — never an agent — so a delivery outlives the machine it
ran on: a checkpoint after every stage, and a commit for a stop, a failure and the approval.
Each covers everything outside build/, and is pushed unless DELIVER_PUSH=0. A push is never
forced: a rejected one stops the run."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from delivery.errors import RunError


class PushRejectedError(RunError):
    """The remote has commits this run doesn't: nothing more can be pushed from here."""


def checkpoint_message(key: str, stage: str, status: str, round_: int, summary: str) -> str:
    return message(f"delivery({key}): {stage} {status}, round {round_}", summary)


def stop_message(key: str, stage: str, round_: int, summary: str) -> str:
    return message(f"delivery({key}): needs a human at {stage}, round {round_}", summary)


def failed_message(key: str, stage: str, round_: int, error: str) -> str:
    return message(f"delivery({key}): failed at {stage}, round {round_}", error)


def accepted_message(key: str, summary: str) -> str:
    return message(f"delivery({key}): accepted", summary)


def message(subject: str, body: str) -> str:
    return f"{subject}\n\n{body.strip()}\n" if body.strip() else f"{subject}\n"


def git(cwd: Path, *args: str, stdin: str | None = None) -> str:
    done = subprocess.run(  # noqa: S603 — fixed program, argument list.
        ["git", "-C", str(cwd), *args],  # noqa: S607 — git from PATH.
        capture_output=True,
        text=True,
        input=stdin,
        check=False,
    )
    if done.returncode != 0:
        raise RunError(done.stderr.strip() or f"git {' '.join(args[:3])} failed")
    return done.stdout.strip()


def commit_all(worktree: Path, text: str) -> bool:
    """Commits everything outside build/ with the author git is configured with; False when
    there was nothing to commit."""
    git(worktree, "add", "-A")
    # build/ is ignored in the repo; this holds even where it isn't. (An exclude pathspec
    # naming an ignored directory makes `git add` fail.)
    git(worktree, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "build")
    try:
        git(worktree, "diff", "--cached", "--quiet")
    except RunError:
        git(worktree, "commit", "-q", "--no-verify", "-F", "-", stdin=text)
        return True
    return False


def set_aside(worktree: Path, paths: Iterable[str], keep: Path) -> None:
    """Moves what a stage wrote where it may not out of the branch, into `keep`, and puts
    each path back as HEAD — the last checkpoint — holds it, so the commit for the failure
    can't keep a refused write and a rerun doesn't build on one."""
    for path in paths:
        here = worktree / path
        if here.is_file() or here.is_symlink():
            (keep / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(here, keep / path, follow_symlinks=False)
        try:
            git(worktree, "cat-file", "-e", f"HEAD:{path}")
        except RunError:
            git(worktree, "rm", "-q", "--cached", "--ignore-unmatch", "--", path)
            here.unlink(missing_ok=True)
        else:
            git(worktree, "checkout", "-q", "HEAD", "--", path)


def push(worktree: Path, remote: str, branch: str) -> None:
    """Pushes the branch and tracks it. A rejection names both ends, and is never forced."""
    try:
        git(worktree, "push", "-q", "-u", remote, f"HEAD:refs/heads/{branch}")
    except RunError as e:
        ours = git(worktree, "rev-parse", "HEAD")
        try:
            git(worktree, "fetch", "-q", remote, branch)
            theirs = git(worktree, "rev-parse", "FETCH_HEAD")
        except RunError:
            raise RunError(f"the push of {branch} to {remote} failed: {e}") from e
        raise PushRejectedError(
            f"the push of {branch} to {remote} was rejected — this run is at {ours[:12]},"
            f" {remote} at {theirs[:12]}, and they have diverged. Nothing is forced: bring them"
            " together by hand, then run this again"
        ) from e
