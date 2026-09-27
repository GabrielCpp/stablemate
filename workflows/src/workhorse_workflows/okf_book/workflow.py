"""The okf-book distribution's composition root: nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.flow import OkfBook
from workhorse_workflows.okf_book.main.repair_book_flow import RepairBook
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook

workflow = (
    Registry("okf-book", package=__package__)
    .add_blueprints()
    .add_flows(write_book=WriteBook, repair_book=RepairBook, exercise_book=ExerciseBook)
    .stub_agents({"write-book": "stub", "repair-pages": "stub"})
)
main = console_script(workflow.entry_point(OkfBook))

__all__ = ["OkfBook", "main", "workflow"]
