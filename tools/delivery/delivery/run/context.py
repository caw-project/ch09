"""The context block: every agent's prompt. `.claude/delivery/agent-context.md` documents it
line by line, so a change to one is a change to the other."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from delivery.run.keys import Paths
from delivery.run.machine import (
    SENDERS,
    earlier_pair,
    has_writer,
    is_final_round,
    is_rework,
    pair_of,
    review_path,
    role_of,
    sendback_path,
)
from delivery.run.rules import turns_for
from delivery.run.settings import Settings
from delivery.run.state import State

#: The most changed paths one `Changed since the send-back` line lists.
CHANGED_LIMIT = 40


def context_block(
    stage: str,
    state: State,
    settings: Settings,
    paths: Paths,
    *,
    worktree: Path,
    branch: str,
    preview: str = "",
    has_reviews: bool = False,
    has_answers: bool = False,
    changed: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """`changed` is, for each sender whose send-back snapshot exists, the paths written
    since it sent work back."""
    pair = pair_of(stage)
    turns = turns_for(stage, state, settings)
    lines = [
        f"Issue: {paths.key}",
        f"Issue file: {paths.issue_copy}",
        f"Plan dir: {paths.plan_dir}/",
        f"Plan: {paths.plan}",
    ]
    # From the test pair on: the failing tests, as the test-writer reports them.
    if pair in ("test", "code", "acceptance"):
        lines.append(f"Red report: {paths.red_report}")
    # From the code pair on: what was built, and what ran, as the code-writer reports it.
    if pair in ("code", "acceptance"):
        lines.append(f"Green report: {paths.green_report}")
    lines.append(f"Worktree: {worktree} (branch {branch})")
    lines.append(f"Stage: {stage}, round {state.rounds[pair]} of {state.final[pair]}")
    lines.append(pass_line(stage, state, turns))
    if role_of(stage) == "writer" and state.review:
        lines.append(f"Review to address: {state.review}")
    if role_of(stage) == "reviewer":
        lines += reviewer_lines(stage, state, paths, preview)
    # Every review so far, approvals included — a final reviewer's approval can leave
    # minor findings for the stages after it to pick up.
    if has_reviews:
        lines.append(f"Earlier reviews: {paths.reviews}/")
    if has_answers:
        lines.append(f"Human answers: {paths.answers}")
    if earlier_pair(stage):
        lines.append(f"Send-back file, if you send work back: {sendback_path(stage, state, paths)}")
    lines += sendback_lines(state, paths, changed or {})
    return "\n".join(lines) + "\n"


def pass_line(stage: str, state: State, turns: int) -> str:
    if is_final_round(stage, state):
        return f"Final round: yes — {turns} turns. Follow your *Final round* rules."
    if is_rework(stage, state):
        return f"Rework pass: yes — {turns} turns. Follow *A rework pass*."
    return f"Turns: {turns}"


def reviewer_lines(stage: str, state: State, paths: Paths, preview: str) -> list[str]:
    if has_writer(stage):
        return [f"Write your review to: {review_path(stage, state, paths)}"]
    return [f"Proof: {paths.proof}", f"Evidence: {paths.evidence}/", f"Preview: {preview}"]


def sendback_lines(state: State, paths: Paths, changed: Mapping[str, Sequence[str]]) -> list[str]:
    """Every stage the flow passes through on its way back to the stage that sent work back
    — the work each takes over has changed since it last saw it, and the list says where,
    so the pass can keep to that."""
    lines = []
    for sender in SENDERS:
        file = state.open_sendbacks.get(sender)
        if not file:
            continue
        if state.review != file:
            lines.append(f"After a send-back by {sender}: {file}")
        since = [p for p in changed.get(sender, ()) if not p.startswith(f"{paths.reviews}/")]
        if since:
            lines.append(
                f"Changed since the send-back by {sender}: {' '.join(since[:CHANGED_LIMIT])}"
            )
    return lines
