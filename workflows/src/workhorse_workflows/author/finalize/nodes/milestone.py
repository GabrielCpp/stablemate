"""Validate and advance the approved milestone finalize delivers."""
from __future__ import annotations

import logging
import re

from ostler import Ostler, doctor, markdown
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.finalize.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import agents_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, MilestoneStatus


@blueprint.node
def validate_milestone_epics(
    logger: logging.Logger,
    milestone: str,
    repo_dir: str = "",
) -> Defects:
    """Prove the milestone lists its epics by id, and that it, they and their stories meet the authoring contract."""
    root = agents_repo_root(repo_dir)
    graph = Ostler(root).graph
    matches = [
        m for m in graph.milestones
        if m.path.relative_to(root).as_posix() == milestone
    ]
    errors: list[str] = []
    if len(matches) != 1:
        errors.append(f"milestone '{milestone}' was not found")
    elif not matches[0].epics:
        errors.append(f"milestone '{matches[0].name}' lists no epics")
    else:
        report = doctor.run(graph, check_schema=False, milestone_filter=matches[0].name)
        errors.extend(
            f"[{finding.code}] ({finding.epic or finding.ref}) {finding.message}"
            for finding in report.findings
            if finding.severity == "error"
        )
    logger.info("milestone epic validation: %d error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node
def mark_milestone_authored(
    logger: logging.Logger,
    milestone: str,
    repo_dir: str = "",
) -> MilestoneStatus:
    """Advance one validated milestone from approved to authored, idempotently."""
    path = agents_repo_root(repo_dir) / milestone
    text = path.read_text(encoding="utf-8")
    document = markdown.split(text)
    status = str((document.frontmatter or {}).get("status", ""))
    if status == "authored":
        return MilestoneStatus(path=milestone, status=status)
    if status != "approved":
        raise WorkflowFailed(
            f"milestone '{milestone}' must still be approved before Author can mark it authored; "
            f"got {status or '<missing>'}"
        )
    front, marker, body = text.removeprefix("---\n").partition("\n---")
    if not marker:
        raise WorkflowFailed(f"milestone '{milestone}' has no closed YAML frontmatter")
    updated, replacements = re.subn(
        r"(?m)^status\s*:.*$", "status: authored", front, count=1
    )
    if replacements != 1:
        raise WorkflowFailed(f"milestone '{milestone}' has no status field to advance")
    path.write_text(f"---\n{updated}{marker}{body}", encoding="utf-8")
    logger.info("marked milestone %s authored", milestone)
    return MilestoneStatus(path=milestone, status="authored")


__all__ = ["mark_milestone_authored", "validate_milestone_epics"]
