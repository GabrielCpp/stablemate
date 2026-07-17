#!/usr/bin/env python3
"""Cut the working branch for a single story (story mode).

Args: <story_slug> [<docs_path>]

Branch name is <slug> (no prefix). Records the branch the run started from as
the PR base. Idempotent: if <slug> already exists (a resume), checks it out
WITHOUT resetting it (preserving its commits). Also branches each repo listed
in plan-context.json (resolved via CODER_WORKSPACE), idempotent.

Prints JSON: {"base_branch": "<branch>", "story_branch": "<slug>",
              "repos": ["vigilant-octo", ...]}.
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


def main(logger: logging.Logger) -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "story"
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    branch = slug

    docs_root = find_docs_root(docs_path_arg)

    # Capture the PR base from the docs repo before cutting the new branch.
    base_branch = "main"
    if (docs_root / ".git").exists():
        base_branch = current_branch(docs_root)
        if not base_branch or base_branch == branch:
            base_branch = "main"

    branched: list[str] = []

    # Branch the docs repo first.
    docs_name = docs_root.name
    if branch_repo(docs_root, docs_name, branch):
        branched.append(docs_name)

    # Branch each affected code repo from plan-context.json via workspace.
    spec_dir_rel = os.environ.get("SPEC_DIR", f"docs/specs/{slug}")
    plan_ctx = load_json(docs_root / spec_dir_rel / "plan-context.json", "plan-context.json", logger)

    repos = resolve_workspace("CODER_WORKSPACE")
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue  # already branched above
        if branch_repo(repo_path, repo_name, branch):
            branched.append(repo_name)

    print(json.dumps({
        "base_branch": base_branch,
        "story_branch": branch,
        "repos": branched,
    }))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("branch-story"))
