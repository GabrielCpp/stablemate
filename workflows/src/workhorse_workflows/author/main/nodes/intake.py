"""Validate and advance the durable inputs Author consumes."""
from __future__ import annotations

import logging
import re

from ostler import Ostler, markdown
from ostler.result import Result
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, RoadmapStatus


@blueprint.node
def adopt_backlog(
    logger: logging.Logger,
    backlog: str = "",
    repo_dir: str = "",
) -> Result:
    """Mint ids for every unnamed backlog bullet before decomposition or story lookup."""
    result = Ostler(survey_repo_root(repo_dir)).backlog_adopt(backlog)
    if not result.ok:
        raise WorkflowFailed(result.message)
    logger.info(result.message)
    return result


@blueprint.node
def validate_roadmap_milestone(
    logger: logging.Logger,
    roadmap: str,
    repo_dir: str = "",
) -> Defects:
    """Prove the roadmap owns one non-empty, internally valid milestone subgraph."""
    okf = Ostler(survey_repo_root(repo_dir))
    milestones = okf.list("milestone")
    matches = [m for m in milestones if roadmap in (m.get("sourceItems") or [])]
    errors: list[str] = []
    if len(matches) != 1:
        errors.append(
            f"roadmap '{roadmap}' must source exactly one milestone; found {len(matches)}"
        )
    elif list(matches[0].get("sourceItems") or []) != [roadmap]:
        errors.append(
            f"milestone '{matches[0].get('name', '?')}' must list only roadmap '{roadmap}' "
            "in sourceItems"
        )
    elif not matches[0].get("epics"):
        errors.append(
            f"milestone '{matches[0].get('name', '?')}' sourced by '{roadmap}' has no epics"
        )
    else:
        for epic in matches[0].get("epics") or []:
            outcome = okf.doctor(epic=str(epic))
            if outcome.status == "invalid":
                errors.append(f"epic '{epic}' could not be validated: {outcome.message}")
                continue
            for finding in outcome.data.get("findings", []):
                if finding.get("severity") != "error":
                    continue
                code = finding.get("code", "unknown")
                message = finding.get("message", "planning graph defect")
                errors.append(f"[{code}] ({epic}) {message}")
    logger.info("roadmap milestone validation: %d error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node
def mark_roadmap_authored(
    logger: logging.Logger,
    roadmap: str,
    repo_dir: str = "",
) -> RoadmapStatus:
    """Advance one validated roadmap from approved to authored, idempotently."""
    path = survey_repo_root(repo_dir) / roadmap
    text = path.read_text(encoding="utf-8")
    document = markdown.split(text)
    status = str((document.frontmatter or {}).get("status", ""))
    if status == "authored":
        return RoadmapStatus(path=roadmap, status=status)
    if status != "approved":
        raise WorkflowFailed(
            f"roadmap '{roadmap}' must still be approved before Author can mark it authored; "
            f"got {status or '<missing>'}"
        )
    front, marker, body = text.removeprefix("---\n").partition("\n---")
    if not marker:
        raise WorkflowFailed(f"roadmap '{roadmap}' has no closed YAML frontmatter")
    updated, replacements = re.subn(
        r"(?m)^status\s*:.*$", "status: authored", front, count=1
    )
    if replacements != 1:
        raise WorkflowFailed(f"roadmap '{roadmap}' has no status field to advance")
    path.write_text(f"---\n{updated}{marker}{body}", encoding="utf-8")
    logger.info("marked roadmap %s authored", roadmap)
    return RoadmapStatus(path=roadmap, status="authored")


__all__ = ["adopt_backlog", "mark_roadmap_authored", "validate_roadmap_milestone"]
