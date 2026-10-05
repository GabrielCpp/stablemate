"""A repair's account of the pages too large for one writer replaces the account the last repair left."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import PAGE, TALLY

from workhorse_workflows.okf_book.main.nodes.repair_ledger import RepairOutcome
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.workflow import OkfBook


def test_a_repair_that_finds_no_page_too_large_drops_the_blockers_an_earlier_repair_left(tmp_path: Path) -> None:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    stale = Blocker(subject=f"tally: {PAGE}, #add", service="tally", phase=Phase.WRITE, side=Side.WORKFLOW, reason="split the section")
    kept = Blocker(subject="tally: tally/cli.py", service="tally", phase=Phase.WRITE, side=Side.BOOK, reason="needs a note")
    _ = record_blocker(tmp_path, stale)
    _ = record_blocker(tmp_path, kept)

    _ = book.settle_repair(index=0, repaired=RepairOutcome(rounds=1))

    assert read_blockers(tmp_path) == (kept,)
