"""A run on a hosted runner has a deadline. No stage starts without time to finish, so the run
ends at a checkpoint, not in the middle of a stage the job's own limit kills."""

from __future__ import annotations

from delivery.run.clock import out_of_time

NOW = 1_792_150_000


def test_no_deadline_never_runs_out():
    assert not out_of_time(NOW, None, 75)


def test_a_stage_starts_with_the_margin_left():
    assert not out_of_time(NOW, NOW + 75 * 60, 75)


def test_no_stage_starts_with_less_than_the_margin_left():
    assert out_of_time(NOW, NOW + 75 * 60 - 1, 75)


def test_a_deadline_already_past_is_out_of_time():
    assert out_of_time(NOW, NOW - 1, 75)
