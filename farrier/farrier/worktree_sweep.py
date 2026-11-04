"""`farrier worktrees`: find the linked worktrees agents left behind and remove the ones that are safe to lose."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from farrier._vendor.stablemate_core.worktree import assess, base_name, git, owning_repo, retire

SECONDS_PER_DAY = 86_400
PROC = Path("/proc")

Action = Literal["remove", "removed", "keep", "prune", "pruned"]


@dataclass(frozen=True, slots=True)
class Entry:
    """One linked worktree as `git worktree list --porcelain` reports it."""

    path: Path
    branch: str = ""
    locked: bool = False
    prunable: bool = False


@dataclass(frozen=True, slots=True)
class Row:
    """What the sweep decided about one worktree."""

    action: Action
    path: Path
    branch: str
    reason: str


def discover_repos(paths: Iterable[Path], worktree_dir: Path | None) -> list[Path]:
    """The repositories that own the given paths, each named once: a path is a checkout or a folder of checkouts."""
    candidates: list[Path] = []
    for path in paths:
        candidates.extend([path] if (path / ".git").exists() else _children(path))
    if worktree_dir is not None:
        candidates.extend(_children(worktree_dir))
    repos = (owning_repo(candidate) for candidate in candidates)
    return sorted({repo.resolve() for repo in repos if repo is not None})


def _children(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return [child for child in folder.iterdir() if (child / ".git").exists()]


def list_entries(repo: Path) -> list[Entry]:
    """The repository's linked worktrees, without the main checkout git always lists first."""
    done = git(repo, "worktree", "list", "--porcelain")
    if done is None or done.returncode != 0:
        return []
    return [_parse(block) for block in done.stdout.strip().split("\n\n")[1:]]


def _parse(block: str) -> Entry:
    fields = dict((line.split(" ", 1) + [""])[:2] for line in block.splitlines())
    return Entry(
        path=Path(fields["worktree"]),
        branch=fields.get("branch", "").removeprefix("refs/heads/"),
        locked="locked" in fields,
        prunable="prunable" in fields,
    )


def process_cwds(proc: Path = PROC) -> set[Path] | None:
    """Every working directory a process on this machine holds, or None where the platform cannot say."""
    if not proc.is_dir():
        return None
    cwds: set[Path] = set()
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                cwds.add(Path(os.readlink(entry / "cwd")))
            except OSError:
                continue
    return cwds


def last_touched(path: Path) -> float:
    """The newest change to the worktree's own git state: a checkout, a commit or a stage."""
    done = git(path, "rev-parse", "--absolute-git-dir")
    if done is None or done.returncode != 0:
        return float("inf")
    git_dir = Path(done.stdout.strip())
    stamps = [
        (git_dir / name).stat().st_mtime
        for name in ("HEAD", "index", "logs/HEAD")
        if (git_dir / name).exists()
    ]
    return max(stamps, default=float("inf"))


def _hold(entry: Entry, *, cwds: set[Path] | None, idle_days: int, now: float) -> str:
    """Why the sweep leaves this worktree alone before git is even asked whether it landed."""
    if entry.locked:
        return "locked"
    if cwds is None:
        return "cannot tell whether a process is using it on this platform"
    if any(cwd == entry.path or entry.path in cwd.parents for cwd in cwds):
        return "a running process is using it"
    idle = (now - last_touched(entry.path)) / SECONDS_PER_DAY
    if idle < idle_days:
        return f"touched less than {idle_days} days ago"
    return ""


def sweep_repo(
    repo: Path,
    *,
    apply: bool,
    idle_days: int,
    now: float,
    cwds: set[Path] | None,
) -> list[Row]:
    """Decide about every linked worktree of one repository, and act on the decisions when ``apply`` is set."""
    base = base_name(repo, "HEAD")
    rows: list[Row] = []
    stale = False
    for entry in list_entries(repo):
        if entry.prunable and not entry.locked:
            stale = True
            rows.append(Row("pruned" if apply else "prune", entry.path, entry.branch, "its folder is gone"))
            continue
        hold = _hold(entry, cwds=cwds, idle_days=idle_days, now=now)
        if hold:
            rows.append(Row("keep", entry.path, entry.branch, hold))
            continue
        if apply:
            done = retire(path=entry.path, branch=entry.branch, base=base, repo_dir=repo)
            action: Action = "removed" if done.action == "removed" else "keep"
            rows.append(Row(action, entry.path, entry.branch, done.reason))
            continue
        verdict = assess(path=entry.path, branch=entry.branch, base=base, repo=repo)
        if verdict.keep:
            rows.append(Row("keep", entry.path, entry.branch, verdict.keep))
        else:
            rows.append(Row("remove", entry.path, entry.branch, verdict.landed))
    if apply and stale:
        git(repo, "worktree", "prune")
    return rows


def format_row(row: Row) -> str:
    branch = f" [{row.branch}]" if row.branch else ""
    return f"{row.action:<8}{row.path}{branch}: {row.reason}"


__all__ = [
    "Entry",
    "Row",
    "discover_repos",
    "format_row",
    "last_touched",
    "list_entries",
    "process_cwds",
    "sweep_repo",
]
