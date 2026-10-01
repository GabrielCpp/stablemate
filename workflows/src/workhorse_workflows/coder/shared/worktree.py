"""What the worktrees held before a turn, and what changed since."""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

from git.exc import GitError
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.worktree import DirtyAtStart, PlanScrub, PorcelainSnapshot
from workhorse_workflows.kit import open_repo, resolve_workspace


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
) -> DirtyAtStart:
    """Record what was already dirty before this story's first dev turn."""
    root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    try:
        repo = open_repo(root)
        dirty = [item.a_path for item in repo.index.diff(None) if item.a_path]
        dirty.extend(repo.untracked_files)
    except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.info("could not read the worktree state at %s (%s) — snapshot is empty", root, exc)
        return DirtyAtStart(entries=[], notes=f"worktree state unavailable: {exc}")

    entries = [f"{rel}\0{sha}" for rel in sorted(set(dirty)) if (sha := digest(root, rel))]
    logger.info("snapshotted %d pre-existing dirty path(s) at %s", len(entries), root)
    return DirtyAtStart(
        entries=entries, notes=f"{len(entries)} path(s) were already dirty when the story started"
    )


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


def _porcelain_paths(porcelain: str) -> dict[str, str]:
    """Porcelain lines keyed by the path they name, rename targets included."""
    entries: dict[str, str] = {}
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        for part in line[3:].split(" -> "):
            entries[part.strip('"')] = line
    return entries


@blueprint.node
def snapshot_worktrees(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = ""
) -> PorcelainSnapshot:
    """Record each code repo's `git status --porcelain` before the plan turn runs."""
    status: dict[str, str] = {}
    for repo in _code_repos(docs_path, repo_dir, workspace_file):
        out = _git(repo, "status", "--porcelain")
        if out is None:
            logger.warning("cannot read git status in %s — the clean-tree gate skips it", repo)
            continue
        status[str(repo)] = out
    return PorcelainSnapshot(status=status)


@blueprint.node
def scrub_plan_mutations(
    logger: logging.Logger,
    before: dict[str, str] | None = None,
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> PlanScrub:
    """Revert whatever the plan turn wrote into the code repos."""
    before = before or {}
    reverted: dict[str, str] = {}
    for repo in _code_repos(docs_path, repo_dir, workspace_file):
        key = str(repo)
        if key not in before:
            continue
        out = _git(repo, "status", "--porcelain")
        if out is None:
            logger.warning("cannot read git status in %s — the clean-tree gate skips it", repo)
            continue
        prior = _porcelain_paths(before[key])
        fresh = {
            path: line for path, line in _porcelain_paths(out).items() if path not in prior
        }
        if not fresh:
            continue
        tracked = sorted(p for p, line in fresh.items() if not line.startswith("??"))
        untracked = sorted(p for p, line in fresh.items() if line.startswith("??"))
        diff = _git(repo, "diff", "HEAD", "--", *tracked) if tracked else ""
        if tracked and _git(repo, "checkout", "HEAD", "--", *tracked) is None:
            logger.warning("could not restore %s in %s", tracked, repo)
        for path in untracked:
            target = repo / path
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        record = "\n".join(sorted(set(fresh.values())))
        if diff:
            record += "\n" + diff[:4000]
        reverted[key] = record
        logger.warning(
            "the plan turn modified %s — reverted, planning must not touch code:\n%s",
            repo,
            record,
        )
    return PlanScrub(reverted=reverted)


__all__ = [
    "digest",
    "scrub_plan_mutations",
    "snapshot_worktree_state",
    "snapshot_worktrees",
    "untouched_since",
]
