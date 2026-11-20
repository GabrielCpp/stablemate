"""`book run --fresh-data` reloads the application's data through the stack's `fresh` command before anything is played."""

from __future__ import annotations

import sys
from pathlib import Path

from book_todo import FIXTURE, module

from ostler.book import Fresh, Stack


def play(todo_app, own_book, tmp_path: Path, monkeypatch, capsys, fresh: Fresh | None, *arguments: str) -> tuple[int, str]:
    from ostler.book.cli import main

    monkeypatch.setenv("TODO_API_PORT", str(todo_app.port))
    monkeypatch.syspath_prepend(str(FIXTURE))
    service = module("services.api.service").service
    kept = service.stack
    monkeypatch.setattr(service, "stack", lambda log_dir: dataclass_with(kept(log_dir), fresh))
    monkeypatch.chdir(FIXTURE)
    code = main(["run", "services.api", "--no-stack", "--partial", "--journey", "TheDayPasses", *arguments, "--out", str(tmp_path / "out")])
    return code, capsys.readouterr().out


def dataclass_with(stack: Stack, fresh: Fresh | None) -> Stack:
    return Stack(stack.processes, stack.log_dir, fresh)


def writing(marker: Path, body: str = "") -> Fresh:
    code = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x'); {body}"
    return Fresh((sys.executable, "-c", code))


def test_the_reload_runs_before_the_first_call_and_the_line_is_printed(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    marker = tmp_path / "marker"
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, writing(marker), "--fresh-data")
    assert code == 0, shown
    assert marker.exists()
    first = shown.splitlines()[0]
    assert first.startswith("data: reloaded by ") and first.endswith("s"), shown
    assert first in (tmp_path / "out" / "api.md").read_text()


def test_a_failing_reload_plays_nothing_and_shows_the_output_tail(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    fresh = writing(tmp_path / "marker", "print('seed broke'); raise SystemExit(7)")
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, fresh, "--fresh-data")
    assert code == 1
    assert "data: reload failed (7)" in shown
    assert "seed broke" in shown
    assert "order:" not in shown


def test_a_reload_that_times_out_is_reported(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    fresh = Fresh((sys.executable, "-c", "import time; time.sleep(30)"), timeout=0.5)
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, fresh, "--fresh-data")
    assert code == 1
    assert "data: reload failed (timed out)" in shown
    assert "order:" not in shown


def managed(monkeypatch, outcome: tuple[int, float, str]) -> list[tuple[Path, str]]:
    from ostler.book.environment import Environment
    from ostler.environments import commands

    asked: list[tuple[Path, str]] = []

    def reset(root, name, wait_seconds=commands.DEFAULT_WAIT_SECONDS, **_):
        asked.append((root, name))
        return outcome

    monkeypatch.setattr(Environment, "copy", lambda self: self.leased or "story-1")
    monkeypatch.setattr(commands, "reset", reset)
    return asked


def test_a_book_with_no_fresh_on_a_managed_copy_resets_the_copy_and_plays(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    asked = managed(monkeypatch, (0, 12.4, ""))
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, None, "--fresh-data", "--copy", "story-7")
    assert code == 0, shown
    assert [name for _root, name in asked] == ["story-7"]
    assert shown.splitlines()[0] == "data: reloaded by resetting the copy story-7 in 12s"
    assert "order:" in shown


def test_a_failed_reset_plays_nothing_and_shows_the_output_tail(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    managed(monkeypatch, (1, 3.0, "story-7 is in use by pid 5: a reset would pull its data from under a play"))
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, None, "--fresh-data", "--copy", "story-7")
    assert code == 1
    assert "data: reload failed (1)" in shown
    assert "is in use by pid 5" in shown
    assert "order:" not in shown


def test_a_book_with_no_fresh_and_no_managed_copy_is_refused(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, None, "--fresh-data")
    assert code == 1
    assert shown.splitlines()[0] == (
        "data: not reloaded, the book states no way to reload it and runs on no copy ostler manages: "
        "state fresh=Fresh(...) on its Stack")
    assert "order:" not in shown


def test_a_book_with_fresh_never_resets_a_copy(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    asked = managed(monkeypatch, (1, 0.0, "must not run"))
    marker = tmp_path / "marker"
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, writing(marker), "--fresh-data")
    assert code == 0, shown
    assert marker.exists() and asked == []
    assert shown.splitlines()[0].startswith("data: reloaded by ")


def test_without_the_flag_nothing_is_reloaded(todo_app, own_book, tmp_path: Path, monkeypatch, capsys):
    marker = tmp_path / "marker"
    code, shown = play(todo_app, own_book, tmp_path, monkeypatch, capsys, writing(marker))
    assert code == 0, shown
    assert not marker.exists()
    assert "data:" not in shown


def test_a_cwd_under_the_book_root_is_resolved_from_it(monkeypatch):
    monkeypatch.chdir(FIXTURE)
    assert Fresh(("true",)).directory() == str(FIXTURE)
    assert Fresh(("true",), cwd="services").directory() == str(FIXTURE / "services")
    assert Fresh(("true",), cwd="/tmp").directory() == "/tmp"
