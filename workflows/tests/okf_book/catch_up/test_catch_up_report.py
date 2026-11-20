"""What the check's output says: the finding lines and the counts of its last line."""
from __future__ import annotations

from workhorse_workflows.okf_book.catch_up.report import read_check


def test_the_counts_come_from_the_last_line_and_the_lines_from_the_findings() -> None:
    said = "CHECK  sources: Ping names no source\nNOTE  index: differs\ncheck: 1 finding, 64 notes\n"

    read = read_check("services.ledger", 1, said)

    assert (read.findings, read.notes, read.lines, read.unlisted) == (1, 64, ["sources: Ping names no source"], 0)


def test_a_last_line_with_no_notes_counts_none() -> None:
    assert read_check("services.ledger", 1, "CHECK  a: b\ncheck: 1 finding\n").notes == 0


def test_a_count_above_the_lines_that_survived_the_tail_is_unlisted() -> None:
    read = read_check("services.ledger", 1, "CHECK  a: b\ncheck: 5 findings\n")

    assert read.findings == 5 and read.unlisted == 4


def test_a_red_check_with_no_finding_lines_gives_its_whole_output() -> None:
    read = read_check("services.ledger", 1, "Traceback\nImportError: nope\n")

    assert read.lines == ["Traceback", "ImportError: nope"] and read.findings == 2 and read.red


def test_a_green_check_that_printed_nothing_has_no_findings() -> None:
    read = read_check("services.ledger", 0, "")

    assert (read.findings, read.notes, read.red) == (0, 0, False)
