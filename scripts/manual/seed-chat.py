#!/usr/bin/env -S uv run --with httpx --no-project --quiet python
"""Fill a channel with history, then keep talking into it.

Built for watching the UI while it runs: it posts a backlog first, so the
message list is long enough to scroll, then drips one message every few seconds
so new messages keep arriving in a browser you already have open. Messaging
publishes `message_received` after every REST write, so the drip shows up live
without a reload.

    scripts/manual/seed-chat.py                       # 60 backlog, one every 3s
    scripts/manual/seed-chat.py --backlog 120         # more history to page back
    scripts/manual/seed-chat.py --drip 1              # faster
    scripts/manual/seed-chat.py --backlog 0 --drip 5  # drip into what is there
    scripts/manual/seed-chat.py --channel standup     # somewhere else

Ctrl+C stops it. Run it in the background and watch http://localhost:5173.

It signs in the way a browser does, by handing off to the Auth service's own
`scripts/sign-in.py`, so there is no second copy of the PKCE dance here. Access
tokens last 15 minutes and this is meant to run longer than that, so a 401 is
caught and the sign-in repeated.
"""

# T20 is not waived here: living under `scripts/` earns ruff.toml's exemption,
# because stdout is a developer CLI's interface. The two below are this file's
# own — the one subprocess call runs a known script from the checkout, and the
# random choice picks chat filler, not anything that needs to be unguessable.
# ruff: noqa: S603, S311

from __future__ import annotations

import argparse
import itertools
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

# scripts/manual/seed-chat.py — the checkout is two directories up.
DEFAULT_REPO = Path(__file__).resolve().parents[2]
DEFAULT_EMAIL = "ada@collabhub.dev"
DEFAULT_MESSAGING = "http://localhost:8002"

SIGN_IN = Path("src/services/auth/scripts/sign-in.py")

# Enough variety that the list looks like a conversation rather than a loop.
LINES = [
    "morning all",
    "just pushed the branch, have a look when you get a minute",
    "did the nightly run go green?",
    "it did, but it took 40 minutes again",
    "that is the container startup, not the tests",
    "worth caching the layer?",
    "probably. I will raise it after standup",
    "anyone else seeing the flaky one in the auth suite?",
    "yes, about one run in ten",
    "I think it is the clock, the token expires mid-test",
    "good catch",
    "lunch?",
    "give me ten minutes",
    "the deploy is out on staging",
    "looks fine from here",
    "I am going to call that done",
    "nice one",
    "one more thing before I forget",
    "the docs still say MinIO in two places",
    "I will fix those",
    "thanks",
    "has anyone looked at the search backlog?",
    "not yet, it is behind the indexing work",
    "fair enough",
    "see you tomorrow",
]


def token_for(repo: Path, email: str) -> str:
    """An access token, obtained the way the browser gets one."""
    script = repo / SIGN_IN
    if not script.exists():
        raise SystemExit(f"cannot find {script} — pass --repo pointing at the checkout")

    done = subprocess.run(
        [str(script), email, "--access-token"],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise SystemExit(
            f"sign-in failed for {email}. Is the stack up (docker compose up -d)?\n"
            f"{done.stderr.strip()}"
        )
    return done.stdout.strip()


class Chat:
    """A signed-in caller that re-authenticates when its token expires."""

    def __init__(self, repo: Path, email: str, base_url: str) -> None:
        self._repo = repo
        self._email = email
        self._client = httpx.Client(base_url=base_url, timeout=15.0)
        self._token = token_for(repo, email)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        response = self._client.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code == httpx.codes.UNAUTHORIZED:
            # 15-minute access tokens; this script is meant to outlive one.
            print("… token expired, signing in again", file=sys.stderr)
            self._token = token_for(self._repo, self._email)
            response = self._client.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise SystemExit(f"{method} {url} answered {response.status_code}: {response.text}")
        return response

    def channel_named(self, name: str) -> str | None:
        """The id of a channel with this name, walking the cursor to be sure."""
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            page = self.request("GET", "/api/v1/channels", params=params).json()
            for channel in page["items"]:
                if channel["name"] == name:
                    return channel["id"]
            cursor = page.get("nextCursor")
            if not cursor:
                return None

    def create_channel(self, name: str) -> str:
        created = self.request(
            "POST",
            "/api/v1/channels",
            json={"name": name, "kind": "public", "topic": "Seeded for local poking"},
        ).json()
        return created["id"]

    def post(self, channel_id: str, body: str) -> None:
        self.request("POST", f"/api/v1/channels/{channel_id}/messages", json={"body": body})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channel", default="scrollback", help="channel name (created if absent)")
    parser.add_argument("--backlog", type=int, default=60, help="messages to post up front")
    parser.add_argument("--drip", type=float, default=3.0, help="seconds between messages after")
    parser.add_argument("--drip-count", type=int, default=0, help="0 means keep going until Ctrl+C")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument(
        "--repo", type=Path, default=DEFAULT_REPO, help="the checkout to sign in with"
    )
    parser.add_argument("--messaging-url", default=DEFAULT_MESSAGING)
    args = parser.parse_args()

    chat = Chat(args.repo, args.email, args.messaging_url)

    channel_id = chat.channel_named(args.channel)
    if channel_id is None:
        channel_id = chat.create_channel(args.channel)
        print(f"created #{args.channel}")
    else:
        print(f"found #{args.channel}")

    # Numbered, so it is obvious at a glance which end of the history you are at
    # and whether anything is missing in between.
    counter = itertools.count(1)

    for _ in range(args.backlog):
        n = next(counter)
        chat.post(channel_id, f"[{n:03d}] {random.choice(LINES)}")
        if n % 10 == 0:
            print(f"  … {n} posted")
    if args.backlog:
        print(f"posted {args.backlog} to #{args.channel}")

    print(f"open http://localhost:5173 and go to #{args.channel}")
    if args.drip <= 0:
        return

    print(f"dripping one message every {args.drip}s — Ctrl+C to stop")
    posted = 0
    try:
        while args.drip_count == 0 or posted < args.drip_count:
            time.sleep(args.drip)
            n = next(counter)
            chat.post(channel_id, f"[{n:03d}] {random.choice(LINES)}")
            posted += 1
            print(f"  → [{n:03d}]")
    except KeyboardInterrupt:
        print(f"\nstopped after {posted} dripped")


if __name__ == "__main__":
    main()
