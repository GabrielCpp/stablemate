"""paddock — one benchmark harness."""

from __future__ import annotations

from paddock.registry import Score, Step, Task, TaskError, step, task
from paddock.runner import CommandResult, Run, RunError

__all__ = [
    "CommandResult",
    "Run",
    "RunError",
    "Score",
    "Step",
    "Task",
    "TaskError",
    "step",
    "task",
]
