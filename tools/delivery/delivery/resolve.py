"""Which backend a run uses: arguments, then the environment, then `local`."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from delivery.errors import ConfigError

LOCAL = "local"
GITHUB = "github"
KNOWN = (LOCAL, GITHUB)

#: Hosts that say which backend they are. Any other host needs `--backend`.
INFERRED = {"github.com": GITHUB, "dev.azure.com": "azure-devops"}


@dataclass(frozen=True)
class BackendConfig:
    kind: str
    url: str | None


def resolve(backend: str | None, url: str | None, env: Mapping[str, str]) -> BackendConfig:
    """The backend and URL to use.

    Taken as a pair from one source: the arguments if either is given, else
    `DELIVERY_BACKEND` and `DELIVERY_URL`. Mixing them would let a URL left in
    the shell turn an explicit `--backend local` into an error.
    """
    if backend is None and url is None:
        backend = env.get("DELIVERY_BACKEND") or None
        url = env.get("DELIVERY_URL") or None
    if url is not None:
        url = repo_url(url)
    if backend is None:
        backend = LOCAL if url is None else infer(url)
    if backend not in KNOWN:
        raise ConfigError(f"unknown backend '{backend}' — expected one of: {', '.join(KNOWN)}")
    if backend == LOCAL and url is not None:
        raise ConfigError(f"the local backend takes no URL, but was given {url}")
    if backend != LOCAL and url is None:
        raise ConfigError(f"the {backend} backend needs the repo's URL (--url or DELIVERY_URL)")
    if backend == GITHUB and urlsplit(url).path.count("/") != 2:
        raise ConfigError(f"{url} is not a GitHub repo's URL, like https://github.com/owner/repo")
    return BackendConfig(kind=backend, url=url)


def repo_url(url: str) -> str:
    """The repo's web URL, tidied: `https://host/owner/repo`, no `.git`, no trailing slash."""
    parts = urlsplit(url)
    path = parts.path.strip("/").removesuffix(".git")
    if parts.scheme not in ("https", "http") or not parts.netloc or not path:
        raise ConfigError(f"{url} is not a repo's web URL, like https://github.com/owner/repo")
    return f"{parts.scheme}://{parts.netloc}/{path}"


def infer(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    kind = INFERRED.get(host)
    if kind is None:
        raise ConfigError(f"can't tell which backend {host} is — say which with --backend")
    if kind not in KNOWN:
        raise ConfigError(f"{host} is {kind}, which is not supported yet")
    return kind
