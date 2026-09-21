"""Cutting a fresh git worktree and branch for a `--worktree`-dispatched run."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 60.0


class WorktreeError(Exception):
    """`--worktree` could not cut a worktree."""


@dataclass(frozen=True, slots=True)
class Worktree:
    """The worktree and branch a fresh `--worktree` dispatch cut."""

    path: Path
    branch: str


def _sanitize(branch: str) -> str:
    """A branch name into something safe as a path segment: `/` is the only character branch names routinely carry that a directory name cannot."""
    return branch.replace("/", "-")


def add(
    *,
    repo_dir: Path,
    worktree_dir: Path,
    branch: str,
    base_ref: str,
    dir_name: str,
) -> Worktree:
    """Run `git worktree add -b <branch> <worktree_dir>/<dir_name> <base_ref>` from ``repo_dir``."""
    target = worktree_dir / dir_name
    if target.exists():
        raise WorktreeError(f"worktree directory already exists: {target}")
    if _branch_exists(repo_dir, branch):
        raise WorktreeError(f"branch already exists: {branch}")

    try:
        done = subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "add", "-b", branch, str(target), base_ref],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorktreeError(f"git worktree add failed: {exc}") from exc
    if done.returncode != 0:
        raise WorktreeError(
            f"git worktree add failed (exit {done.returncode}): {done.stderr.strip()}"
        )
    return Worktree(path=target, branch=branch)


def _branch_exists(repo_dir: Path, branch: str) -> bool:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_dir), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorktreeError(f"could not check for an existing branch: {exc}") from exc
    return done.returncode == 0


def default_names(*, workflow: str, run_id: str) -> tuple[str, str]:
    """The default branch name and its sanitized form, from §3 of the plan."""
    branch = f"run/{workflow}-{run_id}"
    return branch, _sanitize(branch)


def dir_name_for(repo_dir: Path, sanitized_branch: str) -> str:
    """`<repo>-<sanitized-branch>`, the directory naming convention from §4."""
    return f"{repo_dir.name}-{sanitized_branch}"


__all__ = ["Worktree", "WorktreeError", "add", "default_names", "dir_name_for"]
