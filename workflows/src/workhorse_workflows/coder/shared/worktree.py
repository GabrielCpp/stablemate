"""What was already dirty when a story started, and what still is."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from git.exc import GitError
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import WorktreeSnapshot
from workhorse_workflows.kit import open_repo


def digest(root: Path, rel: str) -> str:
    """The sha256 of one worktree file, or `""` when it cannot be read."""
    try:
        return hashlib.sha256((root / rel).read_bytes()).hexdigest()
    except OSError:
        return ""


def untouched_since(root: Path, snapshot: tuple[str, ...]) -> set[str]:
    """Which snapshotted paths still hold exactly the bytes they held at story start."""
    untouched: set[str] = set()
    for entry in snapshot:
        rel, separator, recorded = str(entry).partition("\0")
        if not separator or not rel or not recorded:
            continue
        if digest(root, rel) == recorded:
            untouched.add(rel)
    return untouched


@blueprint.node
def snapshot_worktree_state(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = ""
) -> WorktreeSnapshot:
    """Record what was already dirty before this story's first dev turn."""
    root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    try:
        repo = open_repo(root)
        dirty = [item.a_path for item in repo.index.diff(None) if item.a_path]
        dirty.extend(repo.untracked_files)
    except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.info("could not read the worktree state at %s (%s) — snapshot is empty", root, exc)
        return WorktreeSnapshot(entries=[], notes=f"worktree state unavailable: {exc}")

    entries = [f"{rel}\0{sha}" for rel in sorted(set(dirty)) if (sha := digest(root, rel))]
    logger.info("snapshotted %d pre-existing dirty path(s) at %s", len(entries), root)
    return WorktreeSnapshot(
        entries=entries, notes=f"{len(entries)} path(s) were already dirty when the story started"
    )


__all__ = ["digest", "snapshot_worktree_state", "untouched_since"]
