from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import CommitTheData


class WrongTurns(Journey):
    """A maintainer runs paddock out of order. A run before the data has a commit is refused. After the commit, a
    benchmark the root does not hold and a task the benchmark does not declare are refused, and so is a resume with no
    round, with a round number that was never made, and with a round that already has its result."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.RunTask(f.run("plain")),
            CommitTheData(),
            c.RunTask(f.run(benchmark="nope")),
            c.RunTask(f.run("nope")),
            c.ResumeTask(f.resume("plain")),
            c.ResumeTask(f.resume("plain", n=7)),
            c.ResumeTask(f.resume(benchmark="nope")),
            c.ResumeTask(f.resume("nope")),
            c.RunTask(f.run("plain")),
            c.ResumeTask(f.resume("plain")),
        )
