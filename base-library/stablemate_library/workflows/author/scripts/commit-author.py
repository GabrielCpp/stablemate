#!/usr/bin/env python3
"""Commit the epic/story docs an author run wrote.

The author workflow only ever writes into one repo (the docs repo running the
workflow) — unlike coder, there is no plan-context/affected-repos resolution
here; this always commits in the repo root.

Args: <mode> <epic> <bullet>
Outputs JSON: {"committed": "yes"|"no"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys

from workhorse.scriptutil import find_repo_root

logger = logging.getLogger(__name__)


def commit_in_repo(repo_path, message: str) -> bool:
    """Stage all changes and commit. Returns True if a commit was made."""
    subprocess.run(["git", "add", "-A"], cwd=str(repo_path), capture_output=True, check=False)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_path), capture_output=True, check=False)
    if r.returncode == 0:
        return False

    r = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(repo_path), capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        logger.warning("commit failed in %s: %s", repo_path, r.stderr.strip())
        return False

    logger.info("committed in %s", repo_path)
    return True


def build_message(mode: str, epic: str, bullet: str) -> str:
    if mode == "survey":
        return "author: survey intake and epic backlog authoring"
    if mode == "story" and epic:
        bullet_trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {bullet_trimmed}" if bullet_trimmed else f"author: {epic}"
    return "author: epic backlog authoring"


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[commit-author] %(message)s")

    mode = sys.argv[1] if len(sys.argv) > 1 else "epic"
    epic = sys.argv[2] if len(sys.argv) > 2 else ""
    bullet = sys.argv[3] if len(sys.argv) > 3 else ""

    repo_root = find_repo_root()
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — nothing to commit", repo_root)
        print(json.dumps({"committed": "no"}))
        return

    message = build_message(mode, epic, bullet)
    committed = commit_in_repo(repo_root, message)
    print(json.dumps({"committed": "yes" if committed else "no"}))


if __name__ == "__main__":
    main()
