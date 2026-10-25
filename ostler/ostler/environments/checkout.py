"""Find a repo's files in the main checkout when a git worktree lacks them."""

from __future__ import annotations

from pathlib import Path


def main_checkout(repo: Path) -> Path:
    """The main checkout *repo* belongs to, the same from any of its worktrees."""
    marker = repo / ".git"
    if not marker.is_file():
        return repo
    gitdir = Path(marker.read_text().removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = repo / gitdir
    common = gitdir / "commondir"
    if common.is_file():
        gitdir = gitdir / common.read_text().strip()
    return gitdir.resolve().parent


def locate(repo: Path, path: Path) -> Path:
    """*path*, or the file at the same place in the main checkout when only that one has it."""
    if path.is_file() or not path.is_relative_to(repo):
        return path
    main = main_checkout(repo)
    fallback = main / path.relative_to(repo)
    return fallback if main != repo and fallback.is_file() else path
