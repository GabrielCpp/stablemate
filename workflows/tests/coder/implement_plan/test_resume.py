"""Checkpoint, projection, verification, and push resume tests."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow import WorkflowFailed
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.implement_plan.execution import (
    commit_plan_task, decide_task_entry, project_plan_progress,
    publish_plan_task, verify_plan_task,
)
from workhorse_workflows.coder.implement_plan.inventory import task_key
from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from coder.implement_plan._support import _Agent, _decomposition, _issue, _review
from coder.implement_plan._support import _command, _context, _prepared, _task

def test_tampered_projection_cannot_skip_a_checkpointed_task(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    plan = _prepared(context, logger, _task("one", "src/one.txt"))
    project_plan_progress(logger, context, plan, 0, [])
    path = Path(context.worklist_path)
    tampered = json.loads(path.read_text())
    tampered["tasks"][0]["status"] = "done"
    tampered["tasks"][0]["payload"]["task"]["paths"] = ["."]
    path.write_text(json.dumps(tampered), encoding="utf-8")

    project_plan_progress(logger, context, plan, 0, [])

    rebuilt = json.loads(path.read_text())
    assert rebuilt["tasks"][0]["status"] == "active"
    assert rebuilt["tasks"][0]["payload"]["task"]["paths"] == ["src/one.txt"]


def test_recovered_commit_requires_expected_parent_and_owned_diff(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task = _prepared(context, logger, _task("recover", "src/owned.txt")).tasks[0]
    (repo / "outside.txt").write_text("no\n", encoding="utf-8")
    git(repo, "add", "outside.txt")
    git(
        repo,
        "commit",
        "-qm",
        f"feat: implement planned change\n\nPlan-Task: {task_key(context, task.id)}",
    )

    with pytest.raises(WorkflowFailed, match="out-of-scope"):
        decide_task_entry(logger, context, task, context.base_commit)


def test_valid_commit_crash_window_is_recovered_without_reimplementation(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task = _prepared(context, logger, _task("recover", "src/owned.txt")).tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "owned.txt").write_text("recover\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, task, context.base_commit)

    decision = decide_task_entry(logger, context, task, context.base_commit)

    assert decision.phase == "publish"
    assert decision.commit_sha == committed.commit_sha


def test_publish_is_idempotent_after_the_push_crash_window(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task = _prepared(context, logger, _task("publish", "src/publish.txt")).tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "publish.txt").write_text("publish\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, task, context.base_commit)

    first = publish_plan_task(
        logger, context, task, context.base_commit, committed.commit_sha
    )
    second = publish_plan_task(
        logger, context, task, context.base_commit, committed.commit_sha
    )

    assert first.commit_sha == second.commit_sha == committed.commit_sha


def test_verification_may_not_rewrite_an_owned_file(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task_data = _task(
        "mutating-check",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; Path('src/value.txt').write_text('changed\\n')")
        ],
    )
    task = _prepared(context, logger, task_data).tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("before\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="verification changed"):
        verify_plan_task(logger, context, task, context.base_commit)


def test_real_checkpoint_resumes_committed_task_without_reimplementation(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., Any],
    drive_flow: Callable[..., Any],
) -> None:
    marker = tmp_path / "stop-after-commit"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Resume committed packet\n", encoding="utf-8")
    task = _task(
        "resume",
        "src/value.txt",
        verification=[_command(f"from pathlib import Path; assert not Path({str(marker)!r}).exists()")],
    )
    agent = _Agent(repo, _decomposition(task), edits={"resume": {"src/value.txt": "done\n"}})
    run_env = env()

    with pytest.raises(WorkflowFailed, match="committed verification failed"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), run_env, agent)

    checkpoint = parse_checkpoint((run_env.writer.run_dir / "checkpoint.json").read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "verify_committed"
    calls_before_resume = list(agent.calls)
    marker.unlink()

    result = drive_flow(
        ImplementPlan(**resume.inputs),
        env(run_dir=run_env.writer.run_dir),
        agent,
        resume,
    )

    assert result.status == "complete"
    assert agent.calls == [*calls_before_resume, "review-plan-implementation"]


def test_nested_review_worklist_resumes_committed_fix_without_re_review(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., Any],
    drive_flow: Callable[..., Any],
) -> None:
    marker = tmp_path / "review-fix-committed"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "if git diff --cached | grep -q 'review-fixed'; then\n"
        f"  touch {marker}\n"
        "fi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Resume a review fix\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    issue = _issue(
        "review-fix",
        "src/value.txt",
        finding="The independent review found the final value was incomplete.",
    )
    issue["verification"] = [
        _command(
            "from pathlib import Path; "
            "assert Path('src/value.txt').read_text() == 'review-fixed\\n'; "
            f"assert not Path({str(marker)!r}).exists()"
        )
    ]
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={
            "initial": {"src/value.txt": "initial\n"},
            "review-1-review-fix": {"src/value.txt": "review-fixed\n"},
        },
        reviews=[_review(issue), _review(summary="fix verified")],
    )
    run_env = env()

    with pytest.raises(WorkflowFailed, match="committed verification failed"):
        drive_flow(
            ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)),
            run_env,
            agent,
        )

    root_checkpoint = parse_checkpoint((run_env.writer.run_dir / "checkpoint.json").read_text())
    root_resume = read_resume(root_checkpoint)
    assert root_resume.state == "route_review"
    child_dir = run_env.writer.run_dir / "review_issues" / "_flow"
    child_checkpoint = parse_checkpoint((child_dir / "checkpoint.json").read_text())
    assert read_resume(child_checkpoint).state == "verify_committed"
    calls_before_resume = list(agent.calls)
    marker.unlink()

    result = drive_flow(
        ImplementPlan(**root_resume.inputs),
        env(run_dir=run_env.writer.run_dir),
        agent,
        root_resume,
    )

    assert result.status == "complete"
    assert result.review_issue_count == 1
    assert agent.calls == [*calls_before_resume, "review-plan-implementation"]
