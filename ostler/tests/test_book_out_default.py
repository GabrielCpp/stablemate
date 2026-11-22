from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from ostler.book import Axes, Scene
from ostler.book import cli
from tests.book_fakes import Plain


@pytest.fixture
def fake_book(monkeypatch, tmp_path):
    axes = Axes("todo", date(2026, 11, 4), (Scene("open", "an open todo", lambda today: ()),), {}, lambda m: "open")
    service = SimpleNamespace(name="api", matrices=(axes,), new_model=Plain, documentation=None)
    monkeypatch.setattr(cli, "load", lambda name: service)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setattr(cli, "book_root", lambda start: str(cwd))
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return cwd, temp


def test_graph_without_out_writes_under_a_fresh_temp_folder_and_names_it(fake_book, capsys):
    cwd, temp = fake_book
    assert cli.main(["graph", "services.api"]) == 0
    out = capsys.readouterr().out
    made = [p for p in temp.iterdir() if p.name.startswith("ostler-book-api-")]
    assert len(made) == 1
    assert (made[0] / "api-todo.dot").is_file()
    assert f"reports: {made[0]}" in out.splitlines()
    assert not (cwd / "results").exists()
    assert list(cwd.iterdir()) == []


def test_graph_with_out_writes_there_and_prints_no_reports_line(fake_book, capsys, tmp_path: Path):
    cwd, temp = fake_book
    target = tmp_path / "given"
    assert cli.main(["graph", "services.api", "--out", str(target)]) == 0
    out = capsys.readouterr().out
    assert (target / "api-todo.dot").is_file()
    assert "reports:" not in out
    assert list(temp.iterdir()) == []
    assert not (cwd / "results").exists()
