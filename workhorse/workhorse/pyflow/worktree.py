"""Cutting a fresh git worktree and branch for a `--worktree`-dispatched run, and removing it once the run has landed it."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from workhorse._vendor.stablemate_core import worktree as shared
from workhorse.records import WorktreeOutcome

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


def base_name(repo_dir: Path, base_ref: str) -> str:
    """The name a branch cut from ``base_ref`` is later judged merged against."""
    return shared.base_name(repo_dir, base_ref)


def kept(reason: str) -> WorktreeOutcome:
    """An outcome that leaves the worktree and its branch where they are."""
    return WorktreeOutcome(action="kept", reason=reason)


def retire(*, path: Path, branch: str, base: str, repo_dir: Path | None = None) -> WorktreeOutcome:
    """Remove a finished run's worktree when nothing in it would be lost, and its branch when the branch is merged into ``base``."""
    done = shared.retire(path=path, branch=branch, base=base, repo_dir=repo_dir)
    return WorktreeOutcome(action=done.action, reason=done.reason, branch_deleted=done.branch_deleted)


def default_names(*, workflow: str, run_id: str) -> tuple[str, str]:
    """The default branch name and its sanitized form, from §3 of the plan."""
    branch = f"run/{workflow}-{run_id}"
    return branch, _sanitize(branch)


def dir_name_for(repo_dir: Path, sanitized_branch: str) -> str:
    """`<repo>-<sanitized-branch>`, the directory naming convention from §4."""
    return f"{repo_dir.name}-{sanitized_branch}"


__all__ = [
    "Worktree",
    "WorktreeError",
    "add",
    "base_name",
    "default_names",
    "dir_name_for",
    "kept",
    "retire",
]
