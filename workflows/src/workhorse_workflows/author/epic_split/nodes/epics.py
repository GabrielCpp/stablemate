"""Deterministic intake and output validation for epic splitting."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from ostler import Ostler, markdown, registry
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.epic_split.nodes._blueprint import blueprint
from workhorse_workflows.author.epic_split.schemas import EpicSplitContext, EpicSplitValidation
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.roadmap import approved_roadmap


def _fingerprints(okf: Ostler) -> dict[str, str]:
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


def _seed_ids(okf: Ostler) -> dict[str, list[str]]:
    return {epic.name: [seed.id for seed in epic.seeds] for epic in okf.graph.epics}


def _story_slugs(okf: Ostler) -> dict[str, list[str]]:
    return {epic.name: [story.slug for story in epic.stories] for epic in okf.graph.epics}


def _skeleton_error(path: Path) -> str:
    document = markdown.split(path.read_text(encoding="utf-8"))
    lines = [line.rstrip() for line in document.body.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
    remainder = [line for line in lines if line.strip()]
    if remainder != ["## Seeds", "## Stories"]:
        return f"new epic '{path.parent.name}' contains authored prose or non-skeleton sections"
    return ""


@blueprint.node
def prepare_epic_split(
    logger: logging.Logger,
    roadmap: str,
    epics_dir: str = "",
    repo_dir: str = "",
) -> EpicSplitContext:
    """Require the milestone stage's unique roadmap-owned document and snapshot content."""
    root = survey_repo_root(repo_dir)
    roadmap = approved_roadmap(root, roadmap)
    okf = Ostler(root)
    matches = [m for m in okf.graph.milestones if roadmap in m.source_items]
    if len(matches) != 1 or matches[0].source_items != [roadmap]:
        raise WorkflowFailed(
            f"roadmap '{roadmap}' must already source exactly one milestone with no other sources"
        )
    milestone = matches[0]
    logger.info("prepared milestone %s for epic splitting", milestone.name)
    return EpicSplitContext(
        repo_root=str(root),
        roadmap=roadmap,
        epics_dir=paths.epics_dir(root, epics_dir),
        milestone_path=milestone.path.relative_to(root).as_posix(),
        existing_epics=[epic.name for epic in okf.graph.epics],
        milestone_fingerprints=_milestone_fingerprints(okf, root),
        epic_fingerprints=_fingerprints(okf),
        seed_ids=_seed_ids(okf),
        story_slugs=_story_slugs(okf),
    )


@blueprint.node
def validate_epic_split(
    logger: logging.Logger,
    context: EpicSplitContext,
) -> EpicSplitValidation:
    """Validate an ordered, non-empty epic list without accepting prose, seeds, or stories."""
    root = Path(context.repo_root)
    okf = Ostler(root)
    matches = [m for m in okf.graph.milestones if context.roadmap in m.source_items]
    errors: list[str] = []
    ordered: list[str] = []
    if len(matches) != 1:
        errors.append(
            f"roadmap '{context.roadmap}' must source exactly one milestone; found {len(matches)}"
        )
    else:
        milestone = matches[0]
        if milestone.source_items != [context.roadmap]:
            errors.append("the milestone must list the roadmap as its sole sourceItems value")
        ordered = [str(epic).strip() for epic in milestone.epics if str(epic).strip()]
        if not ordered:
            errors.append("the milestone must contain a non-empty ordered epic list")
        normalized = [registry.epic_slug(epic) for epic in ordered]
        if len(set(normalized)) != len(normalized):
            errors.append("the milestone epic list contains duplicates")
        available = {registry.epic_slug(epic.name): epic for epic in okf.graph.epics}
        for name, slug in zip(ordered, normalized, strict=True):
            if slug not in available:
                errors.append(f"milestone epic '{name}' has no epic skeleton")

    current_seeds = _seed_ids(okf)
    current_stories = _story_slugs(okf)
    for epic, seeds in context.seed_ids.items():
        if current_seeds.get(epic) != seeds:
            errors.append(f"the epic-split flow must not create, remove, or edit seeds in '{epic}'")
    for epic, stories in context.story_slugs.items():
        if current_stories.get(epic) != stories:
            errors.append(
                f"the epic-split flow must not create, remove, or edit stories in '{epic}'"
            )
    current_fingerprints = _fingerprints(okf)
    current_milestones = _milestone_fingerprints(okf, root)
    if set(current_milestones) != set(context.milestone_fingerprints):
        errors.append("the epic-split flow must not create or remove milestone documents")
    for path, fingerprint in context.milestone_fingerprints.items():
        if path == context.milestone_path:
            continue
        if current_milestones.get(path) != fingerprint:
            errors.append(f"the epic-split flow must not edit unrelated milestone '{path}'")
    for epic, fingerprint in context.epic_fingerprints.items():
        if current_fingerprints.get(epic) != fingerprint:
            errors.append(f"the epic-split flow must not edit existing epic '{epic}'")
    for epic in okf.graph.epics:
        if epic.name in context.existing_epics or epic.epic_md is None:
            continue
        if current_seeds.get(epic.name):
            errors.append(f"new epic '{epic.name}' must not contain seeds")
        if current_stories.get(epic.name):
            errors.append(f"new epic '{epic.name}' must not contain stories")
        error = _skeleton_error(epic.epic_md)
        if error:
            errors.append(error)

    logger.info("epic split validation: %d error(s)", len(errors))
    return EpicSplitValidation(
        ok=not errors,
        milestone_path=matches[0].path.relative_to(root).as_posix() if len(matches) == 1 else "",
        ordered_epics=ordered,
        errors="\n".join(errors),
    )


__all__ = ["prepare_epic_split", "validate_epic_split"]
