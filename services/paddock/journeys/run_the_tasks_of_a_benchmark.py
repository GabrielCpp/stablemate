from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import CommitTheData, KeepTheResults


class RunTheTasksOfABenchmark(Journey):
    """A maintainer lists the benchmark's tasks, commits its data and runs five of them. The plain task copies the data
    with no remote and hands its steps the merged config, once driving the checkout in place and once on a pinned clone
    behind a fence. The override task lays its config over the base. The scored task prints its score. The library task
    calls the helpers a task module imports. They keep each result and read its ledger and score."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.ListBenchmarks(f.ListArgs()),
            CommitTheData(),
            c.RunTask(f.run("plain")),
            c.RunTask(f.run("plain", pinned=True)),
            c.RunTask(f.run("override")),
            c.RunTask(f.run("scored")),
            c.RunTask(f.run("library")),
            KeepTheResults(),
            c.ListBenchmarks(f.ListArgs()),
        )
