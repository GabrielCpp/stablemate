from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import BreakTheHomeConfig


class TheHomeConfigIsWrong(Journey):
    """A maintainer leaves the home config as text that is not TOML. List, run and resume all stop with exit 2 and the
    parser's message, before they read the root."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            BreakTheHomeConfig(),
            c.ListBenchmarks(f.ListArgs()),
            c.RunTask(f.run("plain")),
            c.RunTaskThatFails(f.run_step("failing")),
            c.ResumeTask(f.resume("interrupt")),
        )
