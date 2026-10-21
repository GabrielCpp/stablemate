"""What the worktrees held before a turn, and what changed since."""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from git.exc import GitError
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.worktree import (
    CodeChange,
    DirtyAtStart,
    PorcelainSnapshot,
)
from workhorse_workflows.kit import open_repo, resolve_workspace


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


def _dirty_entries(root: Path, owner: str = "") -> list[str]:
    """Each dirty path of *root* with its digest, and *owner* when the entry names its checkout."""
    repo = open_repo(root)
    dirty = [item.a_path for item in repo.index.diff(None) if item.a_path]
    dirty.extend(repo.untracked_files)
    suffix = f"\0{owner}" if owner else ""
    return [f"{rel}\0{sha}{suffix}" for rel in sorted(set(dirty)) if (sha := digest(root, rel))]


@blueprint.node
def snapshot_worktree_state(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
    roots: list[str] | None = None,
) -> DirtyAtStart:
    """Record what was already dirty before this story's first dev turn, in the docs root or in each of *roots*."""
    if roots is None:
        checkouts = [(Path(find_docs_root(docs_path, repo_dir)).resolve(), "")]
    else:
        checkouts = [(resolved, str(resolved)) for resolved in (Path(r).resolve() for r in roots)]
    entries: list[str] = []
    for root, owner in checkouts:
        try:
            entries.extend(_dirty_entries(root, owner))
        except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
            logger.info("could not read the worktree state at %s (%s) — nothing snapshotted there", root, exc)
            if roots is None:
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


GIT_TIMEOUT = 60


def _code_repos(docs_path: str, repo_dir: str, workspace_file: str) -> list[Path]:
    """The workspace repos the clean-tree gate covers: everything but the docs root."""
    docs_root = find_docs_root(docs_path, repo_dir).resolve()
    repos = resolve_workspace(workspace_file, repo_dir)
    return [
        path
        for repo in repos.values()
        if (path := Path(repo["path"])).is_dir() and path.resolve() != docs_root
    ]


def _git(repo: Path, *args: str) -> str | None:
    """One git read in `repo`, or None when it cannot answer — a caller skips, never guesses."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _code_state(docs_path: str, repo_dir: str, workspace_file: str) -> dict[str, str]:
    state: dict[str, str] = {}
    for repo in _code_repos(docs_path, repo_dir, workspace_file):
        head = _git(repo, "rev-parse", "HEAD")
        status = _git(repo, "status", "--porcelain")
        if head is not None and status is not None:
            state[str(repo)] = head + status
    return state


@blueprint.node
def snapshot_code_state(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = ""
) -> PorcelainSnapshot:
    """Record each code repo's HEAD and porcelain status, so later edits and commits both show."""
    return PorcelainSnapshot(status=_code_state(docs_path, repo_dir, workspace_file))


@blueprint.node
def code_changed(
    logger: logging.Logger,
    before: dict[str, str] | None = None,
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> CodeChange:
    """Whether any code repo moved since `snapshot_code_state`, or there is no code repo to watch."""
    now = _code_state(docs_path, repo_dir, workspace_file)
    return CodeChange(changed=not now or now != (before or {}))


__all__ = [
    "code_changed",
    "digest",
    "snapshot_code_state",
    "snapshot_owner_baseline",
    "snapshot_worktree_state",
    "untouched_since",
]
