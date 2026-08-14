"""End-to-end state-machine tests for the stage-plan flow."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.stage_plan.execution import verify_staged_candidate
from workhorse_workflows.coder.stage_plan.flow import StagePlan
from coder.stage_plan._support import (
    FIRST,
    PLAN_TEXT,
    SECOND,
    Agent,
    command,
    decomposition,
    exists,
    slice_of,
    slicing,
)


def _plan(tmp_path: Path) -> Path:
    path = tmp_path / "source-plan.md"
    path.write_text(PLAN_TEXT, encoding="utf-8")
    return path


def _agent(repo: Path, **overrides: Any) -> Agent:
    return Agent(
        repo,
        slicing(
            slice_of("first", FIRST, "src/first.txt"),
            slice_of("second", SECOND, "src/second.txt"),
        ),
        phases={
            FIRST: decomposition("first-piece", "src/first.txt"),
            SECOND: decomposition("second-piece", "src/second.txt"),
        },
        edits={
            "first-piece": {"src/first.txt": "first\n"},
            "second-piece": {"src/second.txt": "second\n"},
        },
        **overrides,
    )


def test_each_phase_is_implemented_and_reviewed_on_its_own(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    ran: Callable[..., bool],
) -> None:
    agent = _agent(repo)
    run_env = env()

    result = drive_flow(
        StagePlan(plan_path=str(_plan(tmp_path)), repo_dir=str(repo)), run_env, agent
    )

    assert result.status == "complete"
    assert result.stage_count == 2
    assert result.task_count == 2
    assert agent.calls == [
        "slice-implementation-plan",
        "decompose-implementation-plan",
        "implement-plan-task-tests",
        "implement-plan-task-code",
        "review-plan-implementation",
        "decompose-implementation-plan",
        "implement-plan-task-tests",
        "implement-plan-task-code",
        "review-plan-implementation",
    ]
    assert (repo / "src" / "first.txt").is_file()
    assert (repo / "src" / "second.txt").is_file()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == result.final_commit
    assert git(repo, "rev-parse", "origin/main").stdout.strip() == result.final_commit
    assert ran(run_env, verify_staged_candidate)


def test_the_repository_wide_gate_runs_once_over_the_accumulated_tree(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Each phase gated only its own slice; only the staged gate sees both files.

    The first phase's own final verification passes with `src/second.txt` absent, so a
    run that never reached the staged gate would still report complete. Requiring a file
    the last phase creates is what makes the assertion about *this* gate.
    """
    agent = _agent(repo)
    agent.proposal["final_verification"] = [exists("src/first.txt", "src/second.txt")]
    run_env = env()

    result = drive_flow(
        StagePlan(plan_path=str(_plan(tmp_path)), repo_dir=str(repo)), run_env, agent
    )

    stage_dir = Path(json.loads(
        (run_env.writer.run_dir / "stage-plan" / "snapshot.json").read_text()
    )["stage_dir"])
    completion = json.loads((stage_dir / "completion.json").read_text())
    assert completion["final_commit"] == result.final_commit
    assert [phase["id"] for phase in completion["phases"]] == ["first", "second"]
    assert all(phase["status"] == "done" for phase in completion["phases"])


def test_a_failing_phase_stops_the_run_with_earlier_phases_intact(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _agent(repo, skip_edit_for="second-piece")
    run_env = env()

    with pytest.raises(WorkflowFailed):
        drive_flow(
            StagePlan(plan_path=str(_plan(tmp_path)), repo_dir=str(repo)), run_env, agent
        )

    stage_dir = run_env.writer.run_dir / "stage-plan"
    worklist = json.loads((stage_dir / "worklist.json").read_text())
    assert [phase["status"] for phase in worklist["phases"]] == ["done", "active"]
    assert (stage_dir / "phases" / "first").is_dir()
    assert not (stage_dir / "completion.json").exists()
    assert (repo / "src" / "first.txt").is_file()
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == (
        worklist["phases"][0]["payload"]["final_commit"]
    )


def test_each_finished_phase_is_archived_before_the_next_one_reuses_the_scope(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _agent(repo)
    run_env = env()

    drive_flow(
        StagePlan(plan_path=str(_plan(tmp_path)), repo_dir=str(repo)), run_env, agent
    )

    archive = run_env.writer.run_dir / "stage-plan" / "phases"
    assert sorted(path.name for path in archive.iterdir() if path.is_dir()) == [
        "first",
        "second",
    ]
    for identity in ("first", "second"):
        assert (archive / identity / "checkpoint.json").is_file()
        outcome = json.loads((archive / f"{identity}.json").read_text())
        assert outcome["task_count"] == 1


def test_a_resume_re_enters_the_unfinished_phase(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A kill inside the second phase must not re-run the first one's agent turns.

    The pre-commit hook is how the failure lands *after* the phase's own edit turn: the
    worktree verification passes, the marker appears with the commit, and the committed
    tree fails — which is the same shape as a kill between commit and verification.
    """
    marker = tmp_path / "stop-after-commit"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "if git diff --cached --name-only | grep -q 'second'; then\n"
        f"  touch {marker}\n"
        "fi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    agent = _agent(repo)
    agent.phases[SECOND]["tasks"][0]["verification"] = [
        exists("src/second.txt"),
        command(f"from pathlib import Path; assert not Path({str(marker)!r}).exists()"),
    ]
    run_env = env()

    with pytest.raises(WorkflowFailed):
        drive_flow(
            StagePlan(plan_path=str(_plan(tmp_path)), repo_dir=str(repo)), run_env, agent
        )

    resume = read_resume(
        parse_checkpoint((run_env.writer.run_dir / "checkpoint.json").read_text())
    )
    assert resume.state == "stage"
    assert resume.params["index"] == 1
    child = run_env.writer.run_dir / "implement_plan" / "_flow"
    assert read_resume(parse_checkpoint((child / "checkpoint.json").read_text())).state == (
        "verify_committed"
    )
    calls_before_resume = list(agent.calls)
    marker.unlink()

    result = drive_flow(
        StagePlan(**resume.inputs),
        env(run_dir=run_env.writer.run_dir),
        agent,
        resume,
    )

    assert result.status == "complete"
    assert agent.count("slice-implementation-plan") == 1
    assert agent.count("decompose-implementation-plan") == 2
    assert agent.calls[: len(calls_before_resume)] == calls_before_resume
