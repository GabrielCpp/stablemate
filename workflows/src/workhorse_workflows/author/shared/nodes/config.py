"""What the run works on."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from ostler.milestones import MOCKUPS_DIR, MilestoneSelectionError
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Config
from workhorse_workflows.kit.manifest import read_manifest

GRILLS_DIR = "grills"
PM_LEDGER_FILE = "pm.md"


def layers(root: Path) -> list[str]:
    """The skill each `localInstructions` entry names, in order; none when the manifest is unreadable."""
    manifest = read_manifest(root)
    if manifest is None:
        return []
    return [entry.skill for entry in manifest.localInstructions if entry.skill]


def approved_milestone_path(root: Path) -> str:
    """The docs-root-relative path of the one approved milestone, or stop before a turn."""
    okf = Ostler(root)
    try:
        milestone = okf.approved_milestone()
    except MilestoneSelectionError as exc:
        raise WorkflowFailed(f"authoring requires exactly one approved milestone: {exc}") from exc
    errors = [f for f in okf.milestone_readiness(milestone.name) if f.severity == "error"]
    if errors:
        listed = "\n".join(f"- [{f.code}] {f.message}" for f in errors)
        raise WorkflowFailed(
            f"milestone '{milestone.name}' is not ready to author from, fix it until "
            f"`ostler doctor` reports no milestone finding:\n{listed}"
        )
    return milestone.path.resolve().relative_to(root.resolve()).as_posix()


def pm_ledger_path(folder: Path) -> str:
    """The absolute `grills/pm.md` the PM keeps beside the milestone at *folder*."""
    return str(folder / GRILLS_DIR / PM_LEDGER_FILE)


def approved_milestone_folder(root: Path) -> Path | None:
    """The absolute folder of the approved milestone, or nothing when none is."""
    try:
        return Ostler(root).approved_milestone().path.parent.resolve()
    except MilestoneSelectionError:
        return None


@blueprint.node
def load_config(
    logger: logging.Logger,
    repo_dir: str = "",
    mode: str = "epic",
) -> Config:
    """Resolve the author's paths and prove the selected intake exists."""
    root = survey_repo_root(repo_dir)
    epics_dir = paths.epics_dir(root)
    milestone = approved_milestone_path(root) if mode == "epic" else ""

    folder = approved_milestone_folder(root)
    services_dir = paths.services_dir(root)
    layer_skills = layers(root)

    logger.info(
        "loaded config for %s (services_dir=%s, %d layer(s))", root, services_dir, len(layer_skills)
    )
    return Config(
        repo_root=str(root),
        milestone_path=milestone,
        milestone_mockups_dir=str(folder / MOCKUPS_DIR) if folder is not None else "",
        milestone_dir=str(folder) if folder is not None else "",
        pm_ledger=pm_ledger_path(folder) if folder is not None else "",
        epics_dir=epics_dir,
        services_dir=str(services_dir),
        layers=layer_skills,
    )


__all__ = ["load_config"]
