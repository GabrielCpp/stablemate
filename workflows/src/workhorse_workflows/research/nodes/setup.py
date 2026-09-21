"""Getting a working tree: clone the repo the program lives in, or adopt one."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import allow_all_directories, clone, fetch_reset
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import RepoSetup

SSH_COMMAND = "ssh -o StrictHostKeyChecking=accept-new"


@blueprint.node
def clone_repo(
    logger: logging.Logger,
    repo_dir: str = "",
    repo_url: str = "",
    repo_branch: str = "main",
    workspace_root: str = "/workspace",
) -> RepoSetup:
    """Check out the repo the program lives in, or adopt the one already there."""
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
