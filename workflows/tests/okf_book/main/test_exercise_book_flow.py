"""The book run a settle hands off stops the servers its bring-up started."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from okf_book.support import ScriptedRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
from workhorse_workflows.okf_book.workflow import workflow


def _drive(tmp_path: Path) -> ExerciseResult:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id="t0")
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=ScriptedRunner({}),
    )
    return ExerciseResult.model_validate(drive(ExerciseBook(repo_dir=str(tmp_path), service="ledger"), env))


def _stub_run(monkeypatch: pytest.MonkeyPatch, stack: StackReadiness) -> list[tuple[str, ...]]:
    released: list[tuple[str, ...]] = []

    def _compile(*_args: object) -> CompileOutcome:
        return CompileOutcome(gaps=(), planned=True)

    def _bring_up(*_args: object) -> StackReadiness:
        return stack

    def _run_plan(*_args: object) -> ExerciseResult:
        raise RuntimeError("the runner died")

    def _release_stack(_logger: logging.Logger, owned: tuple[str, ...]) -> None:
        released.append(tuple(owned))

    def _release(logger: logging.Logger, readiness: StackReadiness) -> None:
        _release_stack(logger, readiness.owned)

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _bring_up)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run_plan)
    monkeypatch.setattr(exercise_book_flow, "release_stack", _release_stack)
    monkeypatch.setattr(exercise_book_flow, "release", _release)
    return released


def test_the_run_stops_the_servers_it_started_even_when_the_runner_dies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released = _stub_run(monkeypatch, StackReadiness(up=True, serving=True, notes="", owned=("4242", "4343")))

    with pytest.raises(RuntimeError):
        _ = _drive(tmp_path)

    assert released == [("4242", "4343")]


def test_a_stack_that_failed_to_come_up_stops_the_servers_it_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released = _stub_run(monkeypatch, StackReadiness(up=False, serving=False, notes="the launch exited 1", owned=("4242",)))

    result = _drive(tmp_path)

    assert result.stack_down
    assert released == [("4242",)]
