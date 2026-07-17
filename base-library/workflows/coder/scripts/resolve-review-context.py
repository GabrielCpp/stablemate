#!/usr/bin/env python3
"""Emit the docs repo path and affected repo paths for the holistic review node.

The review agent needs add_dirs to all affected repos plus the docs repo as its
CWD. This script resolves those paths from the workspace configuration and the
plan-context.json services list.

Usage: resolve-review-context.py <spec_dir> [repo] [docs_path]
  repo: optional repo name (e.g. "api-service", "web-app") used as the sole affected
        repo when plan-context.json is unavailable (standalone PR review).
  docs_path: docs repo root; empty → AGENT_REPO_DIR / CWD (see find_docs_root).
Prints one JSON object on stdout:
  {
    "docs_repo_path": "/abs/path/to/docs/repo",
    "affected_repo_paths": ["/abs/path/to/api-service", "/abs/path/to/web-app"]
  }
"""

from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import (
    find_docs_root,
    get_affected_repos,
    load_json,
    resolve_workspace,
)

def main(logger: logging.Logger) -> None:
    spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    repo_arg = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""
    docs_path_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
    # The docs repo is NOT necessarily the orchestrating repo (AGENT_REPO_DIR) — it
    # may or may not be a workspace folder, a git repo, or have an agents.yml (see
    # docs/repo-modes.md). Use the explicit docs_path arg, never a cwd-walk guess.
    root = find_docs_root(docs_path_arg)

    plan_ctx = (
        load_json(
            root / spec_dir_rel / "plan-context.json", "plan-context.json", logger
        )
        if spec_dir_rel
        else {}
    )
    repos = resolve_workspace("CODER_WORKSPACE")

    # The docs repo is the explicitly-resolved docs root, not the workflow's launch CWD.
    docs_repo_path = str(root)

    if not plan_ctx and repo_arg:
        # Standalone PR review: no plan-context.json, use the explicit repo arg
        affected_names = [repo_arg]
    else:
        affected_names = get_affected_repos(plan_ctx, repos)

    affected_repo_paths = [
        repos[name]["path"] for name in affected_names if name in repos
    ]

    print(
        json.dumps(
            {
                "docs_repo_path": docs_repo_path,
                "affected_repo_paths": affected_repo_paths,
            }
        )
    )


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    main(logging.getLogger("resolve-review-context"))
