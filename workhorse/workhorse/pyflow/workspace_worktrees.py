"""Cutting the worktrees of every repository of a workspace run on one branch, and ending them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workhorse._vendor.stablemate_core import book_branch, books
from workhorse._vendor.stablemate_core import config as core_config
from workhorse._vendor.stablemate_core import worktree as shared
from workhorse.pyflow import worktree as worktree_mod
from workhorse.pyflow.worktree import WorktreeError
from workhorse.records import BookLanding, RunWorktree


@dataclass(frozen=True, slots=True)
class Planned:
    """One worktree a workspace run will cut."""

    name: str
    repo: Path
    target: Path
    base_ref: str
    books: bool


def plan(
    *,
    repo_dir: Path,
    workspace: str,
    worktree_dir: Path,
    sanitized: str,
    base_ref: str,
    create: bool = True,
) -> tuple[list[Planned], Path]:
    """The worktrees of the run's workspace, the invoking repository's first, and the folder `repo_dir` takes inside its worktree; empty when *repo_dir* belongs to no workspace and keeps its book in the repository or is the artifacts repository. A lone repository also gets the artifacts repository's worktree."""
    try:
        name = core_config.run_workspace(repo_dir, workspace)
    except ValueError as exc:
        raise WorktreeError(str(exc)) from exc
    lone = not name
    if lone and books.book_in_repo(repo_dir):
        return [], Path()
    if create:
        core_config.ensure_artifacts_repo()
    identity = core_config.repository_identity(repo_dir)
    rel = repo_dir.resolve().relative_to(identity.folder)
    artifacts = core_config.resolve_artifacts_dir()
    own = artifacts.is_dir() and core_config.repository_identity(artifacts).folder == artifacts
    if lone:
        checked = create or artifacts.is_dir()
        if (checked and not own) or identity.main_folder == artifacts:
            return [], Path()
        first_name = core_config.repository_name(repo_dir)
        return [
            Planned(first_name, identity.folder, worktree_dir / f"{first_name}-{sanitized}", base_ref, False),
            Planned(artifacts.name, artifacts, worktree_dir / f"{artifacts.name}-{sanitized}", "HEAD", True),
        ], rel
    members = core_config.resolve_workspace(name)

    first_name = artifacts.name if identity.main_folder == artifacts else core_config.repository_name(repo_dir)
    entries = [
        Planned(
            first_name,
            identity.folder,
            worktree_dir / f"{first_name}-{sanitized}",
            base_ref,
            own and identity.main_folder == artifacts,
        )
    ]
    seen = {identity.main_folder}
    if own and artifacts not in seen:
        seen.add(artifacts)
        entries.append(Planned(artifacts.name, artifacts, worktree_dir / f"{artifacts.name}-{sanitized}", "HEAD", True))
    for member in members:
        folder = member.path.resolve()
        if folder in seen:
            continue
        if not (folder / ".git").exists():
            print(f"[workhorse] worktree → skipped member '{member.name}': {folder} is not a git checkout")
            continue
        seen.add(folder)
        entries.append(Planned(member.name, folder, worktree_dir / f"{member.name}-{sanitized}", "HEAD", False))
    return entries, rel


def cut(planned: list[Planned], branch: str) -> list[RunWorktree]:
    """Cut every planned worktree on *branch*; a failure part way removes the ones already cut and their branches, then raises."""
    clashes = [
        f"{entry.target} (directory exists)" if entry.target.exists() else f"{entry.repo} (branch '{branch}' exists)"
        for entry in planned
        if entry.target.exists() or _has_branch(entry.repo, branch)
    ]
    if clashes:
        raise WorktreeError(f"cannot cut the run's worktrees: {', '.join(clashes)}")
    done: list[RunWorktree] = []
    for entry in planned:
        try:
            worktree_mod.add(
                repo_dir=entry.repo,
                worktree_dir=entry.target.parent,
                branch=branch,
                base_ref=entry.base_ref,
                dir_name=entry.target.name,
            )
        except WorktreeError as exc:
            undo(done)
            paths = ", ".join(item.path for item in done) or "nothing"
            raise WorktreeError(f"{exc}; removed {paths} and branch '{branch}' in each") from exc
        done.append(
            RunWorktree(
                name=entry.name,
                path=str(entry.target),
                branch=branch,
                repo=str(entry.repo),
                base=worktree_mod.base_name(entry.repo, entry.base_ref),
                books=entry.books,
            )
        )
    return done


def undo(entries: list[RunWorktree]) -> None:
    """Remove each worktree and delete its branch, newest first."""
    for entry in reversed(entries):
        shared.git(Path(entry.repo), "worktree", "remove", "--force", entry.path)
        shared.git(Path(entry.repo), "branch", "-D", entry.branch)


def _has_branch(repo: Path, branch: str) -> bool:
    return _succeeds(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")


def land(entry: RunWorktree) -> BookLanding:
    """Land the run's book branch on the artifacts base in its main folder."""
    landing = book_branch.land(Path(entry.repo), Path(entry.path), entry.branch, entry.base)
    return BookLanding(action=landing.action, reason=landing.reason, files=list(landing.files))


def end(entries: list[RunWorktree]) -> list[RunWorktree]:
    """On a terminal success, land the book branch, then retire each worktree."""
    ended: list[RunWorktree] = []
    for entry in entries:
        landing = land(entry) if entry.books else None
        if landing is not None and landing.action in ("conflict", "kept"):
            reason = landing.reason + (f": {', '.join(landing.files)}" if landing.files else "")
            outcome = worktree_mod.kept(reason)
        else:
            outcome = worktree_mod.retire(
                path=Path(entry.path),
                branch=entry.branch,
                base=entry.base,
                repo_dir=Path(entry.repo) if entry.repo else None,
            )
        ended.append(entry.model_copy(update={"landing": landing, "outcome": outcome}))
    return ended


def keep(entries: list[RunWorktree], reason: str) -> list[RunWorktree]:
    """Every worktree kept for *reason*."""
    return [entry.model_copy(update={"outcome": worktree_mod.kept(reason)}) for entry in entries]


def _succeeds(repo: Path, *args: str) -> bool:
    done = shared.git(repo, *args)
    return done is not None and done.returncode == 0
