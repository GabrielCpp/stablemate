"""What every okf-book machine reads: the repo it writes, the folder its records go in, and its work list."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Workflow
from workhorse.worklist import WorkList
from workhorse_workflows.okf_book.shared.work import book_work


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir

    @property
    def work(self) -> WorkList:
        return book_work(self.records_dir)
