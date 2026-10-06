"""A server that exits partway through a run stops the run and sends its runbook to repair, instead of failing every later scenario on the book."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse import control
from workhorse.control import FakeChannel, Request
from workhorse.reload import ReloadRequested

from workhorse_workflows.kit.qa import runner
from workhorse_workflows.kit.qa.runner import stack_stopped
from workhorse_workflows.okf_book.shared import book_run
from workhorse_workflows.okf_book.shared.book_run import StackReadiness, run_plan, stack_down_failures
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, ScenarioOutcome

WEB_STACK = "docs/features/web-app/ops/web-app-stack.md"


def _exited_group() -> str:
    server = subprocess.Popen(["true"], start_new_session=True)
    _ = server.wait()
    return str(server.pid)


def test_a_group_with_a_running_process_has_not_stopped() -> None:
    server = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        assert stack_stopped((str(server.pid),)) == ""
    finally:
        server.kill()
        _ = server.wait()


def test_a_group_whose_server_exited_has_stopped() -> None:
    pgid = _exited_group()

    assert f"process group {pgid}" in stack_stopped((pgid,))


def test_a_server_a_later_stack_reaped_is_not_owned_so_the_run_does_not_report_it_stopped(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = subprocess.Popen(["sleep", "30"], start_new_session=True)
    reaped = _exited_group()

    def _bring_up(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        return [{"ready": "yes", "app_pgid": reaped}, {"ready": "yes", "app_pgid": str(server.pid)}]

    monkeypatch.setattr(runner.runbook, "bring_up_stacks", _bring_up)
    try:
        stack = book_run.bring_up(logging.getLogger(__name__), app("globex"), "web-app")

        assert stack.owned == (str(server.pid),)
        assert stack_stopped(stack.owned) == ""
    finally:
        server.kill()
        _ = server.wait()


def test_a_run_whose_server_exited_is_a_stopped_stack_its_runbook_repairs(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    repo = app("globex")
    checks: list[str] = []

    def _run_scenarios(_root: Path, _spec: Path, only: tuple[str, ...], _lap: Path, stack_check: Callable[[], str]) -> RunSummary:
        checks.append(stack_check())
        return RunSummary(status="blocked", runner_errors=(checks[-1],), scenarios={name: ScenarioOutcome(status="failed") for name in only})

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)
    log = tmp_path / "vite.log"
    _ = log.write_text("VITE ready in 300 ms\n", encoding="utf-8")
    stack = StackReadiness(up=True, serving=True, notes="", owned=(_exited_group(),), app_logs=(str(log),))

    result = run_plan(repo, tmp_path / "spec", (), stack, only=("docs-a",))

    assert checks and "exited during the run" in checks[0]
    assert result.stack_down and result.summary is None
    assert "problem:   VITE ready in 300 ms" in result.lines
    (problem,) = stack_down_failures(repo, "web-app", result)[WEB_STACK]
    assert "the app's stack stopped serving" in problem.text


def _run_until_stopped(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: Request, checks: list[str],
) -> None:
    """Run two scenarios on a channel holding *request*, recording in *checks* the reason each check gave."""

    def _run_scenarios(_root: Path, _spec: Path, only: tuple[str, ...], _lap: Path, stack_check: Callable[[], str]) -> RunSummary:
        for _name in only:
            checks.append(stack_check())
            if checks[-1]:
                break
        return RunSummary(status="blocked", runner_errors=(checks[-1],), scenarios={})

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)
    control.arm(FakeChannel(request))
    try:
        _ = run_plan(app("globex"), tmp_path / "spec", (), StackReadiness(up=True, serving=True, notes=""), only=("docs-a", "docs-b"))
    finally:
        control.arm(None)


def test_a_stop_asked_during_a_pass_ends_it_before_the_next_scenario(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    checks: list[str] = []
    with pytest.raises(KeyboardInterrupt):
        _run_until_stopped(app, monkeypatch, tmp_path, Request(action="stop"), checks)

    assert checks == ["the operator stopped the run"]


def test_a_reload_asked_during_a_pass_reaches_the_engine_once_the_runner_returns(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    checks: list[str] = []
    with pytest.raises(ReloadRequested) as raised:
        _run_until_stopped(app, monkeypatch, tmp_path, Request(action="reload", core=True), checks)

    assert raised.value.core
    assert checks == ["the operator asked for a reload"]
