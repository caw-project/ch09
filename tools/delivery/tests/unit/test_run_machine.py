"""The state machine: what each verdict does to the run — the bash `deliver.sh`'s `case` block."""

from __future__ import annotations

import copy
import re

import pytest
from delivery.errors import RunError
from delivery.run.keys import paths_for
from delivery.run.machine import STAGES, advance, missing_outputs, next_stage
from delivery.run.settings import Settings
from delivery.run.state import State

PATHS = paths_for("issue-999")
REVIEWS = "docs/plans/issue-999/reviews"


def result(status: str, summary: str = "fake", questions=("what?",)) -> dict:
    return {"status": status, "summary": summary, "files": [], "questions": list(questions)}


def step(state, stage, status, *, written=(), proof_rewritten=True, settings=None, **kw):
    """Runs one verdict through the machine, with only `written` on disk."""
    state.stage = stage
    return advance(
        state,
        stage,
        result(status, **kw),
        PATHS,
        settings or Settings.from_env({}),
        exists=lambda path: path in written,
        proof_rewritten=proof_rewritten,
    )


@pytest.fixture
def state():
    return State.fresh(max_rounds=3)


def test_the_stages_run_in_order_then_done():
    assert [next_stage(s) for s in STAGES] == [*STAGES[1:], "done"]


# --- writers ---------------------------------------------------------------


def test_a_writer_that_is_done_hands_on_to_its_reviewer(state):
    state.review = f"{REVIEWS}/plan-reviewer-1.md"

    moved = step(state, "plan-writer", "done", written={PATHS.plan})

    assert (state.stage, state.review, moved.stop) == ("plan-reviewer", "", False)


def test_a_writer_done_without_its_output_is_an_error(state):
    with pytest.raises(
        RunError, match=re.escape("said done but wrote no docs/plans/issue-999/02-red-tests.md")
    ):
        step(state, "test-writer", "done")


# --- reviewers -------------------------------------------------------------


def test_an_approval_needs_its_review_written(state):
    with pytest.raises(RunError, match=f"approved but wrote no {REVIEWS}/plan-reviewer-1.md"):
        step(state, "plan-reviewer", "approved")


def test_an_approval_moves_on_to_the_next_writer(state):
    step(state, "plan-reviewer", "approved", written={f"{REVIEWS}/plan-reviewer-1.md"})

    assert state.stage == "test-writer"


def test_coming_forward_a_writer_gets_the_review_its_reviewer_left_pending(state):
    state.pending["test"] = f"{REVIEWS}/test-reviewer-1.md"

    step(state, "plan-reviewer", "approved", written={f"{REVIEWS}/plan-reviewer-1.md"})

    assert (state.stage, state.review, state.pending["test"]) == (
        "test-writer",
        f"{REVIEWS}/test-reviewer-1.md",
        "",
    )


def test_changes_requested_go_back_to_the_writer_a_round_on(state):
    review = f"{REVIEWS}/plan-reviewer-1.md"

    moved = step(state, "plan-reviewer", "changes_requested", written={review})

    assert (state.stage, state.review, state.rounds["plan"], moved.stop) == (
        "plan-writer",
        review,
        2,
        False,
    )


def test_changes_requested_need_the_review_written(state):
    with pytest.raises(RunError, match="asked for changes but wrote no"):
        step(state, "plan-reviewer", "changes_requested")


def test_changes_requested_in_the_final_round_stop_for_a_human(state):
    state.rounds["plan"] = 3
    review = f"{REVIEWS}/plan-reviewer-3.md"

    moved = step(state, "plan-reviewer", "changes_requested", written={review})

    assert moved.stop
    assert moved.human.stage == "plan-reviewer"
    assert moved.human.round == 3
    assert "final round (3 of 3)" in moved.human.summary
    assert (state.stage, state.rounds["plan"]) == ("plan-writer", 4)


def test_the_acceptance_reviewer_may_not_ask_for_changes(state):
    with pytest.raises(RunError, match="has no writer to take changes"):
        step(state, "acceptance-reviewer", "changes_requested")


def test_the_acceptance_reviewer_approves_only_with_its_proof(state):
    with pytest.raises(
        RunError, match=re.escape("approved but wrote no docs/plans/issue-999/04-proof.md")
    ):
        step(state, "acceptance-reviewer", "approved")


def test_the_acceptance_reviewer_approves_only_with_a_proof_of_its_own(state):
    with pytest.raises(RunError, match="did not rewrite"):
        step(state, "acceptance-reviewer", "approved", written={PATHS.proof}, proof_rewritten=False)


def test_the_last_approval_is_done(state):
    step(state, "acceptance-reviewer", "approved", written={PATHS.proof})

    assert state.stage == "done"


# --- send-backs ------------------------------------------------------------


def test_a_writer_sends_back_to_the_pair_before(state):
    file = f"{REVIEWS}/code-writer-sendback-2.md"

    moved = step(state, "code-writer", "send_back", written={file})

    assert moved.snapshot
    assert not moved.stop
    assert state.stage == "test-writer"
    assert state.review == file
    assert state.rounds == {"plan": 1, "test": 2, "code": 1, "acceptance": 1}
    assert state.final["test"] == 3
    assert state.sendbacks["test"] == 1
    assert state.open_sendbacks == {"code-writer": file}


def test_a_send_back_without_its_file_is_an_error(state):
    with pytest.raises(RunError, match="sent work back but wrote no"):
        step(state, "code-writer", "send_back")


def test_the_plan_pair_cannot_send_back(state):
    with pytest.raises(RunError, match="no pair before it"):
        step(state, "plan-reviewer", "send_back")


def test_a_reviewer_that_sends_back_leaves_its_review_for_its_writer(state):
    file = f"{REVIEWS}/test-reviewer-sendback-2.md"
    review = f"{REVIEWS}/test-reviewer-1.md"

    step(state, "test-reviewer", "send_back", written={file, review})

    assert state.pending["test"] == review
    assert state.rounds == {"plan": 2, "test": 2, "code": 1, "acceptance": 1}
    assert state.stage == "plan-writer"


def test_a_reviewer_that_sends_back_needs_its_review_too(state):
    with pytest.raises(RunError, match=f"wrote no {REVIEWS}/test-reviewer-1.md"):
        step(
            state, "test-reviewer", "send_back", written={f"{REVIEWS}/test-reviewer-sendback-2.md"}
        )


def test_a_send_back_never_lands_in_a_final_round(state):
    state.rounds["plan"] = 3
    file = f"{REVIEWS}/test-writer-sendback-4.md"

    step(state, "test-writer", "send_back", written={file})

    assert (state.rounds["plan"], state.final["plan"]) == (4, 5)


def test_the_acceptance_reviewer_moves_its_own_round_on_when_it_sends_back(state):
    file = f"{REVIEWS}/acceptance-reviewer-sendback-2.md"

    step(state, "acceptance-reviewer", "send_back", written={file})

    assert state.rounds == {"plan": 1, "test": 1, "code": 2, "acceptance": 2}
    assert state.pending == {"test": "", "code": ""}


def test_one_send_back_too_many_stops_for_a_human(state):
    state.sendbacks["test"] = 3
    file = f"{REVIEWS}/code-writer-sendback-2.md"

    moved = step(state, "code-writer", "send_back", written={file})

    assert moved.stop
    assert moved.human.stage == "code-writer"
    assert moved.human.questions == [
        "Should the test pair take this send-back too? Answer, then rerun to send it."
    ]


def test_a_stage_that_runs_again_closes_its_send_back(state):
    state.open_sendbacks["code-writer"] = f"{REVIEWS}/code-writer-sendback-2.md"

    moved = step(state, "code-writer", "done", written={PATHS.green_report})

    assert moved.cleared
    assert state.open_sendbacks == {}


# --- stops -----------------------------------------------------------------


def test_needs_human_stops_with_the_agents_questions(state):
    moved = step(state, "plan-writer", "needs_human", summary="stuck", questions=["Which?"])

    assert moved.stop
    assert (moved.human.stage, moved.human.summary, moved.human.questions) == (
        "plan-writer",
        "stuck",
        ["Which?"],
    )


def test_a_status_the_role_may_not_return_is_an_error(state):
    with pytest.raises(RunError, match="may not return 'approved'"):
        step(state, "plan-writer", "approved")


# --- what a verdict needs on disk, asked before the machine moves ------------------


def missing(state, stage, status, *, written=(), proof_rewritten=True):
    state.stage = stage
    return missing_outputs(
        state,
        stage,
        result(status),
        PATHS,
        exists=lambda path: path in written,
        proof_rewritten=proof_rewritten,
    )


def test_a_verdict_with_its_files_in_place_misses_nothing(state):
    assert missing(state, "plan-writer", "done", written={PATHS.plan}) == []


def test_an_approval_without_its_review_misses_the_review(state):
    state.rounds["test"] = 2

    assert missing(state, "test-reviewer", "approved") == [f"{REVIEWS}/test-reviewer-2.md"]


def test_a_reviewer_sending_back_misses_both_files_it_owes(state):
    assert missing(state, "code-reviewer", "send_back") == [
        f"{REVIEWS}/code-reviewer-sendback-2.md",
        f"{REVIEWS}/code-reviewer-1.md",
    ]


def test_an_approval_that_left_the_last_proof_misses_the_proof(state):
    assert missing(
        state, "acceptance-reviewer", "approved", written={PATHS.proof}, proof_rewritten=False
    ) == [PATHS.proof]


def test_a_stop_for_a_human_owes_no_file(state):
    assert missing(state, "plan-reviewer", "needs_human") == []


def test_asking_leaves_the_state_alone(state):
    state.stage = "code-reviewer"
    before = copy.deepcopy(state)

    missing(state, "code-reviewer", "send_back")

    assert state == before
