"""Cutting a fresh git worktree and branch for a `--worktree`-dispatched run, and removing it once the run has landed it."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

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
    """The name a branch cut from ``base_ref`` is later judged merged against: ``HEAD`` resolves to the branch it points at, or its commit when detached."""
    if base_ref != "HEAD":
        return base_ref
    branch = _git(repo_dir, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch is not None and branch.returncode == 0 and branch.stdout.strip():
        return branch.stdout.strip()
    head = _git(repo_dir, "rev-parse", "HEAD")
    if head is not None and head.returncode == 0:
        return head.stdout.strip()
    return base_ref


def kept(reason: str) -> WorktreeOutcome:
    """An outcome that leaves the worktree and its branch where they are."""
    return WorktreeOutcome(action="kept", reason=reason)


def retire(*, path: Path, branch: str, base: str, repo_dir: Path | None = None) -> WorktreeOutcome:
    """Remove a finished run's worktree when nothing in it would be lost, and its branch when the branch is merged into ``base``."""
    repo = repo_dir or _owning_repo(path)
    if repo is None:
        return kept(f"cannot find the repository that owns {path}")
    base = base or "HEAD"
    tips: list[tuple[str, str]] = []
    present = path.exists()
    if present:
        status = _git(path, "status", "--porcelain")
        if status is None or status.returncode != 0:
            return kept(f"git status failed in {path}: {_stderr(status)}")
        if status.stdout.strip():
            return kept("the worktree has uncommitted changes")
        head = _rev(path, "HEAD")
        if head is None:
            return kept(f"cannot read the worktree's HEAD in {path}")
        tips.append(("the worktree's HEAD", head))
    branch_tip = _rev(repo, f"refs/heads/{branch}") if branch else None
    if branch_tip is not None:
        tips.append((f"branch '{branch}'", branch_tip))

    pushed = False
    for label, sha in tips:
        if _merged(repo, sha, base):
            continue
        if not _pushed(repo, sha):
            return kept(f"{label} is neither merged into '{base}' nor pushed to a remote")
        pushed = True

    if present:
        removed = _git(repo, "worktree", "remove", str(path))
        if removed is None or removed.returncode != 0:
            return kept(f"git worktree remove failed: {_stderr(removed)}")

    reason = f"pushed to a remote, not merged into '{base}'" if pushed else f"merged into '{base}'"
    if not tips:
        reason = "the worktree directory was already gone"
    deleted = False
    if branch_tip is not None:
        if _merged(repo, branch_tip, base):
            done = _git(repo, "branch", "-D", branch)
            deleted = done is not None and done.returncode == 0
            if not deleted:
                reason += f"; branch '{branch}' kept: {_stderr(done)}"
        else:
            reason += f"; branch '{branch}' kept: not merged into '{base}'"
    return WorktreeOutcome(action="removed", reason=reason, branch_deleted=deleted)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _stderr(done: subprocess.CompletedProcess[str] | None) -> str:
    if done is None:
        return "git could not be run"
    return done.stderr.strip() or f"exit {done.returncode}"


def _rev(cwd: Path, ref: str) -> str | None:
    done = _git(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if done is None or done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _merged(repo: Path, sha: str, base: str) -> bool:
    done = _git(repo, "merge-base", "--is-ancestor", sha, base)
    return done is not None and done.returncode == 0


def _pushed(repo: Path, sha: str) -> bool:
    done = _git(repo, "for-each-ref", "--contains", sha, "--count=1", "--format=%(refname)", "refs/remotes")
    return done is not None and done.returncode == 0 and bool(done.stdout.strip())


def _owning_repo(path: Path) -> Path | None:
    """The checkout a linked worktree belongs to, read off the git dir it shares."""
    if not path.exists():
        return None
    done = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if done is None or done.returncode != 0 or not done.stdout.strip():
        return None
    common = Path(done.stdout.strip())
    return common.parent if common.name == ".git" else common


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
