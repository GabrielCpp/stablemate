"""Cutting a fresh git worktree and branch for a `--worktree`-dispatched run.

Unlike `workhorse.gitstate`, which observes a tree and never fails a run over it, this
module *drives* git: `git worktree add` either produces the worktree the run is about to
live in, or it didn't, and there is no meaningful "empty" answer to fall back to in
between. So it raises a clear, named error — on a missing `worktree_dir` config, on a
branch or directory collision, or on the underlying `git` invocation failing — rather
than returning a sentinel the caller has to re-interpret.

Same subprocess-and-timeout shape as `gitstate.py`, for the same reason: workhorse stays
dependency-light and does not pull in GitPython for one command.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Generous for a worktree checkout of a normal-sized repo; still short enough that a
#: wedged filesystem or a huge repo costs the caller a bounded failure, not a hang.
TIMEOUT_S = 60.0


class WorktreeError(Exception):
    """`--worktree` could not cut a worktree. The message names the fix or the conflict."""


@dataclass(frozen=True, slots=True)
class Worktree:
    """The worktree and branch a fresh `--worktree` dispatch cut."""

    path: Path
    branch: str


def _sanitize(branch: str) -> str:
    """A branch name into something safe as a path segment: `/` is the only character
    branch names routinely carry that a directory name cannot."""
    return branch.replace("/", "-")


def add(
    *,
    repo_dir: Path,
    worktree_dir: Path,
    branch: str,
    base_ref: str,
    dir_name: str,
) -> Worktree:
    """Run `git worktree add -b <branch> <worktree_dir>/<dir_name> <base_ref>` from
    ``repo_dir``. Raises :class:`WorktreeError` naming the conflict when the branch or
    the target directory already exists, or when git itself fails."""
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
