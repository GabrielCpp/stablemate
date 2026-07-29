"""Getting a working tree: clone the repo the program lives in, or adopt one.

Ported from `base-library/workflows/research/scripts/setup.py`.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import allow_all_directories, clone, fetch_reset
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import RepoSetup


@blueprint.node
def clone_repo(logger: logging.Logger) -> RepoSetup:
    """Check out the repo the program lives in, or adopt the one already there.

    In-place mode wins: when the launcher already put a checkout in front of us
    (`AGENT_REPO_DIR`), cloning would discard uncommitted work and point the run at
    the wrong tree.
    """
    repo_dir_env = os.environ.get("AGENT_REPO_DIR") or os.environ.get("HRNET_REPO_DIR")
    if repo_dir_env:
        allow_all_directories()
        logger.info("in-place mode: using existing repo at %s (no clone)", repo_dir_env)
        return RepoSetup(repo_dir=repo_dir_env)

    # Env before argv so a compose override can redirect the clone source without
    # touching the workflow.
    repo_url = os.environ.get("REPO_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not repo_url:
        raise WorkflowFailed(
            "no repo to work on: set REPO_URL (or AGENT_REPO_DIR for in-place mode)"
        )
    repo_branch = os.environ.get("REPO_BRANCH") or (
        sys.argv[2] if len(sys.argv) > 2 else "main"
    )

    os.environ.setdefault("GIT_SSH_COMMAND", "ssh -o StrictHostKeyChecking=accept-new")
    # A bind-mounted source repo is owned by the host user; git refuses it as
    # "dubious ownership" without this.
    allow_all_directories()

    workspace = Path("/workspace")
    repo_dir = workspace / Path(repo_url).name.removesuffix(".git")
    workspace.mkdir(parents=True, exist_ok=True)

    if (repo_dir / ".git").is_dir():
        logger.info("repo already present at %s — fetching %s", repo_dir, repo_branch)
        fetch_reset(repo_dir, repo_branch)
    else:
        logger.info("cloning %s (%s) into %s", repo_url, repo_branch, repo_dir)
        clone(repo_url, repo_dir, branch=repo_branch, single_branch=True)

    synced = subprocess.run(
        ["uv", "sync", "--no-sources"],
        cwd=str(repo_dir),
        stdout=sys.stderr,
        stderr=sys.stderr,
        text=True,
        check=False,
    )
    if synced.returncode != 0:
        logger.warning("'uv sync --no-sources' failed; agent must resolve deps")
    return RepoSetup(repo_dir=str(repo_dir))


__all__ = ["clone_repo"]
