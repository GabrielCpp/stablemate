"""The text of a book command that goes to the writer is bounded in lines and in width."""
from __future__ import annotations

from workhorse_workflows.okf_book.shared.book_gates import GATE_LINE_CHARS, GATE_TAIL_LINES, tail


def test_a_short_text_comes_back_unchanged() -> None:
    assert tail("one\ntwo") == "one\ntwo"


def test_a_long_text_keeps_its_last_lines() -> None:
    text = "\n".join(f"line {n}" for n in range(300))
    kept = tail(text).splitlines()
    assert len(kept) == GATE_TAIL_LINES
    assert kept[0] == "line 100"
    assert kept[-1] == "line 299"


def test_a_wide_line_is_cut_and_says_how_much() -> None:
    assert tail("x" * 5000) == "x" * GATE_LINE_CHARS + " … [3000 more characters cut]"


def test_one_huge_line_among_many_stays_small() -> None:
    lines = ["short"] * 199 + ["y" * 1_500_000]
    assert len(tail("\n".join(lines))) < 500_000
