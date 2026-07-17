#!/usr/bin/env python3
"""Cut the working branch across all affected repos in the workspace.

Args: <story_slug>

For each repo in affected_repos (read from plan-context.json via workspace
resolution), cuts or checks out story/<slug>. Also branches the docs repo
(AGENT_REPO_DIR). Idempotent: existing branches are checked out without reset.

Prints JSON: {"branched": "yes", "repos": ["api-service", "web-app", ...]}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from workhorse.scriptutil import (
    checkout,
    find_repo_root,
    get_affected_repos,
    load_json,
    local_branch_exists,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


def branch_repo(repo_path: Path, repo_name: str, branch: str) -> bool:
    """Cut or check out branch in repo_path. Returns True if successful."""
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return False

    if local_branch_exists(repo_path, branch):
        checkout(repo_path, branch)
        logger.info("%s: checked out existing %s", repo_name, branch)
    else:
        checkout(repo_path, branch, create=True)
        logger.info("%s: created %s", repo_name, branch)
    return True


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    slug = sys.argv[1] if len(sys.argv) > 1 else "story"
    branch = f"story/{slug}"

    root = find_repo_root()
    spec_dir_rel = os.environ.get("SPEC_DIR", "")
    plan_ctx = load_json(root / spec_dir_rel / "plan-context.json", "plan-context.json", logger) if spec_dir_rel else {}

    repos = resolve_workspace("CODER_WORKSPACE")
    branched: list[str] = []

    # Branch the docs repo first
    docs_name = root.name
    if branch_repo(root, docs_name, branch):
        branched.append(docs_name)

    # Branch each affected repo
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == root:
            continue  # already branched above
        if branch_repo(repo_path, repo_name, branch):
            branched.append(repo_name)

    print(json.dumps({"branched": "yes", "repos": branched}))


if __name__ == "__main__":
    main()
