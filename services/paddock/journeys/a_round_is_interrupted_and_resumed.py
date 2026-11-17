from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import CommitTheData, KeepTheResults


class ARoundIsInterruptedAndResumed(Journey):
    """A step stops the interrupt round after its first step. No result is written, so there is nothing to keep. The
    maintainer resumes it: the first step keeps its outcome, the other two run, and the ledger then holds both
    segments. A second resume has no open round left and a numbered one that was never made is refused."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CommitTheData(),
            c.RunTask(f.run("interrupt")),
            KeepTheResults(),
            c.ResumeTask(f.resume("interrupt", n=7)),
            c.ResumeTask(f.resume("interrupt")),
            KeepTheResults(),
            c.ResumeTask(f.resume("interrupt")),
            c.ResumeTask(f.resume("interrupt", n=1)),
        )
