"""The text of a book command that goes to the writer is bounded in lines and in width."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest
from workhorse_workflows.okf_book.shared import book_gates
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


def test_a_run_keeps_its_verdict_under_a_long_progress_stream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    progress = "\n".join(f"[{n}/500] J{n} PASS 1.0s" for n in range(1, 501))
    lists = "\n".join(f"- never seen {n}" for n in range(300))
    report = f"{lists}\nverdict\n499 pass, 0 known defects, 1 fail\nFAIL  J7"

    def _run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout=report, stderr=progress)

    monkeypatch.setattr(book_gates, "run_tool", _run)
    gate = book_gates.python_book_run(logging.getLogger("t"), tmp_path, "services.api", tmp_path)
    lines = gate.output.splitlines()
    assert lines[-1] == "FAIL  J7"
    assert lines[-2] == "499 pass, 0 known defects, 1 fail"
    assert "[500/500] J500 PASS 1.0s" in lines
    assert "[480/500] J480 PASS 1.0s" not in lines
    assert len(lines) == 20 + 1 + GATE_TAIL_LINES
