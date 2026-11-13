"""The okf-book distribution's composition root: nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook
from workhorse_workflows.okf_book.shared.blueprint import blueprint

workflow = (
    Registry("okf-book", package=__package__)
    .add_blueprints(blueprint)
    .add_flows(python_book=WritePythonBook)
)
main = console_script(workflow.entry_point(WritePythonBook))

__all__ = ["WritePythonBook", "main", "workflow"]
