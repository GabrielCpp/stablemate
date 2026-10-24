"""A book whose cited file changed is read against the change before any repair: the nodes the change bears on reach the writer, and every other citation of the file is stamped on the file as it is now."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import PAGE

from workhorse_workflows.okf_book.main.nodes.gate import keep_failures, take_failures
from workhorse_workflows.okf_book.shared.page_check import PageProblem
LEDGER_PAGE = "docs/services/tally/concepts/ledger-file.md"

def test_failures_kept_twice_for_a_page_are_both_read(tmp_path: Path) -> None:
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "first"),)})
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "second"),), LEDGER_PAGE: (PageProblem(LEDGER_PAGE, "third"),)})

    kept = take_failures(tmp_path, "tally")

    assert [problem.text for problem in kept[PAGE]] == ["first", "second"]
    assert [problem.text for problem in kept[LEDGER_PAGE]] == ["third"]
