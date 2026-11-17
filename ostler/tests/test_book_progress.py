"""A play writes a line to stderr as each journey ends and each phase starts and ends, and closes its stdout with the verdict."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast


from book_todo import FIXTURE


def play(todo_app, own_book, tmp_path: Path, monkeypatch, capsys) -> tuple[int, str, str]:
    from ostler.book import progress
    from ostler.book.cli import main

    ticks = iter(range(0, 100_000))
    monkeypatch.setattr(progress, "CLOCK", lambda: float(next(ticks)))
    monkeypatch.setenv("TODO_API_PORT", str(todo_app.port))
    monkeypatch.chdir(FIXTURE)
    code = main(["run", "services.api", "--no-stack", "--out", str(tmp_path / "out")])
    seen = capsys.readouterr()
    return code, seen.out, seen.err


def test_each_journey_writes_a_progress_line_to_stderr(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    code, shown, said = play(todo_app, own_book, tmp_path, monkeypatch, capsys)
    assert code == 0, shown
    journeys = re.findall(r"^(PASS|KNOWN|SKIP|FAIL)  (\w+)  \(", shown, re.MULTILINE)
    lines = [line for line in said.splitlines() if line.startswith("[")]
    assert journeys
    assert len(lines) == len(journeys)
    for at, ((verdict, name), line) in enumerate(zip(journeys, lines), 1):
        assert line == f"[{at}/{len(journeys)}] {name} {verdict} 1.0s"


def test_each_phase_writes_a_start_and_an_end_line(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    _, _, said = play(todo_app, own_book, tmp_path, monkeypatch, capsys)
    assert "witness: start" in said.splitlines()
    for phase in ("cells", "input classes", "witness"):
        assert f"{phase}: start" in said.splitlines()
        assert f"{phase}: end 1.0s" in said.splitlines()


def test_stdout_closes_with_the_counts_after_everything_else(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    code, shown, said = play(todo_app, own_book, tmp_path, monkeypatch, capsys)
    assert code == 0, shown
    lines = shown.splitlines()
    assert lines[-3] == "verdict"
    assert re.fullmatch(r"\d+ pass, \d+ known defects?, 0 fail(, \d+ skipped)?", lines[-2])
    assert lines[-1] == "green"
    assert not any(line.startswith("[") for line in lines)


def test_a_failing_journey_is_named_in_the_closing_block_and_the_rest_is_counted():
    from ostler.book.journey import JourneyResult
    from ostler.book.progress import NAMED_FAILURES, verdict_lines

    class Result:
        def __init__(self, name: str, ok: bool) -> None:
            self.name = name
            self.ok = ok
            self.verdict = "PASS" if ok else "FAIL"
            self.journey = type(name, (), {"title": staticmethod(lambda: name)})

    results = [Result(f"J{n}", n % 2 == 0) for n in range(2 * (NAMED_FAILURES + 3))]
    lines = verdict_lines(cast("list[JourneyResult]", results), ["journeys", "witness"])
    assert lines[0] == "verdict"
    assert lines[1] == f"{NAMED_FAILURES + 3} pass, 0 known defects, {NAMED_FAILURES + 3} fail"
    assert lines[2] == "red: journeys, witness"
    assert lines[3] == "FAIL  J1"
    assert lines[-1] == "and 3 more failing journeys"
    assert len(lines) == 3 + NAMED_FAILURES + 1
