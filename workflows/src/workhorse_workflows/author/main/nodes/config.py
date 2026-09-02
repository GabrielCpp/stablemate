"""What the run works on.

Ported from `base-library/workflows/author/scripts/load-config.py`.

`load_config` drops the script's `try: import yaml / except ImportError: yaml = None`
guard: PyYAML is a declared dependency of this distribution, so an absent one is a broken
install rather than a condition to degrade through. A *missing or unparseable*
`agents.yml` still falls back to the conventions, which is the case the guard actually
covered in practice.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.roadmap import approved_roadmap
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


@blueprint.node
def load_config(
    logger: logging.Logger,
    repo_dir: str = "",
    mode: str = "epic",
) -> Config:
    """Resolve the author's paths and prove the selected intake exists.

    Every path here is ostler's answer, read from `docRoots:` — the run has no parameter that
    can move one, because a run that moved one wrote documents the rest of the toolchain
    could not find. What is left as an input is the repo and the mode.

    The feature book is read-only grounding for author prompts. New visual references are
    story-local mockups; author never creates a feature inventory or registers mockups in one.
    """
    root = survey_repo_root(repo_dir)
    backlog = paths.backlog_file(root)
    epics_dir = paths.epics_dir(root)
    roadmap = approved_roadmap(root) if mode == "epic" else ""

    backlog_path = (root / backlog).resolve()
    if mode in {"story", "story-edit", "epic-edit"} and not backlog_path.is_file():
        logger.warning("backlog file not found: %s", backlog_path)
        raise WorkflowFailed(
            f"backlog file not found: {backlog_path}\n"
            f"Create {backlog} (a markdown bullet list of features) before running the author "
            f"workflow, or point `docRoots: backlog:` at the list this repo keeps."
        )

    data = _template(root)
    features_dir = paths.features_dir(root)

    # Best-effort layer list, a hint for layer-aware prompts only: the prompts use
    # isUsingInstruction() at install time for the authoritative selection.
    layers = [
        str(li["skill"])
        for li in (data.get("localInstructions") or [])
        if isinstance(li, dict) and li.get("skill")
    ]

    logger.info(
        "loaded config for %s (features_dir=%s, %d layer(s))", root, features_dir, len(layers)
    )
    return Config(
        repo_root=str(root),
        backlog_path=backlog,
        roadmap_path=roadmap,
        epics_dir=epics_dir,
        features_dir=str(features_dir),
        layers=layers,
    )


__all__ = ["load_config"]
