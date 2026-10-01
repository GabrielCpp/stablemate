"""A writer's checks in one turn share the stack the first one brought up, and the turn's end stops it."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.main.nodes import exercise, writer_stack
from workhorse_workflows.okf_book.main.nodes.writer_jobs import settle_jobs
from workhorse_workflows.okf_book.main.nodes.writer_stack import KeptStack
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness

RUNBOOK = "docs/ops/http.md"


class _Stack:
    """Bring-ups that start the process group `owned`, and the groups released, in order."""

    def __init__(self, owned: str) -> None:
        self.owned = owned
        self.brought_up = 0
        self.released: list[tuple[str, ...]] = []

    def bring_up(self, *_args: object) -> StackReadiness:
        self.brought_up += 1
        return StackReadiness(up=True, serving=True, notes="", owned=(self.owned,), app_logs=("/cache/api.log",))

    def release(self, _logger: logging.Logger, readiness: StackReadiness) -> None:
        if readiness.owned:
            self.released.append(readiness.owned)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / RUNBOOK).parent.mkdir(parents=True)
    _ = (root / RUNBOOK).write_text("# HTTP\n", encoding="utf-8")
    return root


def _stub(monkeypatch: pytest.MonkeyPatch, owned: str) -> _Stack:
    stack = _Stack(owned)

    def _compile(*_args: object) -> CompileOutcome:
        return CompileOutcome(gaps=(), planned=True)

    def _run_plan(*_args: object) -> ExerciseResult:
        return ExerciseResult(lines=("All 1 scenarios pass",), passed=True)

    def _stack_pages(*_args: object) -> tuple[str, ...]:
        return (RUNBOOK,)

    monkeypatch.setattr(exercise, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise, "run_plan", _run_plan)
    monkeypatch.setattr(exercise, "release", stack.release)
    monkeypatch.setattr(writer_stack, "bring_up", stack.bring_up)
    monkeypatch.setattr(writer_stack, "release", stack.release)
    monkeypatch.setattr(writer_stack, "stack_pages", _stack_pages)
    return stack


def _check(run_dir: Path, repo: Path) -> ExerciseResult:
    return exercise.exercise_book(KeptStack(run_dir, logging.getLogger(__name__)), repo, "api-service", run_dir / "spec")


def _a_group_that_ended() -> str:
    ended = subprocess.Popen([sys.executable, "-c", ""], start_new_session=True)
    _ = ended.wait()
    return str(ended.pid)


def test_a_second_check_runs_on_the_stack_the_first_left_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path) -> None:
    stack = _stub(monkeypatch, str(os.getpgrp()))

    first = _check(tmp_path, repo)
    second = _check(tmp_path, repo)

    assert first.passed
    assert second.passed
    assert stack.brought_up == 1
    assert stack.released == []


def test_the_end_of_the_turn_stops_the_stack_its_checks_kept_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path) -> None:
    stack = _stub(monkeypatch, str(os.getpgrp()))
    _ = _check(tmp_path, repo)

    settle_jobs(tmp_path)
    _ = _check(tmp_path, repo)

    assert stack.released == [(str(os.getpgrp()),)]
    assert stack.brought_up == 2


def test_a_check_after_its_runbook_changed_brings_the_stack_up_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path) -> None:
    stack = _stub(monkeypatch, str(os.getpgrp()))
    _ = _check(tmp_path, repo)

    _ = (repo / RUNBOOK).write_text("# HTTP\n\nThe server listens on 8081.\n", encoding="utf-8")
    _ = _check(tmp_path, repo)

    assert stack.brought_up == 2
    assert stack.released == [(str(os.getpgrp()),)]


def test_a_check_whose_kept_stack_stopped_brings_it_up_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path) -> None:
    stack = _stub(monkeypatch, _a_group_that_ended())
    _ = _check(tmp_path, repo)

    _ = _check(tmp_path, repo)

    assert stack.brought_up == 2
