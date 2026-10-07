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

    def _serving(_owned: tuple[str, ...]) -> str:
        return ""

    def _run_plan(*_args: object) -> ExerciseResult:
        raise RuntimeError("the runner died")

    def _release_stack(_logger: logging.Logger, owned: tuple[str, ...]) -> None:
        released.append(tuple(owned))

    def _release(logger: logging.Logger, readiness: StackReadiness) -> None:
        _release_stack(logger, readiness.owned)

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _bring_up)
    monkeypatch.setattr(exercise_book_flow, "stack_stopped", _serving)
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


def _stub_dead_server(monkeypatch: pytest.MonkeyPatch, gone: list[bool]) -> tuple[list[tuple[str, ...]], list[str]]:
    """A stack whose server each check in *gone* reports dead or serving, in turn, and a runner that passes."""
    released: list[tuple[str, ...]] = []
    owned = iter(("4242", "4343", "4444"))
    brought: list[str] = []

    def _compile(*_args: object) -> CompileOutcome:
        return CompileOutcome(gaps=(), planned=True)

    def _bring_up(*_args: object) -> StackReadiness:
        brought.append(next(owned))
        return StackReadiness(up=True, serving=True, notes="", owned=(brought[-1],))

    def _stopped(_owned: tuple[str, ...]) -> str:
        return "the server exited" if gone.pop(0) else ""

    def _run_plan(*_args: object) -> ExerciseResult:
        return ExerciseResult(lines=(), passed=True)

    def _release_stack(_logger: logging.Logger, pgids: tuple[str, ...]) -> None:
        released.append(tuple(pgids))

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _bring_up)
    monkeypatch.setattr(exercise_book_flow, "stack_stopped", _stopped)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run_plan)
    monkeypatch.setattr(exercise_book_flow, "release_stack", _release_stack)
    return released, brought


def test_a_server_gone_before_the_first_scenario_comes_up_again_before_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released, brought = _stub_dead_server(monkeypatch, [True])

    result = _drive(tmp_path)

    assert result.passed
    assert brought == ["4242", "4343"]
    assert released == [("4242",), ("4343",)]


def test_a_server_that_dies_again_after_coming_back_is_run_once_rather_than_restarted_forever(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gone = [True, True]
    released, brought = _stub_dead_server(monkeypatch, gone)

    _ = _drive(tmp_path)

    assert brought == ["4242", "4343"]
    assert released == [("4242",), ("4343",)]
    assert gone == [True]


def test_a_run_resumed_after_its_retry_brings_the_server_up_once_more(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released, brought = _stub_dead_server(monkeypatch, [True, True])
    retry = exercise_book_flow.bring_up

    def _resumed_after(logger: logging.Logger, root: Path, service: str) -> StackReadiness:
        readiness = retry(logger, root, service)
        if len(brought) == 2:
            monkeypatch.setattr(exercise_book_flow, "_THIS_PROCESS", "the resumed process")
        return readiness

    monkeypatch.setattr(exercise_book_flow, "bring_up", _resumed_after)

    result = _drive(tmp_path)

    assert result.passed
    assert brought == ["4242", "4343", "4444"]
    assert released == [("4242",), ("4343",), ("4444",)]
