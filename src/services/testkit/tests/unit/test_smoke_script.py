"""`scripts/smoke.sh` — its arguments, and where it finds the origin.

Each test runs the real script under `/bin/bash` (3.2 on macOS) with an environment built
from nothing, a fake `uv` on `PATH` that records what it was run with, and — for the
default origin — a fake `deploy.sh` through `SMOKE_DEPLOY_SH`. Nothing reaches the network,
a browser or a cluster: what pytest would do with the pack is the pack's own business.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
SCRIPT = REPO / "scripts" / "smoke.sh"
BASH = "/bin/bash"

# Records its arguments, one per line, its working directory and the three variables
# smoke.sh passes, then exits FAKE_UV_EXIT.
FAKE_UV = """#!/bin/bash
printf '%s\\n' "$@" >"$FAKE_UV_LOG.args"
printf '{"cwd": "%s", "origin": "%s", "out": "%s", "pythonpath": "%s"}\\n' \\
    "$PWD" "$SMOKE_ORIGIN" "$SMOKE_OUT" "$PYTHONPATH" >"$FAKE_UV_LOG.env"
exit "${FAKE_UV_EXIT:-0}"
"""

FAKE_DEPLOY = """#!/bin/bash
printf '%s\\n' "$*" >>"$FAKE_DEPLOY_LOG"
[ "${FAKE_DEPLOY_EXIT:-0}" = 0 ] || { echo "preview's tunnels are not running" >&2; exit 1; }
printf 'APP_ORIGIN=https://quick-fake-tunnel.trycloudflare.com\\n'
printf 'OBJECT_STORE_ORIGIN=https://other-fake-tunnel.trycloudflare.com\\n'
"""


class Run:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for name, body in (("uv", FAKE_UV), ("deploy.sh", FAKE_DEPLOY)):
            path = bin_dir / name
            path.write_text(body)
            path.chmod(0o755)
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp),
            "FAKE_UV_LOG": str(tmp / "uv"),
            "FAKE_DEPLOY_LOG": str(tmp / "deploy.log"),
            "SMOKE_DEPLOY_SH": str(bin_dir / "deploy.sh"),
        }

    def __call__(
        self, *args: str, cwd: Path = REPO, **env: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — argv is the test's own: /bin/bash and literals
            [BASH, str(SCRIPT), *args],
            cwd=cwd,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def uv_args(self) -> list[str]:
        return (self.tmp / "uv.args").read_text().splitlines()

    def uv_env(self) -> dict[str, str]:
        return json.loads((self.tmp / "uv.env").read_text())

    def uv_ran(self) -> bool:
        return (self.tmp / "uv.args").exists()


@pytest.fixture
def run(tmp_path: Path) -> Run:
    return Run(tmp_path)


def test_runs_the_standard_pack_against_the_origin(run: Run, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = run("--origin", "https://example.test", "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert run.uv_args() == [
        "run",
        "pytest",
        "-p",
        "smoke.fixtures",
        "tests/smoke",
        f"--junitxml={out}/junit.xml",
    ]
    env = run.uv_env()
    assert env["cwd"] == str(REPO)
    assert env["origin"] == "https://example.test"
    assert env["out"] == str(out)
    assert env["pythonpath"].split(":")[0] == str(REPO / "tests")
    assert out.is_dir()


def test_a_trailing_slash_is_dropped(run: Run, tmp_path: Path) -> None:
    run("--origin", "http://localhost:8080/", "--out", str(tmp_path / "o"))
    assert run.uv_env()["origin"] == "http://localhost:8080"


@pytest.mark.parametrize("origin", ["localhost:8080", "ftp://example.test", "https://"])
def test_an_origin_that_is_not_http_is_refused(run: Run, tmp_path: Path, origin: str) -> None:
    result = run("--origin", origin, "--out", str(tmp_path / "o"))
    assert result.returncode != 0
    assert "http" in result.stderr
    assert not run.uv_ran()


def test_extra_paths_are_made_absolute(run: Run, tmp_path: Path) -> None:
    caller = tmp_path / "caller"
    (caller / "pack").mkdir(parents=True)
    run("--origin", "https://example.test", "--out", str(tmp_path / "o"), "pack", cwd=caller)
    args = run.uv_args()
    assert args[4:6] == ["tests/smoke", str(caller / "pack")]


def test_a_relative_out_is_under_the_repo(run: Run) -> None:
    run("--origin", "https://example.test", "--out", "build/smoke-unit-test")
    try:
        assert run.uv_env()["out"] == str(REPO / "build" / "smoke-unit-test")
    finally:
        (REPO / "build" / "smoke-unit-test").rmdir()


def test_arguments_after_a_double_dash_go_to_pytest(run: Run, tmp_path: Path) -> None:
    run("--origin", "https://example.test", "--out", str(tmp_path / "o"), "--", "-k", "sign_in")
    assert run.uv_args()[-2:] == ["-k", "sign_in"]


def test_exits_with_pytest_status(run: Run, tmp_path: Path) -> None:
    result = run("--origin", "https://example.test", "--out", str(tmp_path / "o"), FAKE_UV_EXIT="1")
    assert result.returncode == 1
    assert "junit.xml" in result.stderr


def test_no_origin_takes_this_branch_preview(run: Run, tmp_path: Path) -> None:
    result = run("--out", str(tmp_path / "o"))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "deploy.log").read_text().strip() == "preview url"
    assert run.uv_env()["origin"] == "https://quick-fake-tunnel.trycloudflare.com"


def test_no_preview_names_preview_up_and_runs_nothing(run: Run, tmp_path: Path) -> None:
    result = run("--out", str(tmp_path / "o"), FAKE_DEPLOY_EXIT="1")
    assert result.returncode != 0
    assert "preview up" in result.stderr
    assert not run.uv_ran()


def test_an_unknown_option_is_refused(run: Run) -> None:
    result = run("--origni", "https://example.test")
    assert result.returncode != 0
    assert "--origni" in result.stderr
    assert not run.uv_ran()
