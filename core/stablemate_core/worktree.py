"""Whether a linked git worktree can go without losing anything, and removing it when it can."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TIMEOUT_S = 60.0


@dataclass(frozen=True, slots=True)
class Assessment:
    """Why a worktree must stay, or how its work already landed when ``keep`` is empty."""

    keep: str = ""
    landed: str = ""


@dataclass(frozen=True, slots=True)
class Retirement:
    """What retiring a worktree did with it and with its branch."""

    action: Literal["removed", "kept"]
    reason: str = ""
    branch_deleted: bool = False


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run git in ``cwd``, or None when git could not be run at all."""
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


def base_name(repo_dir: Path, base_ref: str) -> str:
    """The name a branch cut from ``base_ref`` is later judged merged against: ``HEAD`` resolves to the branch it points at, or its commit when detached."""
    if base_ref != "HEAD":
        return base_ref
    branch = git(repo_dir, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch is not None and branch.returncode == 0 and branch.stdout.strip():
        return branch.stdout.strip()
    head = git(repo_dir, "rev-parse", "HEAD")
    if head is not None and head.returncode == 0:
        return head.stdout.strip()
    return base_ref


def owning_repo(path: Path) -> Path | None:
    """The checkout a linked worktree belongs to, read off the git dir it shares."""
    if not path.exists():
        return None
    done = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if done is None or done.returncode != 0 or not done.stdout.strip():
        return None
    common = Path(done.stdout.strip())
    return common.parent if common.name == ".git" else common


def assess(*, path: Path, branch: str, base: str, repo: Path) -> Assessment:
    """Decide whether removing the worktree would lose anything, changing nothing."""
    base = base or "HEAD"
    tips: list[tuple[str, str]] = []
    if path.exists():
        status = git(path, "--no-optional-locks", "status", "--porcelain")
        if status is None or status.returncode != 0:
            return Assessment(keep=f"git status failed in {path}: {_stderr(status)}")
        if status.stdout.strip():
            return Assessment(keep="the worktree has uncommitted changes")
        head = _rev(path, "HEAD")
        if head is None:
            return Assessment(keep=f"cannot read the worktree's HEAD in {path}")
        tips.append(("the worktree's HEAD", head))
    branch_tip = _rev(repo, f"refs/heads/{branch}") if branch else None
    if branch_tip is not None:
        tips.append((f"branch '{branch}'", branch_tip))

    pushed = False
    for label, sha in tips:
        if _merged(repo, sha, base):
            continue
        if not _pushed(repo, sha):
            return Assessment(keep=f"{label} is neither merged into '{base}' nor pushed to a remote")
        pushed = True

    if not tips:
        return Assessment(landed="the worktree directory was already gone")
    if pushed:
        return Assessment(landed=f"pushed to a remote, not merged into '{base}'")
    return Assessment(landed=f"merged into '{base}'")


def retire(*, path: Path, branch: str, base: str, repo_dir: Path | None = None) -> Retirement:
    """Remove a worktree when nothing in it would be lost, and its branch when the branch is merged into ``base``."""
    repo = repo_dir or owning_repo(path)
    if repo is None:
        return Retirement("kept", f"cannot find the repository that owns {path}")
    base = base or "HEAD"
    assessment = assess(path=path, branch=branch, base=base, repo=repo)
    if assessment.keep:
        return Retirement("kept", assessment.keep)

    branch_tip = _rev(repo, f"refs/heads/{branch}") if branch else None
    if path.exists():
        removed = git(repo, "worktree", "remove", str(path))
        if removed is None or removed.returncode != 0:
            return Retirement("kept", f"git worktree remove failed: {_stderr(removed)}")

    reason = assessment.landed
    deleted = False
    if branch_tip is not None:
        if _merged(repo, branch_tip, base):
            done = git(repo, "branch", "-D", branch)
            deleted = done is not None and done.returncode == 0
            if not deleted:
                reason += f"; branch '{branch}' kept: {_stderr(done)}"
        else:
            reason += f"; branch '{branch}' kept: not merged into '{base}'"
    return Retirement("removed", reason, deleted)


def _stderr(done: subprocess.CompletedProcess[str] | None) -> str:
    if done is None:
        return "git could not be run"
    return done.stderr.strip() or f"exit {done.returncode}"


def _rev(cwd: Path, ref: str) -> str | None:
    done = git(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if done is None or done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _merged(repo: Path, sha: str, base: str) -> bool:
    done = git(repo, "merge-base", "--is-ancestor", sha, base)
    return done is not None and done.returncode == 0


def _pushed(repo: Path, sha: str) -> bool:
    done = git(repo, "for-each-ref", "--contains", sha, "--count=1", "--format=%(refname)", "refs/remotes")
    return done is not None and done.returncode == 0 and bool(done.stdout.strip())


__all__ = [
    "Assessment",
    "Retirement",
    "assess",
    "base_name",
    "git",
    "owning_repo",
    "retire",
]
