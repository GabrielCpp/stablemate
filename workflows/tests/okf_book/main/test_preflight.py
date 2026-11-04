"""Before its first writer turn the run renders the agent files and brings each declared stack up once, so a setup failure waits at the start."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from okf_book.support import bound
from workhorse.pyflow import Await

from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.main.nodes import preflight
from workhorse_workflows.okf_book.shared import book_flow
from workhorse_workflows.okf_book.shared.book_run import StackReadiness
from workhorse_workflows.okf_book.workflow import OkfBook

RUNBOOK = "docs/services/tally/ops/http.md"


def _book(tmp_path: Path, *, with_folder: bool = True) -> OkfBook:
    if with_folder:
        (tmp_path / "docs/services/tally").mkdir(parents=True)
    return bound(OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,)))


def _stack(monkeypatch: pytest.MonkeyPatch, readiness: StackReadiness) -> tuple[list[str], list[tuple[str, ...]]]:
    brought_up: list[str] = []
    released: list[tuple[str, ...]] = []

    def _bring_up(_logger: logging.Logger, _root: Path, service: str) -> StackReadiness:
        brought_up.append(service)
        return readiness

    def _release(_logger: logging.Logger, stack: StackReadiness) -> None:
        released.append(stack.owned)

    def _pages(_root: Path, _service: str) -> tuple[str, ...]:
        return (RUNBOOK,)

    monkeypatch.setattr(exercise_book_flow, "bring_up", _bring_up)
    monkeypatch.setattr(preflight, "release", _release)
    monkeypatch.setattr(preflight, "stack_pages", _pages)
    return brought_up, released


def test_a_declared_stack_that_does_not_come_up_waits_before_any_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    brought_up, released = _stack(monkeypatch, StackReadiness(up=False, serving=False, notes="port 8000 is taken", owned=("41",)))
    book = _book(tmp_path)

    step = book.start()

    assert isinstance(step, Await)
    assert step.path == book.run_dir / book_flow.PREFLIGHT_GATE
    assert "`tally`" in step.questions
    assert "port 8000 is taken" in step.questions
    assert step.state == "start"
    assert brought_up == ["tally"] and released == [("41",)]


def test_a_declared_stack_that_comes_up_is_released_and_the_run_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, released = _stack(monkeypatch, StackReadiness(up=True, serving=True, notes="", owned=("41",)))
    book = _book(tmp_path)

    step = book.start()

    assert (step.state, step.params) == ("route_book", {"index": 0})
    assert released == [("41",)]


def test_an_agent_files_render_failure_waits_before_any_stack_comes_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    brought_up, _ = _stack(monkeypatch, StackReadiness(up=True, serving=True, notes=""))

    def _unrendered(_root: Path) -> str:
        return "farrier could not render them: no library"

    monkeypatch.setattr(book_flow, "render_agent_files_returning_failure", _unrendered)
    book = _book(tmp_path)

    step = book.start()

    assert isinstance(step, Await)
    assert step.path == book.run_dir / book_flow.RENDER_GATE
    assert step.state == "start"
    assert "no library" in step.questions
    assert brought_up == []


def test_a_surface_with_no_book_folder_starts_as_before(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    brought_up, _ = _stack(monkeypatch, StackReadiness(up=False, serving=False, notes="never asked"))
    book = _book(tmp_path, with_folder=False)

    step = book.start()

    assert (step.state, step.params) == ("route_book", {"index": 0})
    assert brought_up == []
