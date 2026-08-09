"""Adversarial Git publication-boundary tests."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.implement_plan.execution import (
    check_planning_turn, commit_plan_task, verify_committed_task,
)
from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from workhorse_workflows.coder.implement_plan.inventory import snapshot_plan
from coder.implement_plan._support import (
    _Agent,
    _command,
    _context,
    _decomposition,
    _prepared,
    _task,
)

def test_origin_mutation_is_detected(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    git(repo, "remote", "set-url", "origin", str(tmp_path / "other.git"))

    with pytest.raises(WorkflowFailed, match="origin configuration changed"):
        check_planning_turn(logger, context)


def test_git_hook_configuration_mutation_is_detected(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", "untrusted-hooks"],
        cwd=repo,
        check=True,
    )

    with pytest.raises(WorkflowFailed, match="Git configuration"):
        check_planning_turn(logger, context)


def test_active_replacement_refs_are_refused_before_planning(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", f"refs/replace/{head}", head)
    plan = tmp_path / "plan.md"
    plan.write_text("# Replacement ref\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="replacement refs"):
        snapshot_plan(logger, str(plan), str(tmp_path / "run"), str(repo))


def test_repository_hook_mutation_stops_before_publication(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    hooks = repo / ".git" / "hooks"
    hook = hooks / "pre-commit"
    hook.write_text(
        "#!/bin/sh\nprintf 'rewritten\\n' > src/value.txt\ngit add src/value.txt\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Hook mutation\n", encoding="utf-8")
    task = _task(
        "hooked",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; assert Path('src/value.txt').read_text() == 'safe\\n'")
        ],
    )
    agent = _Agent(repo, _decomposition(task), edits={"hooked": {"src/value.txt": "safe\n"}})
    remote_before = git(origin, "rev-parse", "main").stdout

    with pytest.raises(WorkflowFailed, match="left uncommitted work"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert git(origin, "rev-parse", "main").stdout == remote_before


def test_repository_hook_rejection_stops_before_commit(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Hook rejection\n", encoding="utf-8")
    task = _task("hooked", "src/value.txt")
    agent = _Agent(repo, _decomposition(task), edits={"hooked": {"src/value.txt": "safe\n"}})
    head_before = git(repo, "rev-parse", "HEAD").stdout

    with pytest.raises(WorkflowFailed, match="could not commit"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert git(repo, "rev-parse", "HEAD").stdout == head_before
    assert git(origin, "rev-parse", "main").stdout == head_before


def test_post_commit_hook_cannot_publish_before_workflow_verification(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    marker = tmp_path / "post-commit-ran"
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text(
        f"#!/bin/sh\ntouch {marker}\ngit push origin HEAD:main\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Controlled publication\n", encoding="utf-8")
    task = _task("controlled", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"controlled": {"src/value.txt": "safe\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert not marker.exists()
    assert git(repo, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "main").stdout


def test_hook_permission_change_after_snapshot_is_detected(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\ngit push origin HEAD:main\n", encoding="utf-8")
    hook.chmod(0o644)
    context = _context(tmp_path, repo, logger)
    hook.chmod(0o755)

    with pytest.raises(WorkflowFailed, match="Git configuration"):
        check_planning_turn(logger, context)


def test_clean_committed_tree_must_pass_packet_verification(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task_data = _task(
        "committed-bytes",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; assert Path('src/value.txt').read_text() == 'safe\\n'")
        ],
    )
    task = _prepared(context, logger, task_data).tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("different\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed verification failed"):
        verify_committed_task(
            logger, context, task, context.base_commit, committed.commit_sha
        )


def test_clean_filter_cannot_hide_different_committed_bytes(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    (repo / ".gitattributes").write_text("src/value.txt filter=mutate\n", encoding="utf-8")
    git(repo, "config", "filter.mutate.clean", "sed s/safe/bad/")
    git(repo, "config", "filter.mutate.smudge", "cat")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-qm", "test: configure filter")
    git(repo, "push", "-q", "origin", "main")
    context = _context(tmp_path, repo, logger)
    task_data = _task(
        "filtered",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; assert Path('src/value.txt').read_text() == 'safe\\n'")
        ],
    )
    task = _prepared(context, logger, task_data).tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("safe\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed bytes differ"):
        verify_committed_task(
            logger, context, task, context.base_commit, committed.commit_sha
        )


def test_unchanged_filtered_baseline_cannot_differ_from_candidate_tree(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    (repo / ".gitattributes").write_text("src/value.txt filter=mutate\n", encoding="utf-8")
    git(repo, "config", "filter.mutate.clean", "sed s/safe/bad/")
    git(repo, "config", "filter.mutate.smudge", "cat")
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("safe\n", encoding="utf-8")
    git(repo, "add", ".gitattributes", "src/value.txt")
    git(repo, "commit", "-qm", "test: configure baseline filter")
    git(repo, "push", "-q", "origin", "main")
    context = _context(tmp_path, repo, logger)
    task = _prepared(context, logger, _task("other", "src/other.txt")).tasks[0]
    (repo / "src" / "other.txt").write_text("other\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed bytes differ"):
        verify_committed_task(
            logger, context, task, context.base_commit, committed.commit_sha
        )


def test_committed_mode_must_match_the_verified_worktree(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    script = repo / "src" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    git(repo, "add", "src/run.sh")
    git(repo, "commit", "-qm", "test: add script")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "config", "core.fileMode", "false")
    context = _context(tmp_path, repo, logger)
    task = _prepared(context, logger, _task("mode", "src/run.sh")).tasks[0]
    script.write_text("#!/bin/sh\nprintf changed\n", encoding="utf-8")
    script.chmod(0o755)
    committed = commit_plan_task(logger, context, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed mode differs"):
        verify_committed_task(
            logger, context, task, context.base_commit, committed.commit_sha
        )
