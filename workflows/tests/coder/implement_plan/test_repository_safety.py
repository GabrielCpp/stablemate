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
    check_planning_turn, commit_plan_task, extend_task_paths, verify_committed_task,
)
from workhorse_workflows.coder.implement_plan import repository
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


def test_another_branchs_tracking_config_is_not_tampering(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """A sibling worktree's `git push -u` must not kill a run mid-packet.

    Worktrees share one `.git/config`, so every branch's tracking keys land in the
    file this run fingerprints — including branches it never touches.
    """
    context = _context(tmp_path, repo, logger)
    subprocess.run(
        ["git", "config", "--local", "branch.some-other-branch.remote", "origin"],
        cwd=repo,
        check=True,
    )

    check_planning_turn(logger, context)


def test_the_running_branchs_own_tracking_config_is_still_watched(
    tmp_path: Path,
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    """Only *other* branches drop out — this run's own settings stay in the digest."""
    context = _context(tmp_path, repo, logger)
    active = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    subprocess.run(
        ["git", "config", "--local", f"branch.{active}.pushRemote", "elsewhere"],
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
    plan = _prepared(context, logger, task_data)
    task = plan.tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("different\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, plan, task, context.base_commit)

    result = verify_committed_task(
        logger, context, plan, task, context.base_commit, committed.commit_sha
    )

    # The verdict is reported rather than raised so the flow can spend a repair turn on
    # it; what this test protects is that the committed bytes are what got tested.
    assert not result.passed


def test_committed_tree_failure_is_repaired_rather_than_ending_the_run(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The gate after the packet's most expensive work is worth a repair turn.

    Only committed files reach the export, so a command that passed in the worktree and
    fails here has found something real — and it used to find it terminally, discarding
    a tests turn, a code turn and a passing verification for a fault one edit wide. The
    commit is retracted, the work stays in the worktree, and the packet is repaired.
    """
    marker = tmp_path / "only-the-first-commit"
    sentinel = tmp_path / "commit-seen"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        f"#!/bin/sh\n[ -e {sentinel} ] || {{ touch {marker}; touch {sentinel}; }}\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Repair a committed tree\n", encoding="utf-8")
    task = _task(
        "committed-repair",
        "src/value.txt",
        verification=[
            _command(f"from pathlib import Path; assert not Path({str(marker)!r}).exists()")
        ],
    )
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"committed-repair": {"src/value.txt": "done\n"}},
        repair_removes=[str(marker)],
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("repair-plan-task") == 1
    # One packet is still one commit: the retracted attempt left no history behind it.
    assert git(repo, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "main").stdout
    assert git(repo, "rev-list", "--count", "HEAD").stdout.strip() == "2"


def test_export_repair_may_add_the_path_the_packet_left_out(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The one repair arm whose finding is about the declaration may change it.

    A committed-tree failure is routinely the report that the packet edited something it
    never declared — only committed files reach the export, so an undeclared edit is
    exactly what goes missing there. Telling the repair turn that and then refusing the
    file it names ended the run over a correct diagnosis. The declaration is widened from
    what the turn touched, and the packet publishes one commit carrying both paths.
    """
    # Tracked and published before the run, so the repair's edit to it is a modification
    # rather than a creation: a created file is already adopted, and adoption is what this
    # is not. It lands before the hook, which must only ever see the workflow's commits.
    (repo / "config.txt").write_text("before\n", encoding="utf-8")
    git(repo, "add", "config.txt")
    git(repo, "commit", "-qm", "chore: add config")
    git(repo, "push", "-q", "origin", "main")
    marker = tmp_path / "only-the-first-commit"
    sentinel = tmp_path / "commit-seen"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        f"#!/bin/sh\n[ -e {sentinel} ] || {{ touch {marker}; touch {sentinel}; }}\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    plan = tmp_path / "plan.md"
    plan.write_text("# Widen a packet\n", encoding="utf-8")
    task = _task(
        "undeclared-path",
        "src/value.txt",
        verification=[
            _command(f"from pathlib import Path; assert not Path({str(marker)!r}).exists()")
        ],
    )
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"undeclared-path": {"src/value.txt": "done\n"}},
        repair_edits={"undeclared-path": {"config.txt": "after\n"}},
        repair_removes=[str(marker)],
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("repair-plan-task") == 1
    committed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(committed) == ["config.txt", "src/value.txt"]
    assert git(repo, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "main").stdout


def test_export_repair_may_not_reach_into_an_already_published_packet(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    """Widening stops at work that is already at origin.

    Adopting a path an earlier packet declared would mean this commit quietly re-edits
    one that has already been published, which no later verification can undo.
    """
    context = _context(tmp_path, repo, logger)
    plan = _prepared(
        context,
        logger,
        _task("first", "src/first.txt"),
        _task("second", "src/second.txt"),
    )
    (repo / "src").mkdir()
    (repo / "src" / "first.txt").write_text("published\n", encoding="utf-8")
    git(repo, "add", "src/first.txt")
    git(repo, "commit", "-qm", "feat: first")
    (repo / "src" / "first.txt").write_text("meddled\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="already published packet"):
        extend_task_paths(logger, context, plan, 1, plan.tasks[1])


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
    plan = _prepared(context, logger, task_data)
    task = plan.tasks[0]
    (repo / "src").mkdir()
    (repo / "src" / "value.txt").write_text("safe\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, plan, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed bytes differ"):
        verify_committed_task(
            logger, context, plan, task, context.base_commit, committed.commit_sha
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
    plan = _prepared(context, logger, _task("other", "src/other.txt"))
    task = plan.tasks[0]
    (repo / "src" / "other.txt").write_text("other\n", encoding="utf-8")
    committed = commit_plan_task(logger, context, plan, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed bytes differ"):
        verify_committed_task(
            logger, context, plan, task, context.base_commit, committed.commit_sha
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
    plan = _prepared(context, logger, _task("mode", "src/run.sh"))
    task = plan.tasks[0]
    script.write_text("#!/bin/sh\nprintf changed\n", encoding="utf-8")
    script.chmod(0o755)
    committed = commit_plan_task(logger, context, plan, task, context.base_commit)

    with pytest.raises(WorkflowFailed, match="committed mode differs"):
        verify_committed_task(
            logger, context, plan, task, context.base_commit, committed.commit_sha
        )


def test_a_packet_may_change_the_paths_of_a_packet_it_depends_on(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """A declared dependency edge is a licence for the change to travel along it.

    The planner writes `paths` before a line of the work exists, so it cannot see the
    call sites a later packet will have to move when it changes a signature underneath
    them — and the dependant's own verification runs the dependency's tests, so refusing
    the edit fails the packet for doing the only thing that could make it pass.
    """
    context = _context(tmp_path, repo, logger)
    plan = _prepared(
        context,
        logger,
        _task("base", "src/base.txt"),
        _task("dependant", "src/dependant.txt", depends_on=["base"]),
    )
    base, dependant = plan.tasks

    assert repository.task_scopes(plan.tasks, dependant) == [
        "src/base.txt",
        "src/dependant.txt",
    ]
    # The edge points one way: the dependency itself gains nothing from its dependant.
    assert repository.task_scopes(plan.tasks, base) == ["src/base.txt"]


def test_a_commit_along_a_dependency_edge_is_not_rejected_after_it_is_staged(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    """The commit is judged by the same reach the turn was authorised against.

    `assert_owned` admits the packet's dependencies' paths and `create_task_commit` stages
    them, so judging the result by `task.paths` alone rejected a commit the same function
    had just made — a packet failed for following an edge it declared, and no turn could
    fix it because the edit was correct.
    """
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "base.txt").write_text("published\n", encoding="utf-8")
    git(repo, "add", "src/base.txt")
    git(repo, "commit", "-qm", "chore: add base")
    git(repo, "push", "-q", "origin", "main")
    context = _context(tmp_path, repo, logger)
    plan = _prepared(
        context,
        logger,
        _task("base", "src/base.txt"),
        _task("dependant", "src/dependant.txt", depends_on=["base"]),
    )
    dependant = plan.tasks[1]
    (repo / "src" / "dependant.txt").write_text("dependant\n", encoding="utf-8")
    (repo / "src" / "base.txt").write_text("consumed\n", encoding="utf-8")

    result = commit_plan_task(logger, context, plan, dependant, context.base_commit)

    assert result.committed


def test_a_packet_may_not_change_the_paths_of_an_unrelated_packet(
    tmp_path: Path,
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    """Two packets with no edge between them are the collision the check is for.

    Nothing orders them, so both may be in flight against the same file, and the second
    commit would silently carry away the first's work.
    """
    # Tracked before the run, so touching it is a modification: a file that did not
    # exist belongs to nobody and is adopted, which is the case this is not.
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "sibling.txt").write_text("published\n", encoding="utf-8")
    git(repo, "add", "src/sibling.txt")
    git(repo, "commit", "-qm", "chore: add sibling")
    context = _context(tmp_path, repo, logger)
    plan = _prepared(
        context,
        logger,
        _task("sibling", "src/sibling.txt"),
        _task("other", "src/other.txt"),
    )

    assert repository.task_scopes(plan.tasks, plan.tasks[1]) == ["src/other.txt"]

    (repo / "src" / "sibling.txt").write_text("trespass\n", encoding="utf-8")
    with pytest.raises(WorkflowFailed, match="changed paths it does not own"):
        repository.assert_owned(
            context,
            plan.tasks[1],
            scopes=repository.task_scopes(plan.tasks, plan.tasks[1]),
        )
