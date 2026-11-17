from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import AddABrokenBenchmark, CommitTheData, EmptyTheRoot


class ABenchmarkThatDoesNotLoad(Journey):
    """A maintainer lists the benchmarks, adds one whose tasks.py raises, and lists again: the good benchmark's tasks
    are still printed and the exit is 1. A benchmark name is still refused with both benchmarks named. They then point
    paddock_dir at a folder with no gold/: the list says there are no benchmarks and a run names none."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CommitTheData(),
            c.ListBenchmarks(f.ListArgs()),
            AddABrokenBenchmark(),
            c.ListBenchmarks(f.ListArgs()),
            c.RunTask(f.run(benchmark="nope")),
            c.RunTask(f.run("plain")),
            EmptyTheRoot(),
            c.ListBenchmarks(f.ListArgs()),
            c.RunTask(f.run("plain")),
            c.ResumeTask(f.resume("plain")),
        )
