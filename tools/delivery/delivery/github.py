"""The GitHub backend, through the `gh` CLI.

`gh` brings its own authentication — the developer's login locally, `GH_TOKEN`
in GitHub Actions — so there is no token handling here. Every call names the
repo as `HOST/OWNER/REPO`, which is all GitHub Enterprise needs.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from delivery.errors import BackendError
from delivery.model import Issue

#: Runs a command with optional stdin and returns its stdout; raises
#: `BackendError` when the command fails.
Runner = Callable[[list[str], str | None], str]

#: GitHub refuses an issue body longer than this many characters.
BODY_LIMIT = 65536
KEY = re.compile(r"gh-([0-9]+)")
CAN_WRITE = frozenset({"ADMIN", "MAINTAIN", "WRITE"})
ISSUE_FIELDS = "number,title,body,url,labels"


def run_gh(args: list[str], input: str | None = None) -> str:  # noqa: A002
    try:
        done = subprocess.run(  # noqa: S603 — fixed program, argument list.
            args, input=input, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as e:
        raise BackendError("the GitHub backend needs the gh CLI on PATH") from e
    if done.returncode != 0:
        raise BackendError(done.stderr.strip() or f"{' '.join(args[:3])} failed")
    return done.stdout


class GitHubBackend:
    """Issues on a GitHub repo. Keys are `gh-N`."""

    def __init__(self, url: str, run: Runner | None = None) -> None:
        parts = urlsplit(url)
        self.url = url
        self.repo = f"{parts.netloc}{parts.path}"
        self.run = run or run_gh

    def check(self) -> None:
        found = json.loads(
            self._gh(["repo", "view", self.repo, "--json", "hasIssuesEnabled,viewerPermission"])
        )
        if not found.get("hasIssuesEnabled"):
            raise BackendError(f"{self.url} has issues turned off")
        if found.get("viewerPermission") not in CAN_WRITE:
            raise BackendError(
                f"you need write access to {self.url} to create issues and labels"
                f" — you have {found.get('viewerPermission') or 'none'}"
            )

    def create(self, title: str, body: str, labels: Sequence[str] = ()) -> Issue:
        if len(body) > BODY_LIMIT:
            raise BackendError(
                f"the body is {len(body)} characters; GitHub takes at most {BODY_LIMIT}"
            )
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        created = self._gh(args, body).strip()
        number = created.rsplit("/", 1)[-1]
        if not number.isdigit():
            raise BackendError(f"gh issue create printed no issue URL: {created!r}")
        # Read back, rather than echo the draft: the issue as GitHub now holds it.
        return self.get(f"gh-{number}")

    def get(self, key: str) -> Issue:
        number = self._number(key)
        found = json.loads(
            self._gh(["issue", "view", str(number), "--repo", self.repo, "--json", ISSUE_FIELDS])
        )
        return Issue(
            key=f"gh-{found['number']}",
            number=found["number"],
            title=found["title"],
            body=found["body"],
            url=found["url"],
            labels=[label["name"] for label in found["labels"]],
        )

    def edit(self, key: str, title: str, body: str) -> Issue:
        number = self._number(key)
        args = ["issue", "edit", str(number), "--repo", self.repo, "--title", title]
        self._gh([*args, "--body-file", "-"], body)
        return self.get(key)

    def ensure_label(self, name: str, description: str, color: str) -> None:
        args = ["label", "create", name, "--repo", self.repo, "--description", description]
        self._gh([*args, "--color", color, "--force"])

    def _gh(self, args: list[str], stdin: str | None = None) -> str:
        return self.run(["gh", *args], stdin)

    @staticmethod
    def _number(key: str) -> int:
        match = KEY.fullmatch(key)
        if match is None:
            raise BackendError(f"'{key}' is not a GitHub issue key — they look like gh-N")
        return int(match.group(1))
