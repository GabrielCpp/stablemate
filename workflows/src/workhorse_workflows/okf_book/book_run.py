"""What every phase of the okf-book run reads: the repo it writes, and the work set it covers."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Workflow
from workhorse_workflows.okf_book.work_set import WorkSet, read_work_set


class BookRun(Workflow):
    """The base each phase's states sit on. It holds no state of its own."""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def work_set(self) -> WorkSet:
        return read_work_set(self.run_dir) or WorkSet(services=(), files=())
