"""Every Python service image can resolve the uv workspace it is built from.

Each service's Dockerfile runs `uv sync --locked --package <service>`, which reads the
root `pyproject.toml` — and that names every workspace member, installed or not. A member
the build context doesn't copy fails the sync with "is not a workspace member", in every
image at once. Reads the files from disk — no network, no Docker.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SERVICES = ("auth", "messaging", "canvas", "asset", "worker")


def member_roots() -> set[str]:
    """`src/services/*` and `tools/*` -> `src/services/`, `tools/`."""
    members = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["uv"]["workspace"][
        "members"
    ]
    return {m.split("*", 1)[0] for m in members}


def copied(dockerfile: Path) -> set[str]:
    """The sources of the build stage's plain COPY lines — not `--from` an image."""
    lines = dockerfile.read_text().splitlines()
    return {
        source
        for line in lines
        if (match := re.match(r"COPY\s+(?!--from)(.+)\s+\S+$", line.strip()))
        for source in match.group(1).split()
    }


@pytest.mark.parametrize("service", SERVICES)
def test_a_service_image_copies_every_workspace_member(service):
    sources = copied(ROOT / "docker" / service / "Dockerfile")

    assert member_roots() <= sources
