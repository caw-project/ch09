"""The command-line sign-in's one real decision: when a redirect has left the IdP.

Behind one ingress, Dex and Auth share a host, so the host alone cannot say
where Dex ends. The script is loaded by path because its file name has a hyphen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "sign-in.py"


@pytest.fixture(scope="module")
def sign_in() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sign_in", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_idp_is_the_authorize_urls_directory(sign_in: ModuleType) -> None:
    authorize = httpx.URL("http://localhost:5556/dex/auth?client_id=collabhub-auth&state=s")

    assert sign_in.idp_root(authorize) == httpx.URL("http://localhost:5556/dex/")


def test_a_dex_page_on_a_shared_origin_is_inside_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert sign_in.within_idp(
        httpx.URL("http://a.localhost:8080/dex/auth/local?back=&state=s"), idp
    )


def test_auths_callback_on_a_shared_origin_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert not sign_in.within_idp(
        httpx.URL("http://a.localhost:8080/api/v1/auth/callback/dex?code=c&state=s"), idp
    )


def test_another_port_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://localhost:5556/dex/auth?state=s"))

    assert not sign_in.within_idp(httpx.URL("http://localhost:8001/dex/anything"), idp)


def test_another_host_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert not sign_in.within_idp(httpx.URL("http://b.localhost:8080/dex/auth/local"), idp)
