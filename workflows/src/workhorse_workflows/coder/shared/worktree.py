"""What the worktrees held before a turn."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from git.exc import GitError
from workhorse._vendor.stablemate_core import books, config as core_config
from workhorse_workflows.kit import find_book_root, find_repo_root, resolve_workspace
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.worktree import DirtyAtStart
from workhorse_workflows.kit import open_repo


def digest(root: Path, rel: str) -> str:
    """The sha256 of one worktree file, or `""` when it cannot be read."""
    try:
        return hashlib.sha256((root / rel).read_bytes()).hexdigest()
    except OSError:
        return ""


def untouched_since(root: Path, snapshot: tuple[str, ...]) -> set[str]:
    """Which snapshotted paths of *root* still hold exactly the bytes they held at story start."""
    held = str(root.resolve())
    untouched: set[str] = set()
    for entry in snapshot:
        rel, _, rest = str(entry).partition("\0")
        recorded, _, owner = rest.partition("\0")
        if not rel or not recorded or owner not in ("", held):
            continue
        if digest(root, rel) == recorded:
            untouched.add(rel)
    return untouched


def _dirty_entries(root: Path, owner: str = "", keep_missing: bool = False) -> list[str]:
    """Each dirty path of *root* with its digest, and *owner* when the entry names its checkout; a deleted path is kept, with an empty digest, only when *keep_missing* is set."""
    repo = open_repo(root)
    dirty = [item.a_path for item in repo.index.diff(None) if item.a_path]
    dirty.extend(repo.untracked_files)
    suffix = f"\0{owner}" if owner else ""
    return [f"{rel}\0{sha}{suffix}" for rel in sorted(set(dirty)) if (sha := digest(root, rel)) or keep_missing]


@blueprint.node
def snapshot_worktree_state(
    logger: logging.Logger,
    repo_dir: str = "",
    roots: list[str] | None = None,
    workspace: str = "",
) -> DirtyAtStart:
    """Record what was already dirty before this story's first dev turn, in the book root and each code repo of the run, or in each of *roots*."""
    if roots is None:
        book = Path(find_book_root(repo_dir)).resolve()
        members = [Path(repo["path"]).resolve() for repo in resolve_workspace(workspace, repo_dir).values()]
        checkouts = [(book, ""), *((member, str(member)) for member in dict.fromkeys(members) if member != book)]
    else:
        checkouts = [(resolved, str(resolved)) for resolved in (Path(r).resolve() for r in roots)]
    entries: list[str] = []
    for root, owner in checkouts:
        try:
            entries.extend(_dirty_entries(root, owner))
        except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
            logger.info("could not read the worktree state at %s (%s) — nothing snapshotted there", root, exc)
            if not owner:
                return DirtyAtStart(entries=[], notes=f"worktree state unavailable: {exc}")
    logger.info(
        "snapshotted %d pre-existing dirty path(s) at %s",
        len(entries),
        ", ".join(str(root) for root, _ in checkouts),
    )
    return DirtyAtStart(
        entries=entries, notes=f"{len(entries)} path(s) were already dirty when the story started"
    )


@blueprint.node
def snapshot_owner_baseline(
    logger: logging.Logger, roots: list[str] | None = None
) -> DirtyAtStart:
    """`snapshot_worktree_state` under a second node id: what was dirty once the run had seeded the item."""
    return snapshot_worktree_state(logger, roots=list(roots or []))


def not_product_roots(repo_dir: str) -> list[Path]:
    """The resolved folders no proof is reopened by: the artifacts dir, and the book root of a workspace run."""
    artifacts = core_config.resolve_artifacts_dir().resolve()
    if books.book_in_repo(find_repo_root(repo_dir)):
        return [artifacts]
    return list(dict.fromkeys([artifacts, find_book_root(repo_dir).resolve()]))


def is_product(repo: Path, rel: str, excluded: list[Path]) -> bool:
    """Is *rel* of *repo* work a proof depends on: outside every *excluded* folder and not tool output?"""
    if paths.is_tool_output(rel):
        return False
    absolute = (repo / rel).resolve()
    return not any(absolute.is_relative_to(root) for root in excluded)


__all__ = [
    "digest",
    "is_product",
    "not_product_roots",
    "snapshot_owner_baseline",
    "snapshot_worktree_state",
    "untouched_since",
]
