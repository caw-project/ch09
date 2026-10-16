"""Pre-flight: everything a run needs from this machine, checked before the first stage."""

from __future__ import annotations

from delivery.run.preflight import problems

TOOLS = [
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
]


def found(*missing):
    return lambda cmd: None if cmd in missing else f"/usr/bin/{cmd}"


def check(tmp_path, backend="local", which=None, runs=lambda args: True):
    (tmp_path / ".env.example").touch()
    return problems(backend, root=tmp_path, which=which or found(), runs=runs)


def test_a_machine_with_everything_passes(tmp_path):
    assert check(tmp_path) == []


def test_every_missing_tool_is_named_at_once(tmp_path):
    assert check(tmp_path, which=found("k3d", "helm")) == [
        "'helm' is not on PATH",
        "'k3d' is not on PATH",
    ]


def test_jq_is_no_longer_needed(tmp_path):
    asked = []

    check(tmp_path, which=lambda cmd: asked.append(cmd) or f"/usr/bin/{cmd}")

    assert "jq" not in asked
    assert asked[: len(TOOLS)] == TOOLS


def test_gh_is_needed_only_for_github(tmp_path):
    assert check(tmp_path, which=found("gh")) == []
    assert check(tmp_path, backend="github", which=found("gh")) == ["'gh' is not on PATH"]


def test_the_docker_daemon_and_compose_v2_are_needed(tmp_path):
    said = check(tmp_path, runs=lambda args: False)

    assert said == [
        "the Docker daemon is not reachable — the code-writer's e2e run needs it",
        "'docker compose' (v2) is not available — the e2e layer brings its stack up with it",
    ]


def test_a_missing_env_example_is_named(tmp_path):
    said = problems("local", root=tmp_path, which=found(), runs=lambda args: True)

    assert said == [".env.example is missing — a worktree's .env is made from it for the e2e layer"]
