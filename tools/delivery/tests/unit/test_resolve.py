"""Which backend a run uses: arguments, then environment, then `local`."""

from __future__ import annotations

import pytest
from delivery.errors import ConfigError
from delivery.resolve import BackendConfig, resolve

URL = "https://github.com/sixeyed/claude-at-work-project"


def test_nothing_given_is_local():
    assert resolve(backend=None, url=None, env={}) == BackendConfig(kind="local", url=None)


def test_the_environment_is_used_when_no_argument_is_given():
    env = {"DELIVERY_BACKEND": "github", "DELIVERY_URL": URL}

    assert resolve(backend=None, url=None, env=env) == BackendConfig(kind="github", url=URL)


def test_arguments_win_over_the_environment():
    env = {"DELIVERY_BACKEND": "github", "DELIVERY_URL": URL}

    assert resolve(backend="local", url=None, env=env) == BackendConfig(kind="local", url=None)


def test_arguments_are_taken_as_a_pair_and_never_mixed_with_the_environment():
    """`--backend local` with DELIVERY_URL set in the shell is local, not a
    "local takes no URL" error — the URL came from somewhere else."""
    env = {"DELIVERY_URL": URL}

    assert resolve(backend="local", url=None, env=env) == BackendConfig(kind="local", url=None)


def test_a_github_com_url_alone_infers_github():
    assert resolve(backend=None, url=URL, env={}) == BackendConfig(kind="github", url=URL)


def test_a_github_com_url_in_the_environment_alone_infers_github():
    assert resolve(backend=None, url=None, env={"DELIVERY_URL": URL}) == BackendConfig(
        kind="github", url=URL
    )


def test_an_explicit_backend_takes_any_host():
    """GitHub Enterprise: the host can't say it's GitHub, so the user does."""
    url = "https://git.example.com/team/project"

    assert resolve(backend="github", url=url, env={}) == BackendConfig(kind="github", url=url)


def test_a_url_on_another_host_without_a_backend_is_refused():
    with pytest.raises(ConfigError, match="--backend"):
        resolve(backend=None, url="https://forge.sixeyed/manning/project", env={})


def test_an_azure_devops_url_is_recognised_and_refused_as_not_supported_yet():
    with pytest.raises(ConfigError, match="not supported yet"):
        resolve(backend=None, url="https://dev.azure.com/org/project/_git/repo", env={})


def test_local_with_a_url_is_refused():
    with pytest.raises(ConfigError, match="local"):
        resolve(backend="local", url=URL, env={})


def test_github_without_a_url_is_refused():
    with pytest.raises(ConfigError, match="URL"):
        resolve(backend="github", url=None, env={})


def test_an_unknown_backend_is_refused_naming_the_known_ones():
    with pytest.raises(ConfigError, match="local, github"):
        resolve(backend="jira", url=None, env={})


@pytest.mark.parametrize(
    "url",
    [
        "github.com/sixeyed/claude-at-work-project",  # no scheme
        "https://github.com/sixeyed",  # no repo
        "https://github.com/sixeyed/claude-at-work-project/issues",  # not a repo URL
        "ftp://github.com/sixeyed/claude-at-work-project",
    ],
)
def test_a_url_that_is_not_a_repo_web_url_is_refused(url):
    with pytest.raises(ConfigError, match="repo"):
        resolve(backend="github", url=url, env={})


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/sixeyed/claude-at-work-project/",
        "https://github.com/sixeyed/claude-at-work-project.git",
    ],
)
def test_a_trailing_slash_or_dot_git_is_tidied_away(url):
    assert resolve(backend=None, url=url, env={}).url == URL
