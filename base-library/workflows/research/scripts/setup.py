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
import os
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import allow_all_directories, clone, fetch_reset


def _emit(repo_dir: str, status: str = "ok") -> None:
    print(json.dumps({"setup_result": {"repo_dir": repo_dir, "status": status}}))


def main() -> None:
    # Native in-place mode: when AGENT_REPO_DIR is set, operate directly on that
    # existing checkout instead of cloning into /workspace. Used by the generated
    # launcher's `*-native` target, which runs the controller on the host so the
    # agent edits and commits straight into the real repo (no Docker, no clone).
    # HRNET_REPO_DIR is accepted as a backward-compat alias for AGENT_REPO_DIR.
    repo_dir_env = os.environ.get("AGENT_REPO_DIR") or os.environ.get("HRNET_REPO_DIR")
    if repo_dir_env:
        allow_all_directories()
        print(f"[setup] in-place mode: using existing repo at {repo_dir_env} (no clone)",
              file=sys.stderr)
        _emit(repo_dir_env)
        return

    # Env wins over args so a compose override can redirect the clone source (e.g. to
    # a read-only bind mount of a local repo) without editing the committed workflow.
    repo_url = os.environ.get("REPO_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not repo_url:
        print("[setup] repo url required", file=sys.stderr)
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
        print(f"[{repo_dir}] already cloned — fetching and checking out {repo_branch}",
              file=sys.stderr)
        fetch_reset(repo_dir, repo_branch)
    else:
        print(f"[{repo_dir}] cloning {repo_url} @ {repo_branch}", file=sys.stderr)
        clone(repo_url, repo_dir, branch=repo_branch, single_branch=True)

    # Install Python deps so the agent can run pytest/ruff inside the clone.
    synced = subprocess.run(
        ["uv", "sync", "--no-sources"], cwd=str(repo_dir),
        stdout=sys.stderr, stderr=sys.stderr, text=True, check=False,
    )
    if synced.returncode != 0:
        print("[setup] warning: 'uv sync --no-sources' failed; agent must resolve deps",
              file=sys.stderr)

    _emit(str(repo_dir))


if __name__ == "__main__":
    main()
