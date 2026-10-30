"""What the worktrees held before a turn, and what changed since."""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from git.exc import GitError
from ostler import path as okf_path
from workhorse._vendor.stablemate_core import config as core_config
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths
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
) -> DirtyAtStart:
    """Record what was already dirty before this story's first dev turn, in the docs root or in each of *roots*."""
    if roots is None:
        checkouts = [(Path(find_docs_root(repo_dir)).resolve(), "")]
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


def _workspace_repos(repo_dir: str, workspace: str) -> list[Path]:
    """Every workspace repo, the docs root included, each once."""
    seen: set[Path] = set()
    found: list[Path] = []
    for repo in resolve_workspace(workspace, repo_dir).values():
        path = Path(repo["path"])
        if path.is_dir() and path.resolve() not in seen:
            seen.add(path.resolve())
            found.append(path)
    return found


def not_product_roots(repo_dir: str, *, book: bool = True) -> list[Path]:
    """The resolved folders no proof or docs pass is reopened by: the artifacts dir, and the book when *book* is set."""
    roots = [core_config.resolve_artifacts_dir().resolve()]
    if book:
        roots.append(okf_path.services_root_in(find_docs_root(repo_dir)).resolve())
    return roots


def is_product(repo: Path, rel: str, excluded: list[Path]) -> bool:
    """Is *rel* of *repo* work a proof depends on: outside every *excluded* folder and not tool output?"""
    if paths.is_tool_output(rel):
        return False
    absolute = (repo / rel).resolve()
    return not any(absolute.is_relative_to(root) for root in excluded)


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


def _product_entries(repo: Path, excluded: list[Path]) -> list[str] | None:
    """The dirty product paths of *repo* as `rel\0sha`, or None when git cannot say."""
    try:
        entries = _dirty_entries(repo, keep_missing=True)
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        return None
    return sorted(e for e in entries if is_product(repo, e.partition("\0")[0], excluded))


def _code_state(repo_dir: str, workspace: str) -> tuple[dict[str, str], int]:
    """Each readable repo's HEAD and product dirty entries, keyed by path, and how many repos there are."""
    excluded = not_product_roots(repo_dir)
    repos = _workspace_repos(repo_dir, workspace)
    state: dict[str, str] = {}
    for repo in repos:
        head = _git(repo, "rev-parse", "HEAD")
        entries = _product_entries(repo, excluded)
        if head is not None and entries is not None:
            state[str(repo)] = "\n".join([head.strip(), *entries])
    return state, len(repos)


@blueprint.node
def snapshot_code_state(
    logger: logging.Logger, repo_dir: str = "", workspace: str = ""
) -> PorcelainSnapshot:
    """Record each repo's HEAD and its dirty product paths with digests, so later edits and commits both show."""
    return PorcelainSnapshot(status=_code_state(repo_dir, workspace)[0])


def _moved(repo: Path, before: str, now: str, excluded: list[Path]) -> bool:
    """Did a product path of *repo* change between the *before* and *now* states?"""
    old_head, *old_entries = before.split("\n")
    new_head, *new_entries = now.split("\n")
    if set(old_entries) != set(new_entries):
        return True
    if old_head == new_head:
        return False
    listed = _git(repo, "diff", "--name-only", old_head, new_head)
    if listed is None:
        return True
    return any(is_product(repo, rel, excluded) for rel in listed.splitlines() if rel)


@blueprint.node
def code_changed(
    logger: logging.Logger,
    before: dict[str, str] | None = None,
    repo_dir: str = "",
    workspace: str = "",
) -> CodeChange:
    """Whether a product path of any repo changed since `snapshot_code_state`, or no repo can be watched."""
    now, total = _code_state(repo_dir, workspace)
    if not total or len(now) != total:
        return CodeChange(changed=True)
    held = before or {}
    excluded = not_product_roots(repo_dir)
    for key, state in now.items():
        if key not in held or _moved(Path(key), held[key], state, excluded):
            return CodeChange(changed=True)
    return CodeChange(changed=False)


__all__ = [
    "code_changed",
    "digest",
    "is_product",
    "not_product_roots",
    "snapshot_code_state",
    "snapshot_owner_baseline",
    "snapshot_worktree_state",
    "untouched_since",
]
