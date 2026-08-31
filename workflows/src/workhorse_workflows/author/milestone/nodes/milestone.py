"""Deterministic boundaries around milestone authoring."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.milestone.nodes._blueprint import blueprint
from workhorse_workflows.author.milestone.schemas import MilestoneContext, MilestoneValidation
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.roadmap import approved_roadmap


def _epic_fingerprints(okf: Ostler) -> dict[str, str]:
    return {
        epic.name: hashlib.sha256(epic.epic_md.read_bytes()).hexdigest()
        for epic in okf.graph.epics
        if epic.epic_md is not None
    }


def _milestone_fingerprints(okf: Ostler, root: Path) -> dict[str, str]:
    return {
        milestone.path.relative_to(root).as_posix(): hashlib.sha256(
            milestone.path.read_bytes()
        ).hexdigest()
        for milestone in okf.graph.milestones
    }


@blueprint.node
def prepare_milestone(
    logger: logging.Logger,
    repo_dir: str = "",
) -> MilestoneContext:
    """Validate intake and snapshot every epic so this stage cannot create or edit one."""
    root = survey_repo_root(repo_dir)
    roadmap = approved_roadmap(root)
    okf = Ostler(root)
    matches = [m for m in okf.graph.milestones if roadmap in m.source_items]
    if len(matches) > 1:
        raise WorkflowFailed(f"roadmap '{roadmap}' already sources {len(matches)} milestones")
    milestone = matches[0] if matches else None
    logger.info("prepared roadmap %s for milestone authoring", roadmap)
    return MilestoneContext(
        repo_root=str(root),
        roadmap=roadmap,
        epics_dir=paths.epics_dir(root),
        milestone_path=(milestone.path.relative_to(root).as_posix() if milestone else ""),
        milestone_epics=list(milestone.epics) if milestone else [],
        milestone_fingerprints=_milestone_fingerprints(okf, root),
        epic_fingerprints=_epic_fingerprints(okf),
    )


@blueprint.node
def validate_milestone(
    logger: logging.Logger,
    context: MilestoneContext,
) -> MilestoneValidation:
    """Require one roadmap milestone and prove the turn did not touch any epic document."""
    root = Path(context.repo_root)
    okf = Ostler(root)
    matches = [m for m in okf.graph.milestones if context.roadmap in m.source_items]
    errors: list[str] = []
    milestone_path = ""
    if len(matches) != 1:
        errors.append(
            f"roadmap '{context.roadmap}' must source exactly one milestone; found {len(matches)}"
        )
    else:
        milestone = matches[0]
        milestone_path = milestone.path.relative_to(root).as_posix()
        if milestone.source_items != [context.roadmap]:
            errors.append("the milestone must list the roadmap as its sole sourceItems value")
        if milestone.epics != context.milestone_epics:
            errors.append("the milestone flow must not add, remove, or reorder epics")
    current_milestones = _milestone_fingerprints(okf, root)
    allowed_paths = set(context.milestone_fingerprints)
    if milestone_path:
        allowed_paths.add(milestone_path)
    if set(current_milestones) != allowed_paths:
        errors.append("the milestone flow must create or reuse only the roadmap milestone")
    for path, fingerprint in context.milestone_fingerprints.items():
        if path == context.milestone_path:
            continue
        if current_milestones.get(path) != fingerprint:
            errors.append(f"the milestone flow must not edit unrelated milestone '{path}'")
    if _epic_fingerprints(okf) != context.epic_fingerprints:
        errors.append("the milestone flow must not create or edit epic documents")
    logger.info("milestone validation: %d error(s)", len(errors))
    return MilestoneValidation(
        ok=not errors,
        milestone_path=milestone_path,
        reused=bool(context.milestone_path),
        errors="\n".join(errors),
    )


__all__ = ["prepare_milestone", "validate_milestone"]
