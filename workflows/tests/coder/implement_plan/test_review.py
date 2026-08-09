"""Semantic review verdict, issue validation, and worklist authority tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed

from coder.implement_plan._support import _context, _issue, _prepared, _review, _task
from workhorse_workflows.coder.implement_plan.review import (
    prepare_review_issues,
    project_review_progress,
    validate_review_report,
)
from workhorse_workflows.coder.implement_plan.schemas import PlanReview


def test_blank_review_verdict_fails_closed(logger: Any) -> None:
    with pytest.raises(WorkflowFailed, match="no status"):
        validate_review_report(logger, PlanReview())


def test_approval_requires_a_substantive_summary(logger: Any) -> None:
    with pytest.raises(WorkflowFailed, match="substantive summary"):
        validate_review_report(logger, PlanReview(status="approved", summary="  "))


def test_approval_cannot_hide_actionable_issues(logger: Any) -> None:
    report = PlanReview.model_validate(
        {"status": "approved", "summary": "contradictory", "issues": [_issue("hidden", "src/a.py")]}
    )

    with pytest.raises(WorkflowFailed, match="approval while listing issues"):
        validate_review_report(logger, report)


def test_issue_verdict_requires_a_worklist(logger: Any) -> None:
    report = PlanReview(status="issues", summary="missing packets")

    with pytest.raises(WorkflowFailed, match="without an issue worklist"):
        validate_review_report(logger, report)


def test_review_issue_requires_concrete_evidence(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    root_plan = _prepared(context, logger, _task("root", "src/root.py"))
    issue = _issue("unsupported", "src/a.py", finding="")

    with pytest.raises(WorkflowFailed, match="needs concrete evidence"):
        prepare_review_issues(
            logger,
            PlanReview.model_validate(_review(issue)),
            context,
            root_plan,
            0,
        )


@pytest.mark.parametrize("issue_id", ["", "trailing-", "Uppercase", "x" * 49])
def test_review_issue_requires_an_original_bounded_id(
    tmp_path: Path,
    repo: Path,
    logger: Any,
    issue_id: str,
) -> None:
    context = _context(tmp_path, repo, logger)
    root_plan = _prepared(context, logger, _task("root", "src/root.py"))
    issue = _issue("temporary", "src/a.py") | {"id": issue_id}

    with pytest.raises(WorkflowFailed, match="review issue id"):
        prepare_review_issues(
            logger,
            PlanReview.model_validate(_review(issue)),
            context,
            root_plan,
            0,
        )


def test_review_issue_dependencies_must_stay_in_the_same_report(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    root_plan = _prepared(context, logger, _task("root", "src/root.py"))
    issue = _issue("dependent", "src/a.py") | {"depends_on": ["not-reported"]}

    with pytest.raises(WorkflowFailed, match="unknown dependencies"):
        prepare_review_issues(
            logger,
            PlanReview.model_validate(_review(issue)),
            context,
            root_plan,
            0,
        )


def test_tampered_review_projection_cannot_skip_checkpointed_issue(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    root_plan = _prepared(context, logger, _task("root", "src/root.py"))
    issue_plan = prepare_review_issues(
        logger,
        PlanReview.model_validate(_review(_issue("real", "src/value.py"))),
        context,
        root_plan,
        0,
    )
    project_review_progress(logger, context, issue_plan, 0, 0, [])
    path = Path(context.worklist_path).with_name("review-worklist.json")
    tampered = json.loads(path.read_text())
    tampered["status"] = "approved"
    tampered["issues"][0]["status"] = "done"
    tampered["issues"][0]["payload"]["issue"]["paths"] = ["."]
    path.write_text(json.dumps(tampered), encoding="utf-8")

    project_review_progress(logger, context, issue_plan, 0, 0, [])

    rebuilt = json.loads(path.read_text())
    assert rebuilt["status"] == "active"
    assert rebuilt["issues"][0]["status"] == "active"
    assert rebuilt["issues"][0]["payload"]["issue"]["paths"] == ["src/value.py"]