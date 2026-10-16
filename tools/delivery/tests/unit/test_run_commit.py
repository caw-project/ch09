"""What the runner commits its branch with: a checkpoint after every stage, and one for a
stop, a failure and the approval — so a delivery outlives the machine it ran on."""

from __future__ import annotations

from delivery.run.commit import (
    accepted_message,
    checkpoint_message,
    failed_message,
    stop_message,
)


def test_a_checkpoint_names_the_stage_its_result_and_round_with_the_summary_as_body():
    assert checkpoint_message("gh-3", "test-reviewer", "approved", 1, "Tests fail as planned.") == (
        "delivery(gh-3): test-reviewer approved, round 1\n\nTests fail as planned.\n"
    )


def test_a_stop_for_a_human_says_where_it_stopped():
    assert stop_message("gh-3", "plan-reviewer", 2, "Which tenancy rule?") == (
        "delivery(gh-3): needs a human at plan-reviewer, round 2\n\nWhich tenancy rule?\n"
    )


def test_a_failure_carries_the_error_as_its_body():
    assert failed_message("issue-8", "code-writer", 1, "code-writer wrote outside ^src/") == (
        "delivery(issue-8): failed at code-writer, round 1\n\ncode-writer wrote outside ^src/\n"
    )


def test_the_approval_is_accepted():
    assert accepted_message("gh-3", "Proven on the preview.") == (
        "delivery(gh-3): accepted\n\nProven on the preview.\n"
    )


def test_an_empty_summary_leaves_a_subject_alone():
    assert checkpoint_message("gh-3", "plan-writer", "done", 1, "  ") == (
        "delivery(gh-3): plan-writer done, round 1\n"
    )
