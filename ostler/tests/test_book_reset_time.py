"""A play records how many times its surface reset and how long the resets took."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, module


@pytest.fixture
def todo_app() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


def test_the_time_line_counts_each_reset_the_run_made(todo_app, tmp_path: Path, monkeypatch, capsys):
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
    code = main(["run", "services.api", "--no-stack", "--out", str(tmp_path / "out")])
    shown = capsys.readouterr().out
    line = next(line for line in shown.splitlines() if line.startswith("time: "))
    assert code == 0, shown
    assert counted
    assert re.search(rf"resets {len(counted)}, \d+\.\d s \(\d+\.\d s each\)", line), line
