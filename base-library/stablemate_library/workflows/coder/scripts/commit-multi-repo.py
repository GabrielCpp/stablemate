#!/usr/bin/env python3
"""Commit changes across all affected repos in the workspace.

Args: <story_slug> [<epic>]

For each repo with uncommitted changes: stage all + commit with a message
prefixed by the epic (or slug-only if no epic). Skips repos with no changes.

Prints JSON: {"committed": "yes"|"no", "repos_committed": ["api-service", ...]}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root, get_affected_repos, load_json, resolve_workspace

from lib import ghutil

logger = logging.getLogger(__name__)


def commit_repo(repo_path: Path, repo_name: str, message: str) -> bool:
    """Stage all changes and commit. Returns True if a commit was made."""
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return False

    ghutil.run(["git", "add", "-A"], repo_path)
    if ghutil.run(["git", "diff", "--cached", "--quiet"], repo_path).returncode == 0:
        logger.info("%s: no changes to commit", repo_name)
        return False

    r = ghutil.run(["git", "commit", "-m", message], repo_path)
    if r.returncode != 0:
        logger.warning("%s: commit failed: %s", repo_name, r.stderr.strip())
        return False

    logger.info("%s: committed '%s'", repo_name, message)
    return True


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    slug = sys.argv[1] if len(sys.argv) > 1 else "story"
    epic = sys.argv[2] if len(sys.argv) > 2 else ""
    message = f"{epic}: {slug}" if epic else slug

    root = find_repo_root()
    spec_dir_rel = os.environ.get("SPEC_DIR", "")
    plan_ctx = load_json(root / spec_dir_rel / "plan-context.json", "plan-context.json", logger) if spec_dir_rel else {}

    repos = resolve_workspace("CODER_WORKSPACE")
    committed: list[str] = []

    # Commit the docs repo first
    docs_name = root.name
    if commit_repo(root, docs_name, message):
        committed.append(docs_name)

    # Commit each affected repo
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == root:
            continue  # already handled above
        if commit_repo(repo_path, repo_name, message):
            committed.append(repo_name)

    if committed:
        print(json.dumps({"committed": "yes", "repos_committed": committed}))
    else:
        print(json.dumps({"committed": "no", "repos_committed": []}))


if __name__ == "__main__":
    main()
