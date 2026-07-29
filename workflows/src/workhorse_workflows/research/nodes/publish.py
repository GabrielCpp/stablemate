"""Getting the gate's work off this machine: commit onto the result branch and push.

Ported from `base-library/workflows/research/scripts/publish.py`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import checkout, commit_all, push_to_origin, set_identity
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import PublishResult


@blueprint.node
def publish_results(
    logger: logging.Logger,
    repo_dir: str,
    result_branch: str = "research/auto",
    program_dir: str = "",
) -> PublishResult:
    """Commit whatever the gate produced onto the result branch and push it.

    Every failure here is soft: an unpushed branch is still a branch on disk, and
    losing a week of gate work because a remote was unreachable would be the wrong
    trade for an unattended run.
    """
    if not repo_dir:
        raise WorkflowFailed("publish_results needs a repo_dir")

    if program_dir:
        program_label = Path(program_dir).name
    else:
        program_label = (
            result_branch.rsplit("/", 1)[0] if "/" in result_branch else result_branch
        )
    program_label = program_label or result_branch

    set_identity(repo_dir, "Research Agent", "research-agent@local")
    checkout(repo_dir, result_branch, reset=True)
    if not commit_all(repo_dir, f"{program_label}: automated gate update"):
        logger.info("no changes to commit")
        return PublishResult(published=False, result_branch=result_branch)
    if push_to_origin(repo_dir, result_branch, force_with_lease=True):
        return PublishResult(published=True, result_branch=result_branch)
    logger.warning(
        "push failed — edits remain on local branch %s only", result_branch
    )
    return PublishResult(
        published=False, result_branch=result_branch, status="push_failed"
    )


__all__ = ["publish_results"]
