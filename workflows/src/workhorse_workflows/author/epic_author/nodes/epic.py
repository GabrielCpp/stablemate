"""Resolve and validate one caller-selected epic through Ostler."""
from __future__ import annotations

import logging

from ostler import Ostler
from ostler.select import epic_by_name
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.epic_author.nodes._blueprint import blueprint
from workhorse_workflows.author.epic_author.schemas import EpicEvidence, EpicTarget
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root


@blueprint.node
def prepare_epic_target(
    logger: logging.Logger,
    epic: str,
    epics_dir: str = "",
    repo_dir: str = "",
) -> EpicTarget:
    """Resolve exactly the named epic; never substitute a worklist neighbor."""
    root = survey_repo_root(repo_dir)
    requested = epic.strip()
    if not requested:
        raise WorkflowFailed("an explicit epic is required")
    found = epic_by_name(Ostler(root).graph, requested)
    if found is None:
        raise WorkflowFailed(f"epic '{requested}' was not found")
    epic_dir = paths.epic_dir(root, found.name, epics_dir)
    logger.info("prepared explicit epic '%s'", found.name)
    return EpicTarget(
        epic=found.name,
        epic_dir=epic_dir,
        epic_path=f"{epic_dir}/epic.md",
    )


@blueprint.node
def validate_authored_epic(
    logger: logging.Logger,
    epic: str,
    epics_dir: str = "",
    repo_dir: str = "",
) -> EpicEvidence:
    """Apply the main worklist's documented-epic evidence to one explicit epic."""
    root = survey_repo_root(repo_dir)
    found = epic_by_name(Ostler(root).graph, epic)
    errors: list[str] = []
    if found is None:
        errors.append(f"epic '{epic}' was not found")
        epic_dir = paths.epic_dir(root, epic, epics_dir)
        epic_path = f"{epic_dir}/epic.md"
        seed_count = 0
    else:
        epic_dir = paths.epic_dir(root, found.name, epics_dir)
        epic_path = (
            found.epic_md.relative_to(root).as_posix()
            if found.epic_md is not None
            else f"{epic_dir}/epic.md"
        )
        seed_count = len(found.seeds)
        if found.epic_md is None:
            errors.append(f"epic '{found.name}' has no epic.md")
        if not found.seeds:
            errors.append(f"epic '{found.name}' has no researched seeds")
    logger.info("epic document validation: %d error(s)", len(errors))
    return EpicEvidence(
        ok=not errors,
        epic=found.name if found is not None else epic,
        epic_dir=epic_dir,
        epic_path=epic_path,
        seed_count=seed_count,
        errors="\n".join(errors),
    )


__all__ = ["prepare_epic_target", "validate_authored_epic"]
