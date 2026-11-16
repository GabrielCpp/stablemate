"""A play records how many times its surface reset and how long the resets took."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, module


@pytest.fixture
def todo_app() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


@pytest.fixture
def own_book(monkeypatch) -> None:
    """The fixture's `services` package imported anew, so its address is read from this test's port."""
    for name in [n for n in sys.modules if n == "services" or n.startswith("services.")]:
        monkeypatch.delitem(sys.modules, name)


def play(todo_app, own_book, tmp_path: Path, monkeypatch, capsys, *arguments: str) -> tuple[int, str, int]:
    """The run's exit code, its output and the resets its surface made."""
    from ostler.book.cli import main

    surface = module("services.api.surface").TodoApi
    counted = []
    kept = surface.reset

    def reset(self) -> None:
        counted.append(1)
        kept(self)

    monkeypatch.setattr(surface, "reset", reset)
    monkeypatch.setenv("TODO_API_PORT", str(todo_app.port))
    monkeypatch.chdir(FIXTURE)
    code = main(["run", "services.api", "--no-stack", *arguments, "--out", str(tmp_path / "out")])
    return code, capsys.readouterr().out, len(counted)


def test_the_time_line_counts_each_reset_the_run_made(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    code, shown, counted = play(todo_app, own_book, tmp_path, monkeypatch, capsys)
    assert code == 0, shown
    assert counted
    assert re.search(rf"^time: .*resets {counted}, \d+\.\d s \(\d+\.\d s each\)", shown, re.MULTILINE), shown


def test_two_alone_journeys_in_a_row_reset_once_between_them(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    code, shown, counted = play(todo_app, own_book, tmp_path, monkeypatch, capsys,
                                "--partial", "--journey", "TheDayPasses", "--journey", "TheStoreIsDown")
    assert code == 0, shown
    assert "[alone]" in shown
    assert f"resets {counted}," in shown
    assert counted == 4, shown
