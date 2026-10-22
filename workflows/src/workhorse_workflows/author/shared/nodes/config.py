"""What the run works on."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from ostler import Ostler
from ostler.milestones import MilestoneSelectionError
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Config


def _template(root: Path) -> dict:
    """`agents.yml` as a dict, or an empty one — an unreadable config is not a failure."""
    cfg_path = root / "agents.yml"
    if not cfg_path.is_file():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


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


@blueprint.node
def load_config(
    logger: logging.Logger,
    repo_dir: str = "",
    mode: str = "epic",
) -> Config:
    """Resolve the author's paths and prove the selected intake exists."""
    root = survey_repo_root(repo_dir)
    backlog = paths.backlog_file(root)
    epics_dir = paths.epics_dir(root)
    milestone = approved_milestone_path(root) if mode == "epic" else ""

    backlog_path = (root / backlog).resolve()
    if mode in {"story", "story-edit", "epic-edit"} and not backlog_path.is_file():
        logger.warning("backlog file not found: %s", backlog_path)
        raise WorkflowFailed(
            f"backlog file not found: {backlog_path}\n"
            f"Create {backlog} (a markdown bullet list of features) before running the author "
            f"workflow."
        )

    data = _template(root)
    services_dir = paths.services_dir(root)

    layers = [
        str(li["skill"])
        for li in (data.get("localInstructions") or [])
        if isinstance(li, dict) and li.get("skill")
    ]

    logger.info(
        "loaded config for %s (services_dir=%s, %d layer(s))", root, services_dir, len(layers)
    )
    return Config(
        repo_root=str(root),
        backlog_path=backlog,
        milestone_path=milestone,
        epics_dir=epics_dir,
        services_dir=str(services_dir),
        layers=layers,
    )


__all__ = ["load_config"]
