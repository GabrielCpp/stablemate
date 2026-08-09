"""End-to-end state-machine tests for the implement-plan flow."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from coder.implement_plan._support import (
    _Agent,
    _command,
    _decomposition,
    _issue,
    _review,
    _task,
)

def test_dependent_packets_become_separate_verified_remote_commits(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "private-plan.md"
    plan.write_text("# Build two ordered pieces\n", encoding="utf-8")
    first = _task("first-piece", "src/first.txt")
    second = _task("second-piece", "src/second.txt", depends_on=["first-piece"])
    agent = _Agent(
        repo,
        _decomposition(second, first),
        edits={
            "first-piece": {"src/first.txt": "first-piece\n"},
            "second-piece": {"src/second.txt": "second-piece\n"},
        },
    )
    run_env = env()

    result = drive_flow(
        ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), run_env, agent
    )

    assert result.status == "complete"
    assert agent.calls == [
        "decompose-implementation-plan",
        "implement-plan-task",
        "implement-plan-task",
        "review-plan-implementation",
    ]
    subjects = git(repo, "log", "--format=%s", "--reverse").stdout.splitlines()
    assert subjects[-2:] == [
        "feat: implement planned change",
        "feat: implement planned change",
    ]
    assert git(repo, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "main").stdout
    worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "worklist.json").read_text()
    )
    assert [item["status"] for item in worklist["tasks"]] == ["done", "done"]
    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "approved"
    assert review_worklist["issues"] == []


def test_failed_packet_gate_gets_one_repair_turn(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Repair\n", encoding="utf-8")
    task = _task(
        "repair-me",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; assert Path('src/value.txt').read_text() == 'fixed\\n'")
        ],
    )
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"repair-me": {"src/value.txt": "broken\n"}},
        repair_edits={"repair-me": {"src/value.txt": "fixed\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("repair-plan-task") == 1


def test_planning_turn_may_not_edit_the_repository(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan only\n", encoding="utf-8")
    task = _task("later", "src/later.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        planning_edits={"src/planning-leak.txt": "no\n"},
    )

    with pytest.raises(WorkflowFailed, match="expected a clean worktree"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_implementation_turn_may_not_commit(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# No agent commit\n", encoding="utf-8")
    task = _task("owned", "src/owned.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"owned": {"src/owned.txt": "owned\n"}},
        commit_on_task="owned",
    )

    with pytest.raises(WorkflowFailed, match="agent turn moved HEAD"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_out_of_scope_edit_fails_before_commit(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Scoped edit\n", encoding="utf-8")
    task = _task("scoped", "src/owned.txt")
    agent = _Agent(repo, _decomposition(task), edits={"scoped": {"outside.txt": "no\n"}})

    with pytest.raises(WorkflowFailed, match="does not own"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_blocked_agent_result_stops_before_verification(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Blocked\n", encoding="utf-8")
    task = _task("blocked", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"blocked": {"src/value.txt": "partial\n"}},
        blocked_on_task="blocked",
    )

    with pytest.raises(WorkflowFailed, match="implementation blocked"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_review_issues_become_fixed_worklist_before_completion(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Implement and independently review\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    issue = _issue("missing-edge", "src/value.txt", finding="The edge case is absent.")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={
            "initial": {"src/value.txt": "initial\n"},
            "review-1-missing-edge": {"src/value.txt": "fixed\n"},
        },
        reviews=[_review(issue), _review(summary="all blocking issues resolved")],
    )
    run_env = env()

    result = drive_flow(
        ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent
    )

    assert result.status == "complete"
    assert result.review_issue_count == 1
    assert result.review_passes == 2
    assert agent.calls == [
        "decompose-implementation-plan",
        "implement-plan-task",
        "review-plan-implementation",
        "fix-plan-review-issue",
        "review-plan-implementation",
    ]
    assert git(origin, "show", "main:src/value.txt").stdout == "fixed\n"
    subjects = git(repo, "log", "--format=%s", "--reverse").stdout.splitlines()
    assert subjects[-2:] == [
        "feat: implement planned change",
        "fix: implement planned change",
    ]
    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "approved"
    assert [item["id"] for item in review_worklist["resolved_issues"]] == [
        "review-1-missing-edge"
    ]
    completion = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "completion.json").read_text()
    )
    assert completion["review"]["fixed_issue_count"] == 1
    assert completion["review"]["resolved_issues"][0]["id"] == "review-1-missing-edge"


def test_failed_post_review_gate_leaves_no_approved_review_worklist(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Approval is not authority\n", encoding="utf-8")
    marker = tmp_path / "final-gate-ran"
    task = _task("initial", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(
            task,
            final=[
                _command(
                    "from pathlib import Path; "
                    f"marker = Path({str(marker)!r}); "
                    "assert not marker.exists(); "
                    "marker.write_text('ran')"
                )
            ],
        ),
        edits={"initial": {"src/value.txt": "initial\n"}},
        reviews=[_review(summary="looks complete to me")],
    )
    run_env = env()

    with pytest.raises(WorkflowFailed, match="final plan verification failed"):
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent)

    review_worklist = run_env.writer.run_dir / "implement-plan" / "review-worklist.json"
    assert not review_worklist.exists()
    assert not (run_env.writer.run_dir / "implement-plan" / "completion.json").exists()


def test_review_fix_may_not_edit_outside_issue_ownership(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Scoped review fix\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    issue = _issue("scoped", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={
            "initial": {"src/value.txt": "initial\n"},
            "review-1-scoped": {"outside.txt": "not owned\n"},
        },
        reviews=[_review(issue)],
    )

    with pytest.raises(WorkflowFailed, match="does not own"):
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), env(), agent)


def test_review_must_converge_before_claiming_completion(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Bounded review\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    reviews = [
        _review(_issue(f"issue-{cycle}", "src/value.txt"))
        for cycle in range(1, ImplementPlan.MAX_REVIEW_FIX_CYCLES + 2)
    ]
    edits = {"initial": {"src/value.txt": "initial\n"}}
    edits.update(
        {
            f"review-{cycle}-issue-{cycle}": {"src/value.txt": f"fixed {cycle}\n"}
            for cycle in range(1, ImplementPlan.MAX_REVIEW_FIX_CYCLES + 1)
        }
    )
    agent = _Agent(repo, _decomposition(task), edits=edits, reviews=reviews)

    with pytest.raises(WorkflowFailed, match="did not converge"):
        run_env = env()
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent)

    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "blocked"
    assert review_worklist["cycle"] == ImplementPlan.MAX_REVIEW_FIX_CYCLES + 1
    assert review_worklist["issues"][0]["id"].endswith("issue-4")
