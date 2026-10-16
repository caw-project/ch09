"""The GitHub backend: what it asks `gh` to do, and what it makes of the answer."""

from __future__ import annotations

import json

import pytest
from delivery.errors import BackendError
from delivery.github import BODY_LIMIT, GitHubBackend
from delivery.model import Issue

REPO_URL = "https://github.com/sixeyed/claude-at-work-project"
REPO = "github.com/sixeyed/claude-at-work-project"


@pytest.fixture
def backend(gh):
    return GitHubBackend(REPO_URL, run=gh)


# --- check -----------------------------------------------------------------


def test_check_asks_for_the_repo_by_host_owner_and_name(backend, gh):
    backend.check()

    args, _ = gh.call("repo view")
    assert args == ["gh", "repo", "view", REPO, "--json", "hasIssuesEnabled,viewerPermission"]


@pytest.mark.parametrize("permission", ["ADMIN", "MAINTAIN", "WRITE"])
def test_check_passes_for_a_viewer_who_can_write(gh, permission):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": True, "viewerPermission": permission})

    GitHubBackend(REPO_URL, run=gh).check()


@pytest.mark.parametrize("permission", ["TRIAGE", "READ", ""])
def test_check_fails_for_a_viewer_who_cannot_create_labels(gh, permission):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": True, "viewerPermission": permission})

    with pytest.raises(BackendError, match="write"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_check_fails_when_issues_are_disabled(gh):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": False, "viewerPermission": "ADMIN"})

    with pytest.raises(BackendError, match="issues"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_a_failing_gh_surfaces_as_a_backend_error(gh):
    gh.answers["repo view"] = BackendError("gh: Could not resolve to a Repository")

    with pytest.raises(BackendError, match="Could not resolve"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_an_enterprise_host_is_passed_through(gh):
    GitHubBackend("https://git.example.com/team/project", run=gh).check()

    args, _ = gh.call("repo view")
    assert args[3] == "git.example.com/team/project"


# --- create ----------------------------------------------------------------


def test_create_sends_the_body_on_stdin_with_title_and_labels(backend, gh):
    backend.create("Pin a message", "## Summary\n\nPins.\n", labels=["delivery"])

    args, stdin = gh.call("issue create")
    assert args == [
        "gh",
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        "Pin a message",
        "--body-file",
        "-",
        "--label",
        "delivery",
    ]
    assert stdin == "## Summary\n\nPins.\n"


def test_create_returns_the_issue_as_github_holds_it(backend, gh):
    """Read back by the number in the URL `gh issue create` prints — not the
    draft echoed back, which would prove nothing."""
    issue = backend.create("Pin a message", "## Summary\n\nPins.\n")

    args, _ = gh.call("issue view")
    assert args[:4] == ["gh", "issue", "view", "5"]
    assert issue == Issue(
        key="gh-5",
        number=5,
        title="Pin a message",
        body="## Summary\n\nPins.\n",
        url=f"{REPO_URL}/issues/5",
        labels=["delivery"],
    )


def test_a_body_over_githubs_limit_is_refused_before_gh_runs(backend, gh):
    with pytest.raises(BackendError, match=str(BODY_LIMIT)):
        backend.create("Too long", "x" * (BODY_LIMIT + 1))

    assert gh.calls == []


def test_a_body_at_githubs_limit_is_sent(backend, gh):
    backend.create("Just fits", "x" * BODY_LIMIT)

    gh.call("issue create")


# --- get and edit ----------------------------------------------------------


def test_get_asks_for_every_field_the_model_holds(backend, gh):
    backend.get("gh-5")

    args, _ = gh.call("issue view")
    assert args == [
        "gh",
        "issue",
        "view",
        "5",
        "--repo",
        REPO,
        "--json",
        "number,title,body,url,labels",
    ]


@pytest.mark.parametrize("key", ["issue-5", "5", "gh-", "gh-five"])
def test_a_key_that_is_not_a_github_key_is_refused_before_gh_runs(backend, gh, key):
    with pytest.raises(BackendError, match="gh-N"):
        backend.get(key)

    assert gh.calls == []


def test_edit_sends_the_new_title_and_body_then_reads_back(backend, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(title="Pin messages", body="## Summary\n\nSeveral.\n")

    issue = backend.edit("gh-5", "Pin messages", "## Summary\n\nSeveral.\n")

    args, stdin = gh.call("issue edit")
    assert args == [
        "gh",
        "issue",
        "edit",
        "5",
        "--repo",
        REPO,
        "--title",
        "Pin messages",
        "--body-file",
        "-",
    ]
    assert stdin == "## Summary\n\nSeveral.\n"
    assert issue.title == "Pin messages"


# --- ensure_label ----------------------------------------------------------


def test_ensure_label_creates_or_updates_it(backend, gh):
    """`--force` makes it idempotent: an existing label is updated, not an error."""
    backend.ensure_label("delivery", "Written for scripts/deliver.sh", "0e8a16")

    args, _ = gh.call("label create")
    assert args == [
        "gh",
        "label",
        "create",
        "delivery",
        "--repo",
        REPO,
        "--description",
        "Written for scripts/deliver.sh",
        "--color",
        "0e8a16",
        "--force",
    ]
