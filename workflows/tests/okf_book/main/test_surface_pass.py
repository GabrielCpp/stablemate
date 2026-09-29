"""The operator's answer sends back only the books its blockers named."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import TALLY

from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.main.nodes.surface_pass import read_pass
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.workflow import OkfBook


def test_a_run_that_wrote_no_pass_routes_every_service(tmp_path: Path) -> None:
    assert read_pass(tmp_path, ("tally", "ledger")) == ("tally", "ledger")


def test_the_operators_answer_routes_only_the_books_it_blocked(tmp_path: Path) -> None:
    ledger = Surface(service="ledger", kind=SurfaceKind.CLI, entry="ledger/__main__.py")
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY, ledger))
    _ = book.start()
    _ = record_blocker(tmp_path, Blocker(subject="ledger", service="ledger", phase=Phase.EXERCISE, side=Side.BOOK, reason="failed its run"))

    step = book.resume()

    assert (step.state, step.params) == ("route_book", {"index": 1})
    assert read_pass(tmp_path, book.services) == ("ledger",)
    assert read_blockers(tmp_path) == ()
