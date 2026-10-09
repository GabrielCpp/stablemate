"""A long check or scenario run hands its result to the call that asks for it again, whenever the first call came back early."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.main.nodes import writer_jobs
from workhorse_workflows.okf_book.main.nodes.writer_commands import CommandOutput, WriterCommandState, read_command_state, write_command_state
from workhorse_workflows.okf_book.main.nodes.writer_jobs import (
    STILL_RUNNING_LINE,
    STOPPED_LINE,
    finish_job,
    job_folder,
    jobs_folder,
    run_or_attach,
    settle_jobs,
)

PASSED = CommandOutput(0, ("All 1 scenarios pass",))


def _passed(_argv: Sequence[str]) -> CommandOutput:
    return PASSED


def _state(tmp_path: Path) -> str:
    (tmp_path / "repo" / "docs").mkdir(parents=True)
    return str(write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path / "repo", service="ledger")))


def _runs_spent(state: str) -> int:
    return read_command_state(Path(state)).check_and_scenario_runs


def _pending(job: Path, pid: int) -> None:
    _ = (job / "pid").write_text(str(pid), encoding="utf-8")


def _here(job: Path, argv: Sequence[str]) -> None:
    finish_job(job, _passed, argv)


def _ended_pid() -> int:
    process = subprocess.Popen(["true"])
    _ = process.wait()
    return process.pid


def test_a_call_that_outlives_its_wait_is_told_to_ask_again_and_the_next_call_reads_the_result_without_spending_a_run(tmp_path: Path) -> None:
    state = _state(tmp_path)
    argv = (state, "docs/a.md")

    def _still_going(job: Path, _argv: Sequence[str]) -> None:
        _pending(job, os.getpid())

    first = run_or_attach("exercise", argv, _still_going, wait_s=0)
    finish_job(job_folder("exercise", argv), _passed, argv)
    second = run_or_attach("exercise", argv, _still_going, wait_s=0)

    assert first == CommandOutput(1, (STILL_RUNNING_LINE,))
    assert second == PASSED
    assert _runs_spent(state) == 1


def test_a_result_is_read_again_until_a_page_changes_and_then_the_command_runs_anew(tmp_path: Path) -> None:
    state = _state(tmp_path)
    argv = (state,)

    first = run_or_attach("check", argv, _here, wait_s=0)
    again = run_or_attach("check", argv, _here, wait_s=0)
    _ = (tmp_path / "repo" / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
    anew = run_or_attach("check", argv, _here, wait_s=0)

    assert first == again == anew == PASSED
    assert _runs_spent(state) == 2


def test_a_result_is_not_read_again_once_the_repository_opts_in_another_qa_tool(tmp_path: Path) -> None:
    state = _state(tmp_path)
    argv = (state,)

    first = run_or_attach("exercise", argv, _here, wait_s=0)
    _ = (tmp_path / "repo" / "agents.yml").write_text("qa:\n  tools:\n    - ledger\n", encoding="utf-8")
    anew = run_or_attach("exercise", argv, _here, wait_s=0)

    assert first == anew == PASSED
    assert _runs_spent(state) == 2


def test_a_run_whose_process_ended_without_a_result_says_so_and_the_next_call_starts_it_again(tmp_path: Path) -> None:
    state = _state(tmp_path)
    argv = (state,)

    def _dies(job: Path, _argv: Sequence[str]) -> None:
        _pending(job, _ended_pid())

    stopped = run_or_attach("check", argv, _dies, wait_s=0)
    rerun = run_or_attach("check", argv, _here, wait_s=0)

    assert stopped == CommandOutput(1, (STOPPED_LINE,))
    assert rerun == PASSED
    assert _runs_spent(state) == 2


def test_work_that_raises_leaves_a_failed_result(tmp_path: Path) -> None:
    state = _state(tmp_path)

    def _raises(_argv: Sequence[str]) -> CommandOutput:
        raise RuntimeError("the stack is gone")

    def _start(job: Path, argv: Sequence[str]) -> None:
        finish_job(job, _raises, argv)

    assert run_or_attach("exercise", (state,), _start, wait_s=0) == CommandOutput(1, ("the run failed: RuntimeError: the stack is gone",))


def test_settling_waits_for_a_job_a_turn_left_running_and_clears_every_job(tmp_path: Path) -> None:
    state = _state(tmp_path)
    process = subprocess.Popen(["sleep", "0.3"])

    def _left_running(job: Path, _argv: Sequence[str]) -> None:
        _pending(job, process.pid)

    _ = run_or_attach("exercise", (state,), _left_running, wait_s=0)
    settle_jobs(Path(state).parent)

    assert process.poll() is not None
    assert not jobs_folder(Path(state).parent).exists()


def test_settling_stops_a_job_still_running_at_the_deadline_with_the_processes_it_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer_jobs, "SETTLE_WAIT_S", 0.0)
    state = _state(tmp_path)
    leader = subprocess.Popen(["sh", "-c", "sleep 60 & wait"], start_new_session=True)

    def _left_running(job: Path, _argv: Sequence[str]) -> None:
        _pending(job, leader.pid)

    _ = run_or_attach("exercise", (state,), _left_running, wait_s=0)
    settle_jobs(Path(state).parent)

    assert leader.wait(timeout=5) != 0
    assert not jobs_folder(Path(state).parent).exists()


def test_a_call_waits_as_long_as_the_agents_shell_lets_one_command_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(writer_jobs.SHELL_LIMIT_VAR, "600000")

    assert writer_jobs.attach_wait_s() == 600 - writer_jobs.SHELL_LIMIT_MARGIN_S


def test_a_call_waits_the_short_default_where_the_shell_names_no_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(writer_jobs.SHELL_LIMIT_VAR, raising=False)

    assert writer_jobs.attach_wait_s() == writer_jobs.ATTACH_WAIT_S
