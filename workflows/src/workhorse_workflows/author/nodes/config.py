"""What the run works on, and the branch it works on it in.

Ported from `base-library/workflows/author/scripts/{load-config,branch-author}.py`.

`load_config` drops the script's `try: import yaml / except ImportError: yaml = None`
guard: PyYAML is a declared dependency of this distribution, so an absent one is a broken
install rather than a condition to degrade through. A *missing or unparseable*
`agents.yml` still falls back to the conventions, which is the case the guard actually
covered in practice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse.scriptutil import find_repo_root
from workhorse_workflows.author.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Branches, Config
from workhorse_workflows.kit import active_branch, checkout, local_branch_exists


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
    backlog: str = "",
    epics_dir: str = "",
    repo_dir: str = "",
) -> Config:
    """Resolve the author's paths and prove the backlog exists.

    A missing backlog fails the run here rather than letting the decomposition agent
    hallucinate scope from an empty file. Everything else is a convention default a repo
    may override under `template.*` in `agents.yml`; the base workflow never branches on
    those values, it only passes them to the prompts.

    The three convention paths stay **inert until the file they name exists**, which is
    what makes them safe to default: a greenfield repo with no OKF book is simply not
    asked to cite one. `surface_manifest` is the one picked up by presence — an unpinned
    manifest prefers the surveyor's `unit-manifest.json` when a survey has run.
    """
    root = survey_repo_root(repo_dir)
    backlog = paths.backlog_file(root, backlog)
    epics_dir = paths.epics_dir(root, epics_dir)
    backlog_path = (root / backlog).resolve()
    if not backlog_path.is_file():
        logger.warning("backlog file not found: %s", backlog_path)
        raise WorkflowFailed(
            f"backlog file not found: {backlog_path}\n"
            f"Create {backlog} (a markdown bullet list of features) before running the author "
            f"workflow, or pass --params '{{\"backlog\":\"<path>\"}}'."
        )

    data = _template(root)
    template = data.get("template") or {}

    features_dir = paths.features_dir(root, template.get("features_dir") or "")

    surface_manifest = template.get("surface_manifest") or ""
    if not surface_manifest:
        survey_manifest = "docs/survey/unit-manifest.json"
        surface_manifest = (
            survey_manifest if (root / survey_manifest).is_file()
            else f"{features_dir}/inventory.json"
        )
    mockup_dir = template.get("mockup_dir") or "docs/design"

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
        epics_dir=epics_dir,
        surface_manifest=str(surface_manifest),
        features_dir=str(features_dir),
        mockup_dir=str(mockup_dir),
        layers=layers,
    )


def _base_branch(author_branch: str, cwd: Path, configured: str = "") -> str:
    """The branch the run forked from — what a PR would target.

    The branch the repo is sitting on wins, unless that is already the author branch (a
    resume). Otherwise the first of `configured`, `develop`, `main`, `master` that
    exists locally, and failing all of those the configured name or `main`.

    `configured` is the run's `base_branch` input, carried down from the workflow rather
    than read from the environment — the branch a run targets is an input, so it has to be
    visible in the checkpoint and overridable by a caller.
    """
    current = active_branch(cwd)
    if current and current != author_branch:
        return current

    configured = configured.strip()
    for candidate in [configured, "develop", "main", "master"]:
        if candidate and candidate != author_branch and local_branch_exists(cwd, candidate):
            return candidate
    return configured or "main"


def _run_slug(run_dir: str) -> str:
    """The run directory's own name, which is stable for the life of the run.

    Deriving the branch from the run dir rather than from a fresh timestamp is what makes
    this idempotent: a resume after a mid-run kill checks out the SAME branch instead of
    abandoning a partial one.
    """
    if run_dir:
        return Path(run_dir).name
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@blueprint.node
def branch_author(
    logger: logging.Logger,
    run_dir: str = "",
    mode: str = "epic",
    repo_dir: str = "",
    base_branch: str = "",
) -> Branches:
    """Cut (or re-check-out) the one branch this run works on.

    One branch per run. A blank `author_branch` in the return is the "carry on where we
    are" answer, not a failure: it is what a repo with no `.git` gets, and what a failed
    checkout gets. `mode` reaches only a log line — it is here because the script took it.
    """
    repo_root = find_repo_root(repo_dir)
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — skipping branch creation", repo_root)
        return Branches(base_branch="main", author_branch="")

    branch = f"author/{_run_slug(run_dir)}"
    base_branch = _base_branch(branch, repo_root, base_branch)

    if local_branch_exists(repo_root, branch):
        checkout(repo_root, branch)
        logger.info("checked out existing %s", branch)
    elif not checkout(repo_root, branch, create=True):
        logger.warning("cannot create branch %s", branch)
        return Branches(base_branch=base_branch, author_branch="")
    else:
        logger.info("created %s (mode=%s)", branch, mode)

    return Branches(base_branch=base_branch, author_branch=branch)


__all__ = ["branch_author", "load_config"]
