"""The errors a benchmark run raises."""

from __future__ import annotations


class RunError(RuntimeError):
    """A task that could not be run, or a result that must not be recorded."""


class RoundInterrupted(RunError):
    """A round that stopped before it finished and left its workspace to be resumed."""
