"""Validate and project the independent post-implementation review worklist."""
from __future__ import annotations

import json
from pathlib import Path

from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.implement_plan import repository
from workhorse_workflows.coder.implement_plan.inventory import prepare_plan
from workhorse_workflows.coder.implement_plan.schemas import (
    PlanDecomposition,
    PlanReview,
    PlanRunContext,
    PreparedPlan,
    ReviewFixResult,
)
from workhorse_workflows.coder.shared.blueprint import blueprint


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@blueprint.node
def check_review_turn(logger, context: PlanRunContext, expected_head: str) -> None:
    """The independent reviewer is read-only and reviews the published candidate."""
    repository.assert_clean_at(context, expected_head, expected_head)
    logger.info("candidate review left repository %s unchanged", expected_head[:12])


@blueprint.node
def validate_review_report(logger, review: PlanReview) -> None:
    """Refuse a blank, contradictory, or unsupported semantic-review verdict."""
    if review.status not in {"approved", "issues"}:
        raise WorkflowFailed(
            f"implementation review returned {review.status or 'no status'}: "
            f"{review.summary or 'no review summary'}"
        )
    if not review.summary.strip():
        raise WorkflowFailed("implementation review needs a substantive summary")
    if review.status == "approved" and review.issues:
        raise WorkflowFailed("implementation review claimed approval while listing issues")
    if review.status == "issues" and not review.issues:
        raise WorkflowFailed("implementation review reported issues without an issue worklist")
    logger.info("implementation review returned %s", review.status)


@blueprint.node
def prepare_review_issues(
    logger,
    review: PlanReview,
    context: PlanRunContext,
    root_plan: PreparedPlan,
    cycle: int,
) -> PreparedPlan:
    """Turn one review's findings into a uniquely identified validated packet batch."""
    validate_review_report(logger, review)
    if review.status != "issues":
        raise WorkflowFailed("cannot prepare a review worklist from an approved review")
    prefix = f"review-{cycle + 1}-"
    original_ids = {issue.id for issue in review.issues}
    rewritten = []
    for issue in review.issues:
        if not issue.id.strip():
            raise WorkflowFailed("review issue needs an id to be addressable across cycles")
        if not issue.finding.strip():
            raise WorkflowFailed(f"review issue {issue.id or '(missing id)'} needs concrete evidence")
        unknown = set(issue.depends_on) - original_ids
        if unknown:
            raise WorkflowFailed(
                f"review issue {issue.id} has unknown dependencies: {', '.join(sorted(unknown))}"
            )
        rewritten.append(
            issue.model_copy(
                update={
                    "id": prefix + issue.id,
                    "depends_on": [prefix + dependency for dependency in issue.depends_on],
                }
            )
        )
    return prepare_plan(
        logger,
        PlanDecomposition(
            status="ready",
            summary=review.summary,
            tasks=rewritten,
            final_verification=root_plan.final_verification,
        ),
        context,
    )


@blueprint.node
def project_review_progress(
    logger,
    context: PlanRunContext,
    plan: PreparedPlan,
    cycle: int,
    index: int,
    completed_commits: list[str],
    blocked: str = "",
) -> None:
    """Project review checkpoint authority without making the JSON a scheduler."""
    items: list[wl.WorkItem] = []
    for item_index, issue in enumerate(plan.tasks):
        if item_index < len(completed_commits):
            status, commit_sha = "done", completed_commits[item_index]
        elif item_index == index and blocked == issue.id:
            status, commit_sha = "blocked", ""
        elif item_index == index:
            status, commit_sha = "active", ""
        else:
            status, commit_sha = "pending", ""
        items.append(
            wl.WorkItem(
                id=issue.id,
                status=status,
                kind="review-issue",
                order=item_index + 1,
                payload={"issue": issue.model_dump(mode="json"), "commit_sha": commit_sha},
            )
        )
    _atomic_json(
        Path(context.worklist_path).with_name("review-worklist.json"),
        {
            "version": 1,
            "plan_digest": context.plan_digest,
            "cycle": cycle + 1,
            "status": "blocked" if blocked else ("done" if index >= len(plan.tasks) else "active"),
            "issues": [item.model_dump(exclude_unset=True, mode="json") for item in items],
        },
    )
    logger.info("projected review cycle %d progress %d/%d", cycle + 1, index, len(plan.tasks))


@blueprint.node
def project_review_approval(
    logger,
    context: PlanRunContext,
    cycle: int,
    summary: str,
    issue_ids: list[str],
    commits: list[str],
) -> None:
    """Record the empty worklist that authorizes completion after deterministic gates."""
    _atomic_json(
        Path(context.worklist_path).with_name("review-worklist.json"),
        {
            "version": 1,
            "plan_digest": context.plan_digest,
            "cycle": cycle + 1,
            "status": "approved",
            "summary": summary,
            "issues": [],
            "resolved_issues": [
                {"id": issue_id, "status": "done", "commit_sha": commits[index]}
                for index, issue_id in enumerate(issue_ids)
            ],
        },
    )
    logger.info("review cycle %d approved the candidate", cycle + 1)


@blueprint.node
def complete_review_issues(
    logger,
    context: PlanRunContext,
    plan: PreparedPlan,
    commits: list[str],
    expected_head: str,
) -> ReviewFixResult:
    """Close one issue worklist only after every fix is present at origin."""
    repository.assert_clean_at(context, expected_head, expected_head)
    if len(commits) != len(plan.tasks):
        raise WorkflowFailed("review issue batch completed without one commit per issue")
    logger.info("completed %d review issues at %s", len(commits), expected_head[:12])
    return ReviewFixResult(
        status="fixed",
        issue_count=len(plan.tasks),
        issue_ids=[issue.id for issue in plan.tasks],
        commits=commits,
        final_commit=expected_head,
    )


__all__ = [
    "check_review_turn",
    "complete_review_issues",
    "prepare_review_issues",
    "project_review_approval",
    "project_review_progress",
    "validate_review_report",
]