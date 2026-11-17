from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import CommitTheData, KeepTheResults, StopARound


class ARoundStoppedFromOutside(Journey):
    """A maintainer starts the interrupt task by hand and its round is stopped before the last two steps, as Ctrl-C
    would stop it. They resume it, the first step keeps its outcome and the other two run, and they keep the result."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CommitTheData(),
            StopARound(),
            c.ResumeTask(f.resume("interrupt")),
            KeepTheResults(),
        )
