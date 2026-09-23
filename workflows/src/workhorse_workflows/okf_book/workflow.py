"""The okf-book distribution's composition root: nothing else."""
from __future__ import annotations

from workhorse.cli import console_script
from workhorse.pyflow import Registry
from workhorse_workflows.okf_book.aggregate import Aggregate
from workhorse_workflows.okf_book.document import Document
from workhorse_workflows.okf_book.exercise import Exercise
from workhorse_workflows.okf_book.main.flow import OkfBook

workflow = (
    Registry("okf-book", package=__package__)
    .add_blueprints()
    .add_flows(document=Document, aggregate=Aggregate, exercise=Exercise)
    .stub_agents({
        "list-entry-points": {"entry_points": [{"slug": "home", "title": "Home"}]},
        "document-files": {"contracts": []},
        "write-page": {"summary": "stub"},
        "write-operations": {"summary": "stub"},
        "write-flows": {"summary": "stub"},
        "verify-page": {"claims": [], "problems": []},
        "pick-flows": {"ids": []},
        "judge-failure": {"side": "book", "reason": "stub"},
    })
)
main = console_script(workflow.entry_point(OkfBook))

__all__ = ["OkfBook", "main", "workflow"]
