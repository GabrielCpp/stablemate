#!/usr/bin/env python3
"""Commit a completed story's changes in each affected code repo.

Commits only in repos where implementation work was done (resolved from
plan-context.json). The docs repo is never committed to by this script —
it is only committed to if it appears in the affected repos list (i.e.
if it was an implementation target, not merely the workflow host).

Args: <epic> <story_slug> <spec_dir>
Outputs JSON: {"committed": "yes"|"no"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse.scriptutil import (
    commit_all,
    find_repo_root,
    get_affected_repos,
    load_json,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


def commit_in_repo(repo_path: Path, message: str) -> bool:
    """Stage all changes and commit in a repo. Returns True if a commit was made."""
    if not commit_all(repo_path, message):
        return False
    logger.info("committed in %s", repo_path.name)
    return True


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[commit-story] %(message)s")

    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else "story"
    spec_dir_rel = sys.argv[3] if len(sys.argv) > 3 else ""

    if epic:
        message = f"{epic}: {slug}"
    else:
        message = slug

    root = find_repo_root()
    repos = resolve_workspace("CODER_WORKSPACE")

    # Resolve affected repos from plan-context.json
    spec_dir = root / spec_dir_rel if spec_dir_rel else None
    plan_ctx = load_json(spec_dir / "plan-context.json", "plan-context.json", logger) if spec_dir and spec_dir.exists() else {}
    affected_names = get_affected_repos(plan_ctx, repos)

    if not affected_names:
        # No plan-context.json or empty services — fall back to committing in the CWD repo
        # (single-repo / no-workspace-file case, and test sandboxes without a seeded plan).
        logger.info("no affected repos resolved from plan-context — falling back to CWD")
        committed = commit_in_repo(root, message)
        print(json.dumps({"committed": "yes" if committed else "no"}))
        return

    any_committed = False
    for name in affected_names:
        repo_info = repos.get(name, {})
        repo_path = Path(repo_info.get("path", ""))
        if not repo_path.is_dir():
            logger.warning("repo %s path not found: %s", name, repo_path)
            continue
        if not (repo_path / ".git").exists():
            logger.warning("repo %s is not a git repo — skipping", name)
            continue

        if commit_in_repo(repo_path, message):
            any_committed = True

    print(json.dumps({"committed": "yes" if any_committed else "no"}))


if __name__ == "__main__":
    main()
