"""What a run writes for people — `history.log`'s stats and `needs-human.md` — and how it
sees what a stage wrote. The formats are the bash `deliver.sh`'s, so runs stay comparable."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

from delivery.run.machine import HumanStop
from delivery.run.rules import ran_with_model


def jq_round(value: float, places: int) -> str:
    """`. * 10^p | round / 10^p` as jq printed it: half away from zero, no trailing `.0`."""
    scale = 10**places
    rounded = math.floor(abs(value) * scale + 0.5) / scale * (1 if value >= 0 else -1)
    return str(int(rounded)) if rounded.is_integer() else repr(rounded)


def step_stats(transcripts: Iterable[Path]) -> str:
    """A step's minutes, turns and cost, over every run it took — a retry and a resume each
    leave a transcript of their own beside the result."""
    runs = []
    try:
        for path in transcripts:
            text = path.read_text().strip()
            # An empty transcript is a crash that printed nothing: no run to count.
            runs += [json.loads(line) for line in text.splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return "no stats"
    minutes = sum(r.get("duration_ms") or 0 for r in runs) / 60000
    turns = sum(r.get("num_turns") or 0 for r in runs)
    cost = sum(r.get("total_cost_usd") or 0 for r in runs)
    return f"{jq_round(minutes, 1)}m {turns} turns ${jq_round(cost, 2)}"


def ran_with(model: str, effort: str, agent_file: Path) -> str:
    """What history.log says a stage ran with: the model passed, or the one its agent names,
    and the effort."""
    return f"{ran_with_model(model, agent_file)} · {effort or 'default'}"


def needs_human_entry(key: str, stop: HumanStop, *, first: bool) -> str:
    """A stop for `needs-human.md`, with a space under each question to answer."""
    heading = f"# {key} — questions for a human\n" if first else ""
    entry = f"\n## {stop.stage} stopped, round {stop.round}\n\n{stop.summary}\n\n"
    answers = "".join(f"{i}. {q}\n\n   **Answer:**\n\n" for i, q in enumerate(stop.questions, 1))
    return heading + entry + answers


# --- what a stage wrote ----------------------------------------------------------


def snapshot(worktree: Path) -> dict[str, str]:
    """Every uncommitted path outside build/, tracked or not, with a hash of what is in it
    now. Two snapshots differ exactly where a stage wrote."""
    out = subprocess.run(  # noqa: S603 — fixed program, argument list.
        ["git", "-C", str(worktree), "status", "--porcelain", "-z", "--untracked-files=all"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout.decode()
    entries = out.split("\0")
    found: dict[str, str] = {}
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        # A rename's entry is followed by the path it came from, which no longer exists.
        if "R" in code or "C" in code:
            i += 1
        if path.startswith("build/"):
            continue
        found[path] = content_hash(worktree / path)
    return found


def content_hash(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha1(str(path.readlink()).encode()).hexdigest()  # noqa: S324 — not security.
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()  # noqa: S324 — change detection only.
    except OSError:
        return "deleted"


def touched_between(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """The paths whose content differs between two snapshots."""
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def save_snapshot(path: Path, snap: Mapping[str, str]) -> None:
    path.write_text(json.dumps(dict(snap), indent=0, sort_keys=True))


def load_snapshot(path: Path) -> dict[str, str] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
