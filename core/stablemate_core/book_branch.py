"""Opening a book branch as a worktree of the artifacts repository, and landing it on the artifacts base."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from platformdirs import user_data_dir

from . import books, config, worktree


@dataclass(frozen=True, slots=True)
class Landing:
    """What landing a book branch did."""

    action: Literal["nothing", "landed", "rebased", "conflict", "kept"]
    reason: str = ""
    files: tuple[str, ...] = ()


def book_worktree_path(branch: str) -> Path:
    """Where the worktree of *branch* in the artifacts repository goes."""
    top = config.artifacts_toplevel() or config.resolve_artifacts_dir()
    root = config.resolve_worktree_dir() or Path(user_data_dir("stablemate")) / "worktrees"
    return root / f"{top.name}-{branch.replace('/', '-')}"


def land(repo: Path, path: Path, branch: str, base: str) -> Landing:
    """Land *branch* on *base* checked out in *repo*, rebasing it in *path* first when *base* moved on."""
    tip = _rev(repo, f"refs/heads/{branch}")
    if tip is None:
        if not path.exists():
            return Landing("nothing", f"'{branch}' is gone, landed earlier")
        return Landing("kept", f"branch '{branch}' is gone")
    if _succeeds(repo, "merge-base", "--is-ancestor", tip, base):
        return Landing("nothing", f"'{branch}' has no commit beyond '{base}'")
    checked_out = _head(repo) or ""
    if checked_out != base:
        return Landing("kept", f"{repo} has '{checked_out or 'a detached HEAD'}' checked out, not '{base}'")
    rebased = False
    if not _succeeds(repo, "merge-base", "--is-ancestor", base, branch):
        if not path.is_dir():
            return Landing("kept", "the worktree is gone")
        done = worktree.git(path, "rebase", "--quiet", base)
        if done is None or done.returncode != 0:
            listed = worktree.git(path, "diff", "--name-only", "--diff-filter=U")
            files = tuple(listed.stdout.split()) if listed is not None else ()
            worktree.git(path, "rebase", "--abort")
            if files:
                return Landing("conflict", f"rebasing '{branch}' onto '{base}' conflicts", files)
            return Landing("kept", _stderr(done))
        rebased = True
    merged = worktree.git(repo, "merge", "--ff-only", "--quiet", branch)
    if merged is None or merged.returncode != 0:
        return Landing("kept", _stderr(merged))
    how = "rebased onto and " if rebased else ""
    return Landing("rebased" if rebased else "landed", f"'{branch}' {how}fast-forwarded '{base}'")


def open_book_branch(start: Path, branch: str | None = None) -> Path:
    """The book root for *branch*, cutting a worktree of the artifacts repository on it when none exists."""
    if books.book_in_repo(start):
        return books.book_home(start)
    artifacts = config.ensure_artifacts_repo()
    top = config.artifacts_toplevel()
    if top is None:
        return artifacts
    name = branch or _head(start)
    if not name:
        raise config.ConfigError(f"cannot open a book branch for {start}: it is on a detached HEAD")
    relative = artifacts.relative_to(top)
    base = _head(top)
    if name == base:
        return artifacts
    existing = config.checkout_on(top, name)
    if existing != top:
        return existing / relative
    target = book_worktree_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if _succeeds(top, "show-ref", "--verify", "--quiet", f"refs/heads/{name}"):
        args = ["worktree", "add", "--quiet", str(target), name]
    else:
        args = ["worktree", "add", "--quiet", "-b", name, str(target), base or "HEAD"]
    done = worktree.git(top, *args)
    if done is None or done.returncode != 0:
        raise config.ConfigError(f"git {' '.join(args)} failed in {top}: {_stderr(done)}")
    return target.resolve() / relative


def close_book_branch(branch: str) -> tuple[Landing, worktree.Retirement | None]:
    """Land *branch* on the artifacts base, then retire its worktree and branch when the landing allows it."""
    top = config.artifacts_toplevel()
    if top is None:
        raise config.ConfigError("the artifacts folder is not a git repository, so there is no book branch to land")
    base = _head(top)
    if not base:
        raise config.ConfigError(f"{top} is on a detached HEAD, so nothing can land on it")
    found = config.checkout_on(top, branch)
    path = found if found != top else top / ".stablemate-no-book-worktree" / branch
    landing = land(top, path, branch, base)
    if landing.action in ("landed", "rebased", "nothing"):
        return landing, worktree.retire(path=path, branch=branch, base=base, repo_dir=top)
    return landing, None


def _head(folder: Path) -> str | None:
    done = worktree.git(folder, "symbolic-ref", "--quiet", "--short", "HEAD")
    if done is None or done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _rev(repo: Path, ref: str) -> str | None:
    done = worktree.git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return done.stdout.strip() or None if done is not None and done.returncode == 0 else None


def _succeeds(repo: Path, *args: str) -> bool:
    return getattr(worktree.git(repo, *args), "returncode", 1) == 0


def _stderr(done: subprocess.CompletedProcess[str] | None) -> str:
    return "git could not be run" if done is None else done.stderr.strip() or f"exit {done.returncode}"
