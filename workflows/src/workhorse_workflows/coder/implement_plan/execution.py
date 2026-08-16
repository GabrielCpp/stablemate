"""Blueprint nodes that execute, verify, and publish validated plan packets."""
from __future__ import annotations

import json
from pathlib import Path

from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.implement_plan import repository
from workhorse_workflows.coder.implement_plan.inventory import write_worklist
from workhorse_workflows.coder.implement_plan.schemas import (
    CommitResult,
    PlanImplementationResult,
    PlanRunContext,
    PlanTask,
    PreparedPlan,
    PublishResult,
    TaskDecision,
    VerificationResult,
)
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.kit import push_to_origin


@blueprint.node
def check_planning_turn(logger, context: PlanRunContext) -> None:
    """A planning-only agent must leave repository identity and content untouched."""
    repository.assert_clean_at(context, context.base_commit, context.base_commit)
    logger.info("planning turn left repository unchanged")


@blueprint.node
def decide_task_entry(
    logger,
    context: PlanRunContext,
    task: PlanTask,
    expected_head: str,
) -> TaskDecision:
    """Resume implementation, or validate the exact commit left in the commit crash window."""
    repository.assert_repository_identity(context)
    repository.assert_remote(context, expected_head)
    head = repository.head(context)
    changed = repository.changed_paths(Path(context.repo_root))
    if head == expected_head:
        if changed:
            logger.info("resuming task %s with %d existing changed paths", task.id, len(changed))
        return TaskDecision(phase="implement")
    if changed:
        raise WorkflowFailed("HEAD moved while the worktree or index is also dirty")
    repository.validate_task_commit(context, task, expected_head, head)
    logger.info("recovered committed task %s at %s", task.id, head[:12])
    return TaskDecision(phase="publish", commit_sha=head)


@blueprint.node
def check_agent_turn(
    logger,
    context: PlanRunContext,
    task: PlanTask,
    expected_head: str,
    require_changes: bool = True,
) -> None:
    """An edit turn may change owned files, but never repository refs or configuration.

    `require_changes=False` is for the tests-only turn: an empty diff there is the red
    gate's verdict to hand back as a bounded rework, not this check's hard failure.
    """
    repository.assert_repository_identity(context)
    repository.assert_remote(context, expected_head)
    if repository.head(context) != expected_head:
        raise WorkflowFailed(f"task {task.id} agent turn moved HEAD")
    repository.assert_owned(context, task, require_changes=require_changes)
    logger.info("task %s agent turn stayed within its repository boundary", task.id)


@blueprint.node
def verify_plan_task(
    logger, context: PlanRunContext, task: PlanTask, expected_head: str
) -> VerificationResult:
    root = Path(context.repo_root)
    check_agent_turn(logger, context, task, expected_head)
    before = repository.worktree_fingerprint(root)
    result = repository.run_commands(root, task.verification)
    repository.assert_repository_identity(context)
    if repository.head(context) != expected_head:
        raise WorkflowFailed(f"task {task.id} verification moved HEAD")
    repository.assert_remote(context, expected_head)
    if repository.worktree_fingerprint(root) != before:
        raise WorkflowFailed(f"task {task.id} verification changed the worktree or index")
    logger.info("task %s verification %s", task.id, "passed" if result.passed else "failed")
    return result


@blueprint.node
def verify_committed_task(
    logger,
    context: PlanRunContext,
    task: PlanTask,
    expected_parent: str,
    commit_sha: str,
) -> VerificationResult:
    """Test the exact clean committed tree that publication will send to origin."""
    repository.assert_clean_at(context, commit_sha, expected_parent)
    repository.validate_task_commit(context, task, expected_parent, commit_sha)
    repository.assert_tree_matches_worktree(context, task, commit_sha)
    with repository.committed_tree(Path(context.repo_root), commit_sha) as candidate:
        result = repository.run_commands(candidate, task.verification)
    repository.assert_clean_at(context, commit_sha, expected_parent)
    if not result.passed:
        raise WorkflowFailed(f"task {task.id} committed verification failed:\n{result.findings}")
    logger.info("task %s committed tree passed verification", task.id)
    return result


@blueprint.node
def commit_plan_task(
    logger, context: PlanRunContext, task: PlanTask, expected_head: str
) -> CommitResult:
    root = Path(context.repo_root)
    repository.assert_repository_identity(context)
    repository.assert_remote(context, expected_head)
    head = repository.head(context)
    if head != expected_head:
        if repository.changed_paths(root):
            raise WorkflowFailed("cannot recover task commit with a dirty worktree")
        repository.validate_task_commit(context, task, expected_head, head)
        return CommitResult(committed=True, commit_sha=head)
    repository.assert_owned(context, task, require_changes=True)
    commit_sha = repository.create_task_commit(context, task)
    repository.validate_task_commit(context, task, expected_head, commit_sha)
    if repository.changed_paths(root):
        raise WorkflowFailed(f"task {task.id} left uncommitted work after its scoped commit")
    logger.info("committed task %s as %s", task.id, commit_sha[:12])
    return CommitResult(committed=True, commit_sha=commit_sha)


@blueprint.node
def publish_plan_task(
    logger,
    context: PlanRunContext,
    task: PlanTask,
    expected_parent: str,
    commit_sha: str,
) -> PublishResult:
    repository.assert_repository_identity(context)
    if repository.head(context) != commit_sha:
        raise WorkflowFailed(f"HEAD moved away from task {task.id} before publication")
    if repository.changed_paths(Path(context.repo_root)):
        raise WorkflowFailed(f"task {task.id} publication requires a clean worktree")
    repository.validate_task_commit(context, task, expected_parent, commit_sha)
    remote = repository.remote_head(context)
    if remote not in {expected_parent, commit_sha}:
        raise WorkflowFailed(
            f"origin/{context.branch} moved to unexpected commit {remote[:12] or '(missing)'}"
        )
    if remote != commit_sha:
        if not push_to_origin(context.repo_root, context.branch):
            raise WorkflowFailed(f"push rejected for {context.branch}; reconcile and revalidate")
        if repository.remote_head(context) != commit_sha:
            raise WorkflowFailed(f"push of task {task.id} could not be verified at origin")
    logger.info("published task %s at %s", task.id, commit_sha[:12])
    return PublishResult(pushed=True, commit_sha=commit_sha)


@blueprint.node
def project_plan_progress(
    logger,
    context: PlanRunContext,
    plan: PreparedPlan,
    index: int,
    completed_commits: list[str],
    blocked: str = "",
) -> None:
    write_worklist(
        context,
        plan,
        current_index=index,
        completed_commits=completed_commits,
        blocked=blocked,
    )
    logger.info("projected plan progress %d/%d", len(completed_commits), len(plan.tasks))


@blueprint.node
def verify_final_candidate(
    logger,
    context: PlanRunContext,
    plan: PreparedPlan,
    completed_commits: list[str],
    expected_head: str,
    expected_remote: str,
) -> VerificationResult:
    repository.assert_clean_at(context, expected_head, expected_remote)
    if len(completed_commits) != len(plan.tasks):
        raise WorkflowFailed("final candidate gate reached without a commit for every task")
    with repository.committed_tree(Path(context.repo_root), expected_head) as candidate:
        result = repository.run_commands(candidate, plan.final_verification)
    repository.assert_clean_at(context, expected_head, expected_remote)
    if not result.passed:
        raise WorkflowFailed(f"final plan verification failed:\n{result.findings}")
    logger.info("final candidate %s passed aggregate verification", expected_head[:12])
    return result


@blueprint.node
def complete_plan(
    logger,
    context: PlanRunContext,
    plan: PreparedPlan,
    completed_commits: list[str],
    expected_head: str,
    review_issue_count: int = 0,
    review_passes: int = 1,
    review_commits: list[str] | None = None,
    review_issue_ids: list[str] | None = None,
) -> PlanImplementationResult:
    """Verify publication identity and write evidence after the candidate was gated."""
    repository.assert_clean_at(context, expected_head, expected_head)
    if len(completed_commits) != len(plan.tasks):
        raise WorkflowFailed("completion reached without a commit for every checkpointed task")
    manifest = {
        "version": 1,
        "plan_digest": context.plan_digest,
        "source_path": context.source_path,
        "branch": context.branch,
        "base_commit": context.base_commit,
        "final_commit": expected_head,
        "tasks": [
            {"id": task.id, "status": "done", "commit_sha": completed_commits[index]}
            for index, task in enumerate(plan.tasks)
        ],
        "final_verification": "passed before the final packet was published",
        "review": {
            "status": "approved",
            "passes": review_passes,
            "fixed_issue_count": review_issue_count,
            "commits": review_commits or [],
            "resolved_issues": [
                {"id": issue_id, "commit_sha": (review_commits or [])[index]}
                for index, issue_id in enumerate(review_issue_ids or [])
            ],
        },
    }
    path = Path(context.worklist_path).with_name("completion.json")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    logger.info("completed plan at %s", expected_head[:12])
    return PlanImplementationResult(
        status="complete",
        plan_digest=context.plan_digest,
        task_count=len(plan.tasks),
        review_issue_count=review_issue_count,
        review_passes=review_passes,
        final_commit=expected_head,
    )


__all__ = [
    "complete_plan",
    "check_agent_turn",
    "check_planning_turn",
    "commit_plan_task",
    "decide_task_entry",
    "project_plan_progress",
    "publish_plan_task",
    "verify_final_candidate",
    "verify_committed_task",
    "verify_plan_task",
]