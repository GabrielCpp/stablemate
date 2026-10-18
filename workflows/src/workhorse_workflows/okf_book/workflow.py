"""The okf-book distribution's composition root: nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.flow import OkfBook
from workhorse_workflows.okf_book.main.reground_book_flow import RegroundBook
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook
from workhorse_workflows.okf_book.shared.blueprint import blueprint

workflow = (
    Registry("okf-book", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(write_book=WriteBook, exercise_book=ExerciseBook, reground_book=RegroundBook)
)
main = console_script(workflow.entry_point(OkfBook))

__all__ = ["OkfBook", "main", "workflow"]
