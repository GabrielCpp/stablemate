"""The todo book of `fixtures/book_todo`, run against the stand-in app the way an author runs a book."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, run_book, runtime, module


@pytest.fixture
def todo_app() -> Iterator:
    app = module("app")
    server = app.TodoServer().start()
    yield server
    server.stop()


@pytest.fixture
def buggy_app() -> Iterator:
    app = module("app")
    server = app.TodoServer(bug="update").start()
    yield server
    server.stop()


def _ostler(arguments: list[str], port: int, cwd: Path) -> subprocess.CompletedProcess[str]:
    binary = Path(sys.executable).parent / "ostler"
    return subprocess.run([str(binary), *arguments], cwd=cwd, env=runtime(port), capture_output=True, text=True,
                          check=False)


def test_check_finds_nothing_wrong_with_the_book(todo_app):
    done = run_book(["check", "services.api"], todo_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "check: 0 findings" in done.stdout


def test_run_plays_the_journeys_the_cells_and_the_input_classes(todo_app, tmp_path: Path):
    done = run_book(["run", "services.api", "--no-stack", "--out", str(tmp_path / "out")], todo_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "5 pass, 0 known defects, 0 fail" in done.stdout
    assert "cells: 38 played on 24 arrangements, 8 impossible, 0 fail" in done.stdout
    assert "inputs: 47 played, 5 diverge as declared, 0 fail" in done.stdout
    assert "27 of 27 answers and 47 of 47 fields witnessed" in done.stdout


def test_explore_names_each_rule_never_refused_under_the_count(todo_app, tmp_path: Path):
    done = run_book(["explore", "services.api", "--no-stack", "--out", str(tmp_path / "out")], todo_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("rules never refused: "))
    count = int(lines[head].rsplit(": ", 1)[1])
    assert count > 0
    assert all(line.startswith("  ") for line in lines[head + 1 : head + 1 + count])
    assert lines[head + 1 + count].startswith("declared scenes never reached: ")


def test_an_update_that_changes_nothing_turns_the_book_red(buggy_app, tmp_path: Path):
    done = run_book(["run", "services.api", "--no-stack", "--out", str(tmp_path / "out")], buggy_app.port)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "FAIL  AWeekOfChores" in done.stdout
    assert "at: PUT /todos/{id}" in done.stdout


def test_the_runtime_starts_the_app_itself_when_the_stack_is_not_skipped(tmp_path: Path):
    done = run_book(["run", "services.api", "--out", str(tmp_path / "out")], _free_port())
    assert done.returncode == 0, done.stdout + done.stderr
    assert "5 pass, 0 known defects, 0 fail" in done.stdout


def test_ostler_book_check_runs_from_the_fixture_root_with_no_import_path(todo_app):
    done = _ostler(["book", "check", "services.api"], todo_app.port, FIXTURE)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().endswith("check: 0 findings")


def test_ostler_book_takes_the_directory_that_holds_the_services_from_dash_c(todo_app, tmp_path: Path):
    done = _ostler(["-C", str(FIXTURE), "book", "check", "services.api"], todo_app.port, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().endswith("check: 0 findings")


def test_ostler_book_help_lists_the_runtimes_verbs(tmp_path: Path):
    done = _ostler(["book", "--help"], 0, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    for verb in ("run", "explore", "check", "search", "plan"):
        assert verb in done.stdout


def test_ostler_book_returns_the_runtimes_exit_code(todo_app, tmp_path: Path):
    done = _ostler(["book", "check", "services.nothing"], todo_app.port, FIXTURE)
    assert done.returncode != 0


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
