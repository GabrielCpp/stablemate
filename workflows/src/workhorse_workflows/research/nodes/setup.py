"""Getting a working tree: clone the repo the program lives in, or adopt one.

Ported from `base-library/workflows/research/scripts/setup.py`.

The script read `AGENT_REPO_DIR`/`HRNET_REPO_DIR`, `REPO_URL` and `REPO_BRANCH` from the
environment, and `GIT_SSH_COMMAND` it *wrote* there. All four are arguments now, per the
rule in `workflows/README.md`: a run's inputs have to be visible in the checkpoint and
overridable by a caller, which an ambient variable is not.

That reshuffles the clone-vs-adopt ladder, and deliberately. `repo_dir` always resolves —
the CLI defaults it to the launch directory — so an in-place-wins ladder keyed on it would
make the clone branch unreachable, which is what the environment version had quietly
become (`workhorse.cli.run` `setdefault`s `AGENT_REPO_DIR` before any node sees it). The
explicit ask therefore wins instead: a `repo_url` means *clone*, and with none the run
adopts the tree it was pointed at.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import allow_all_directories, clone, fetch_reset
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import RepoSetup

#: What git is told about unknown hosts when this node clones. Passed into the clone's
#: own environment rather than exported into the process, so it cannot leak into an
#: unrelated node's git call.
SSH_COMMAND = "ssh -o StrictHostKeyChecking=accept-new"


@blueprint.node
def clone_repo(
    logger: logging.Logger,
    repo_dir: str = "",
    repo_url: str = "",
    repo_branch: str = "main",
    workspace_root: str = "/workspace",
) -> RepoSetup:
    """Check out the repo the program lives in, or adopt the one already there.

    No `repo_url` means adopt: the launcher already put a checkout in front of us, and
    cloning would discard uncommitted work and point the run at the wrong tree.
    """
    if not repo_url:
        if not repo_dir:
            raise WorkflowFailed(
                "no repo to work on: pass --params '{\"repo_url\": \"<url>\"}' to clone, "
                "or '{\"repo_dir\": \"<path>\"}' to work in place"
            )
        allow_all_directories()
        logger.info("in-place mode: using existing repo at %s (no clone)", repo_dir)
        return RepoSetup(repo_dir=repo_dir)

    repo_branch = repo_branch or "main"
    # A bind-mounted source repo is owned by the host user; git refuses it as
    # "dubious ownership" without this.
    allow_all_directories()

    workspace = Path(workspace_root)
    repo_path = workspace / Path(repo_url).name.removesuffix(".git")
    workspace.mkdir(parents=True, exist_ok=True)

    if (repo_path / ".git").is_dir():
        logger.info("repo already present at %s — fetching %s", repo_path, repo_branch)
        fetch_reset(repo_path, repo_branch)
    else:
        logger.info("cloning %s (%s) into %s", repo_url, repo_branch, repo_path)
        clone(repo_url, repo_path, branch=repo_branch, single_branch=True, ssh_command=SSH_COMMAND)

    synced = subprocess.run(
        ["uv", "sync", "--no-sources"],
        cwd=str(repo_path),
        stdout=sys.stderr,
        stderr=sys.stderr,
        text=True,
        check=False,
    )
    if synced.returncode != 0:
        logger.warning("'uv sync --no-sources' failed; agent must resolve deps")
    return RepoSetup(repo_dir=str(repo_path))


__all__ = ["SSH_COMMAND", "clone_repo"]
