"""The two ways a delivery command fails — the CLI maps each to an exit code."""

from __future__ import annotations


class ConfigError(Exception):
    """The backend asked for can't be built: a bad name, URL or combination. Exit 2."""


class BackendError(Exception):
    """The backend was reached and refused, or couldn't be reached. Exit 1."""


class RunError(Exception):
    """A delivery broke a rule or lost a stage: the run stops, nothing is undone. Exit 1."""
