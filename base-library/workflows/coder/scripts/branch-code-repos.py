#!/usr/bin/env python3
"""Branch any code repos named in plan-context.json onto the story branch.

Called after planning (resolve_impl_context) so plan-context.json already exists and
the affected_repos list is authoritative. The target branch is passed explicitly by the
workflow (from branch_story output). Falls back to the docs repo's current HEAD only
when no explicit branch is given. Idempotent: repos already on the target branch are
skipped silently.

Args: <spec_dir> [<branch>]

Prints JSON: {"branched": ["api-service", ...], "already_on_branch": ["web-app", ...]}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from workhorse.scriptutil import (
    checkout,
    current_branch,
    find_docs_root,
    get_affected_repos,
    load_json,
    local_branch_exists,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


def branch_repo(repo_path: Path, repo_name: str, branch: str) -> str:
    """Ensure repo_path is on branch. Returns 'branched', 'already_on_branch', or 'skipped'."""
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return "skipped"

    if current_branch(repo_path) == branch:
        logger.info("%s: already on %s", repo_name, branch)
        return "already_on_branch"

    if local_branch_exists(repo_path, branch):
        checkout(repo_path, branch)
        logger.info("%s: checked out existing %s", repo_name, branch)
    else:
        checkout(repo_path, branch, create=True)
        logger.info("%s: created %s", repo_name, branch)
    return "branched"


def main(logger: logging.Logger) -> None:
    spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 else ""
    branch_arg = sys.argv[2] if len(sys.argv) > 2 else ""

    docs_root = find_docs_root()
    spec_dir_rel = spec_dir_rel or os.environ.get("SPEC_DIR", "")
    plan_ctx = load_json(docs_root / spec_dir_rel / "plan-context.json", "plan-context.json", logger) if spec_dir_rel else {}

    # Use explicit branch from workflow; fall back to docs repo HEAD.
    if branch_arg:
        branch = branch_arg
    elif (docs_root / ".git").exists():
        branch = current_branch(docs_root)
    else:
        branch = "main"
        logger.warning("docs root %s is not a git repo and no branch arg — defaulting to 'main'", docs_root)

    repos = resolve_workspace("CODER_WORKSPACE")
    branched: list[str] = []
    already_on_branch: list[str] = []

    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue  # docs repo is already on the correct branch
        result = branch_repo(repo_path, repo_name, branch)
        if result == "branched":
            branched.append(repo_name)
        elif result == "already_on_branch":
            already_on_branch.append(repo_name)

    print(json.dumps({"branched": branched, "already_on_branch": already_on_branch}))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("branch-code-repos"))
