#!/usr/bin/env python3
"""Clone the target repo into /workspace so the agent works against its own
clean checkout — never a host working tree.

Args:
    argv[1]  repo url    (e.g. git@github.com:<org>/<repo>.git)
    argv[2]  repo branch (default: main)

Outputs JSON: {"setup_result": {"repo_dir": "...", "status": "ok"}}
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import allow_all_directories, clone, fetch_reset


def _emit(repo_dir: str, status: str = "ok") -> None:
    print(json.dumps({"setup_result": {"repo_dir": repo_dir, "status": status}}))


def main(logger: logging.Logger) -> None:
    # Native in-place mode: when AGENT_REPO_DIR is set, operate directly on that
    # existing checkout instead of cloning into /workspace. Used by the generated
    # launcher's `*-native` target, which runs the controller on the host so the
    # agent edits and commits straight into the real repo (no Docker, no clone).
    # HRNET_REPO_DIR is accepted as a backward-compat alias for AGENT_REPO_DIR.
    repo_dir_env = os.environ.get("AGENT_REPO_DIR") or os.environ.get("HRNET_REPO_DIR")
    if repo_dir_env:
        allow_all_directories()
        logger.info("in-place mode: using existing repo at %s (no clone)", repo_dir_env)
        _emit(repo_dir_env)
        return

    # Env wins over args so a compose override can redirect the clone source (e.g. to
    # a read-only bind mount of a local repo) without editing the committed workflow.
    repo_url = os.environ.get("REPO_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not repo_url:
        logger.error("repo url required")
        sys.exit(1)
    repo_branch = os.environ.get("REPO_BRANCH") or (sys.argv[2] if len(sys.argv) > 2 else "main")

    # Accept GitHub's host key non-interactively when cloning over SSH (no-op for a
    # local path source).
    os.environ.setdefault("GIT_SSH_COMMAND", "ssh -o StrictHostKeyChecking=accept-new")

    # A local bind-mounted source repo is owned by the host user, not the container's
    # `nobody`; git refuses such repos by default ("dubious ownership"). Trust them —
    # this container is disposable and isolated.
    allow_all_directories()

    workspace = Path("/workspace")
    repo_dir = workspace / Path(repo_url).name.removesuffix(".git")
    workspace.mkdir(parents=True, exist_ok=True)

    if (repo_dir / ".git").is_dir():
        logger.info("%s already cloned — fetching and checking out %s", repo_dir, repo_branch)
        fetch_reset(repo_dir, repo_branch)
    else:
        logger.info("cloning %s @ %s into %s", repo_url, repo_branch, repo_dir)
        clone(repo_url, repo_dir, branch=repo_branch, single_branch=True)

    # Install Python deps so the agent can run pytest/ruff inside the clone.
    synced = subprocess.run(
        ["uv", "sync", "--no-sources"], cwd=str(repo_dir),
        stdout=sys.stderr, stderr=sys.stderr, text=True, check=False,
    )
    if synced.returncode != 0:
        logger.warning("'uv sync --no-sources' failed; agent must resolve deps")

    _emit(str(repo_dir))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("setup"))
