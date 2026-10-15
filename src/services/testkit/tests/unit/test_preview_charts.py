"""What the two charts render for a preview: the origins they are given.

`helm template` as a subprocess, against the real charts and the real
`values-*.yaml`; no cluster, no network. A test fails — it never skips — when
`helm` is missing: `scripts/test.sh lint` needs it too, and a skipped chart test
reads as green.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[5]
APP_CHART = REPO / "charts" / "collabhub"
DEPS_CHART = REPO / "charts" / "collabhub-deps"
A = "https://quiet-fox-runs.trycloudflare.com"
B = "https://bold-owl-sings.trycloudflare.com"


@pytest.fixture(scope="module")
def helm() -> str:
    found = shutil.which("helm")
    if found is None:
        pytest.fail("helm is required for the chart tests — scripts/test.sh lint needs it too")
    return found


def _run(argv: list[str], helm: str, home: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{Path(helm).parent}:/usr/bin:/bin", "HOME": str(home), "IMAGE_TAG": "t"}
    return subprocess.run(  # noqa: S603 — argv is the test's own: helm, /bin/bash and literals
        argv, env=env, cwd=REPO, text=True, capture_output=True, timeout=60, check=False
    )


@pytest.fixture
def deps_chart_files(helm: str, tmp_path: Path) -> list[str]:
    """The real `--set-file` list from common.sh, never a copy."""
    done = _run(
        ["/bin/bash", "-c", '. scripts/lib/common.sh; printf "%s\\n" "${DEPS_CHART_FILES[@]}"'],
        helm,
        tmp_path,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


def _app(
    helm: str, home: Path, template: str, *sets: str, values: str = "values-k3d.yaml"
) -> subprocess.CompletedProcess[str]:
    argv = [
        helm,
        "template",
        "collabhub",
        str(APP_CHART),
        "--values",
        str(APP_CHART / values),
        "--api-versions",
        "keda.sh/v1alpha1",
        "--show-only",
        template,
    ]
    for item in sets:
        argv += ["--set-string", item]
    return _run(argv, helm, home)


def _deps(
    helm: str, home: Path, files: list[str], template: str, *sets: str
) -> subprocess.CompletedProcess[str]:
    argv = [
        helm,
        "template",
        "collabhub-deps",
        str(DEPS_CHART),
        "--values",
        str(DEPS_CHART / "values-k3d.yaml"),
        *files,
        "--api-versions",
        "keda.sh/v1alpha1",
        "--show-only",
        template,
    ]
    for item in sets:
        argv += ["--set-string", item]
    return _run(argv, helm, home)


def _documents(rendered: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    assert rendered.returncode == 0, rendered.stderr
    return [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]


def _find_env(node: Any, name: str) -> str | None:
    """The value of the container env var `name`, wherever in a manifest it is."""
    if isinstance(node, dict):
        if node.get("name") == name and "value" in node:
            return node["value"]
        for child in node.values():
            found = _find_env(child, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_env(child, name)
            if found is not None:
                return found
    return None


MESSAGING_CONFIGMAP = "templates/messaging/configmap.yaml"
MESSAGING_DEPLOYMENT = "templates/messaging/deployment.yaml"


def _cors(helm: str, home: Path, *sets: str, values: str = "values-k3d.yaml") -> str | None:
    (configmap,) = _documents(_app(helm, home, MESSAGING_CONFIGMAP, *sets, values=values))
    return configmap["data"].get("CORS_ALLOWED_ORIGINS")


def _checksum(helm: str, home: Path, origin: str) -> str:
    rendered = _app(
        helm, home, MESSAGING_DEPLOYMENT, "ingress.host=a.localhost", f"origin={origin}"
    )
    (deployment,) = _documents(rendered)
    return deployment["spec"]["template"]["metadata"]["annotations"]["checksum/config"]


def test_messaging_cors_is_the_app_origin_on_k3d(helm: str, tmp_path: Path) -> None:
    """R5: with the list always set, engine.io compares the browser's Origin as given."""
    value = _cors(helm, tmp_path, "ingress.host=a.localhost", f"origin={A}")

    assert value == json.dumps([A])


def test_messaging_cors_is_the_app_origin_on_the_lab(helm: str, tmp_path: Path) -> None:
    """R5 holds in every environment, the lab's plain http included."""
    value = _cors(
        helm,
        tmp_path,
        "ingress.host=lab.example",
        "origin=http://lab.example",
        values="values-lab.yaml",
    )

    assert value == json.dumps(["http://lab.example"])


def test_the_app_chart_refuses_no_origin(helm: str, tmp_path: Path) -> None:
    """An empty list would put back the predicate that refuses a tunnel's https origin."""
    refused = _app(helm, tmp_path, MESSAGING_CONFIGMAP, "ingress.host=a.localhost")
    accepted = _app(helm, tmp_path, MESSAGING_CONFIGMAP, "ingress.host=a.localhost", f"origin={A}")

    assert refused.returncode != 0
    assert "origin is empty" in refused.stderr
    assert accepted.returncode == 0, accepted.stderr


def test_messaging_rolls_when_the_origin_changes(helm: str, tmp_path: Path) -> None:
    """The list comes from outside the component's env, so its checksum must see it."""
    first = _checksum(helm, tmp_path, A)
    again = _checksum(helm, tmp_path, A)
    other = _checksum(helm, tmp_path, B)

    assert first == again
    assert first != other


def test_garage_is_routed_on_the_object_store_origin(
    helm: str, tmp_path: Path, deps_chart_files: list[str]
) -> None:
    """R4: the presigned URL's host is the tunnel's, so the Ingress must answer on it."""
    rendered = _deps(
        helm,
        tmp_path,
        deps_chart_files,
        "templates/garage.yaml",
        f"origin={A}",
        f"objectStoreOrigin={B}",
    )

    docs = _documents(rendered)
    (ingress,) = [doc for doc in docs if doc["kind"] == "Ingress"]
    hosts = [rule["host"] for rule in ingress["spec"]["rules"]]
    assert hosts == ["bold-owl-sings.trycloudflare.com"]
    assert "s3.quiet-fox-runs" not in rendered.stdout
    # The browser's origin is the app's, whichever host it uploads to.
    assert _find_env(docs, "GARAGE_CORS_ORIGINS") == A


def test_garage_defaults_to_s3_of_the_app_host(
    helm: str, tmp_path: Path, deps_chart_files: list[str]
) -> None:
    """Green by design: plain k3d and the lab keep `s3.<host>` (R4)."""
    rendered = _deps(
        helm, tmp_path, deps_chart_files, "templates/garage.yaml", "origin=http://localhost:8080"
    )

    (ingress,) = [doc for doc in _documents(rendered) if doc["kind"] == "Ingress"]
    assert [rule["host"] for rule in ingress["spec"]["rules"]] == ["s3.localhost"]
