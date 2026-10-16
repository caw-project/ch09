"""The context block — every agent's prompt, and `.claude/delivery/agent-context.md`'s subject.

Line for line the bash `context_block`, but for the issue: `Issue: <key>` with no `#`, and a
`Plan dir:` line, so no agent builds a path from the key.
"""

from __future__ import annotations

from pathlib import Path

from delivery.run.context import context_block
from delivery.run.keys import paths_for
from delivery.run.settings import Settings
from delivery.run.state import State

WORKTREE = Path("/work/caw-gh-3")
BRANCH = "feature/gh-3"
PATHS = paths_for("gh-3")
REVIEWS = "docs/plans/gh-3/reviews"


def block(stage, state=None, **kw) -> list[str]:
    return context_block(
        stage,
        state or State.fresh(max_rounds=3),
        Settings.from_env({}),
        PATHS,
        worktree=WORKTREE,
        branch=BRANCH,
        **kw,
    ).splitlines()


def test_a_first_pass_is_told_the_issue_by_key_and_where_its_plan_lives():
    assert block("plan-writer") == [
        "Issue: gh-3",
        "Issue file: docs/plans/gh-3/00-issue.md",
        "Plan dir: docs/plans/gh-3/",
        "Plan: docs/plans/gh-3/01-implementation-plan.md",
        "Worktree: /work/caw-gh-3 (branch feature/gh-3)",
        "Stage: plan-writer, round 1 of 3",
        "Turns: 150",
    ]


def test_a_reviewer_is_told_where_its_review_goes():
    assert "Write your review to: docs/plans/gh-3/reviews/plan-reviewer-1.md" in block(
        "plan-reviewer"
    )


def test_the_reports_are_named_from_the_pair_that_has_them():
    test_pair = block("test-writer")
    code_pair = block("code-reviewer")

    assert "Red report: docs/plans/gh-3/02-red-tests.md" in test_pair
    assert not any(line.startswith("Green report:") for line in test_pair)
    assert "Green report: docs/plans/gh-3/03-green-report.md" in code_pair


def test_the_acceptance_reviewer_is_told_its_proof_evidence_and_preview():
    lines = block(
        "acceptance-reviewer",
        preview="up at https://x.example — log: build/acceptance/preview-up.log",
    )

    assert lines[-4:] == [
        "Proof: docs/plans/gh-3/04-proof.md",
        "Evidence: build/acceptance/",
        "Preview: up at https://x.example — log: build/acceptance/preview-up.log",
        f"Send-back file, if you send work back: {REVIEWS}/acceptance-reviewer-sendback-2.md",
    ]
    assert not any(line.startswith("Write your review to:") for line in lines)


def test_a_rework_pass_says_so_with_its_turns():
    state = State.fresh(max_rounds=3)
    state.rounds["plan"] = 2
    state.review = f"{REVIEWS}/plan-reviewer-1.md"

    lines = block("plan-writer", state)

    assert "Rework pass: yes — 100 turns. Follow *A rework pass*." in lines
    assert f"Review to address: {REVIEWS}/plan-reviewer-1.md" in lines


def test_a_final_round_says_so_with_its_turns():
    state = State.fresh(max_rounds=3)
    state.rounds["test"] = 3

    assert "Final round: yes — 60 turns. Follow your *Final round* rules." in block(
        "test-reviewer", state
    )


def test_earlier_reviews_and_human_answers_appear_once_there_are_some():
    lines = block("plan-writer", has_reviews=True, has_answers=True)

    assert "Earlier reviews: docs/plans/gh-3/reviews/" in lines
    assert "Human answers: docs/plans/gh-3/needs-human.md" in lines


def test_every_stage_on_the_way_back_is_told_of_an_open_send_back_and_what_changed():
    state = State.fresh(max_rounds=3)
    state.open_sendbacks["test-reviewer"] = f"{REVIEWS}/test-reviewer-sendback-2.md"
    changed = {
        "test-reviewer": [
            f"{REVIEWS}/plan-reviewer-2.md",
            "docs/plans/gh-3/01-implementation-plan.md",
        ]
    }

    lines = block("plan-reviewer", state, changed=changed)

    assert f"After a send-back by test-reviewer: {REVIEWS}/test-reviewer-sendback-2.md" in lines
    # Reviews left out: the pass looks where the work changed.
    assert (
        "Changed since the send-back by test-reviewer: docs/plans/gh-3/01-implementation-plan.md"
        in lines
    )


def test_the_writer_answering_a_send_back_is_not_told_it_twice():
    state = State.fresh(max_rounds=3)
    file = f"{REVIEWS}/test-reviewer-sendback-2.md"
    state.open_sendbacks["test-reviewer"] = file
    state.review = file

    lines = block("plan-writer", state)

    assert f"Review to address: {file}" in lines
    assert not any(line.startswith("After a send-back") for line in lines)


def test_at_most_forty_changed_paths_are_listed():
    state = State.fresh(max_rounds=3)
    state.open_sendbacks["code-writer"] = f"{REVIEWS}/code-writer-sendback-2.md"
    changed = {"code-writer": [f"src/f{i:02d}.py" for i in range(50)]}

    line = next(
        line for line in block("test-writer", state, changed=changed) if line.startswith("Changed")
    )

    assert line.split(": ", 1)[1].split() == [f"src/f{i:02d}.py" for i in range(40)]
