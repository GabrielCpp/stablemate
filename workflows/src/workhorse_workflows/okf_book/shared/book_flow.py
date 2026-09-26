"""What every okf-book machine reads: the repo it writes and the folder its records go in."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Workflow


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir
