"""Pre-flight: everything a run needs from this machine, checked before the first stage.

The stages that need most of it come last: the test pair installs and runs Vitest and
pytest, the code-writer's verification runs scripts/test.sh, whose e2e layer builds the
Compose test stack, and the acceptance-reviewer deploys a preview (cloudflared, k3d,
kubectl, curl). A missing tool found there costs every stage before it. Every problem is
listed at once, so one fix-and-rerun is enough.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from delivery.resolve import GITHUB

#: The workflow itself, and what the stages run: tests, lint, the scripts' layers.
TOOLS = (
    "claude",
    "git",
    "uv",
    "node",
    "npm",
    "python3",
    "helm",
    "docker",
    "cloudflared",
    "k3d",
    "kubectl",
    "curl",
)


def runs_quietly(args: list[str]) -> bool:
    try:
        return subprocess.run(args, capture_output=True, check=False).returncode == 0  # noqa: S603
    except OSError:
        return False


def problems(
    backend: str,
    *,
    root: Path,
    which: Callable[[str], str | None] = shutil.which,
    runs: Callable[[list[str]], bool] = runs_quietly,
) -> list[str]:
    tools = (*TOOLS, "gh") if backend == GITHUB else TOOLS
    found = [f"'{cmd}' is not on PATH" for cmd in tools if which(cmd) is None]
    if which("docker") is not None:
        if not runs(["docker", "info"]):
            found.append("the Docker daemon is not reachable — the code-writer's e2e run needs it")
        if not runs(["docker", "compose", "version"]):
            found.append(
                "'docker compose' (v2) is not available — the e2e layer brings its stack up with it"
            )
    if not (root / ".env.example").is_file():
        found.append(
            ".env.example is missing — a worktree's .env is made from it for the e2e layer"
        )
    return found
