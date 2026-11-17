from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import CommitTheData, KeepTheResults


class AStepFails(Journey):
    """A maintainer runs a task that does not fail and then the three tasks that fail on purpose. A step that raises is printed with its error and the
    steps after it are skipped. A step that reads a boolean input as a number fails on its type. A command that is not
    installed fails the step that runs it. Each round still writes a result, whose ledger names the failed and skipped
    steps."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CommitTheData(),
            c.RunTaskThatFails(f.run_step("override")),
            c.RunTaskThatFails(f.run_step("failing")),
            c.RunTaskThatFails(f.run_step("inputs")),
            c.RunTaskThatFails(f.run_step("tools")),
            KeepTheResults(),
        )
