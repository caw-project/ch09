"""A real Garage for the tests that need object storage (register D34).

One container per session, started the first time a test asks. It is made ready
by **the real bootstrap** — `charts/collabhub-deps/files/garage-bootstrap.py`,
the script Compose, the test stack and k3d all run — not a copy of it, so a test
that passes here proves the bootstrap's layout, bucket, key, grant and CORS too.

There is no S3 client in this module: the tests that need one sign with boto3
(Asset's own), and the ones here use the admin API and plain HTTP, as the
bootstrap does.

Heavy imports sit inside the fixture, as in `testkit.containers`.
"""

from __future__ import annotations

import importlib.util
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from testkit import images

ROOT = Path(__file__).resolve().parents[4]
CONFIG = ROOT / "docker" / "garage" / "garage.toml"
BOOTSTRAP = ROOT / "charts" / "collabhub-deps" / "files" / "garage-bootstrap.py"

S3_PORT = 3900
ADMIN_PORT = 3903

#: Garage imports only this shape of key: `GK` and 24 hex, then 64 hex.
ACCESS_KEY = "GK000000000000000000000001"
SECRET_KEY = "0" * 63 + "1"
#: The `admin_token` in `docker/garage/garage.toml`.
ADMIN_TOKEN = "collabhub-local-admin-token"
BUCKET = "collabhub-assets"
#: The one origin the bootstrap allows; the CORS test shows another is refused.
CORS_ORIGIN = "http://spa.test"

_START_SECONDS = 60


@dataclass(frozen=True)
class GarageServer:
    """Where a bootstrapped Garage listens, and the key that may use its bucket."""

    #: The S3 API, as a test on the host reaches it.
    endpoint: str
    #: The admin API, for tests that read what the bootstrap configured.
    admin_url: str
    access_key: str
    secret_key: str
    bucket: str
    admin_token: str = ADMIN_TOKEN
    cors_origin: str = CORS_ORIGIN


def _wait_until_serving(admin_url: str) -> None:
    """Poll the admin API's unauthenticated `/health` until Garage answers at all.

    Any HTTP answer is enough — it is a 503 until a layout exists — because
    the bootstrap's own `retry` covers the layout settling.
    """
    deadline = time.monotonic() + _START_SECONDS
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{admin_url}/health", timeout=2)  # noqa: S310
            return
        except urllib.error.HTTPError:
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.5)
    raise AssertionError(f"Garage did not start within {_START_SECONDS} s")


def _bootstrap(admin_url: str) -> None:
    """Run the real bootstrap's `main()` against `admin_url`, leaving the environment as found."""
    environment = {
        "GARAGE_ADMIN_URL": admin_url,
        "GARAGE_ADMIN_TOKEN": ADMIN_TOKEN,
        "GARAGE_BUCKET": BUCKET,
        "GARAGE_ACCESS_KEY_ID": ACCESS_KEY,
        "GARAGE_SECRET_ACCESS_KEY": SECRET_KEY,
        "GARAGE_CAPACITY_BYTES": str(1024**3),
        "GARAGE_CORS_ORIGINS": CORS_ORIGIN,
    }
    with pytest.MonkeyPatch.context() as patch:
        for name, value in environment.items():
            patch.setenv(name, value)
        # The script reads its settings at import, so it is loaded under the
        # environment above and not imported by name.
        spec = importlib.util.spec_from_file_location("garage_bootstrap", BOOTSTRAP)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()


@pytest.fixture(scope="session")
def garage_server() -> Iterator[GarageServer]:
    """Garage as Compose runs it, bootstrapped as every environment bootstraps it."""
    from testcontainers.core.container import DockerContainer

    container = (
        DockerContainer(images.GARAGE)
        .with_exposed_ports(S3_PORT, ADMIN_PORT)
        .with_volume_mapping(str(CONFIG), "/etc/garage.toml", "ro")
    )
    with container:
        host = container.get_container_host_ip()
        admin_url = f"http://{host}:{container.get_exposed_port(ADMIN_PORT)}"
        _wait_until_serving(admin_url)
        _bootstrap(admin_url)
        yield GarageServer(
            endpoint=f"http://{host}:{container.get_exposed_port(S3_PORT)}",
            admin_url=admin_url,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            bucket=BUCKET,
        )
