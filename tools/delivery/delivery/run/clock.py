"""The run's deadline. A hosted runner's job is killed at its time limit, wherever it is; a
stage killed half-way loses its work. So no stage starts without the margin left to finish,
and the run ends at a checkpoint instead."""

from __future__ import annotations


def out_of_time(now: float, deadline: int | None, margin_minutes: int) -> bool:
    """True when a stage started now might not finish by the deadline. None never runs out."""
    return deadline is not None and deadline - now < margin_minutes * 60
