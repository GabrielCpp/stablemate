"""A run's name, and the folders it owns under a benchmark root."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from paddock import paths

SHA_WIDTH = 12


@dataclass(frozen=True, slots=True)
class RunName:
    """`<benchmark>/<task>/<data commit>-<stablemate sha>/<n>`."""

    benchmark: str
    task: str
    data_commit: str
    stablemate: str
    n: int

    @property
    def key(self) -> str:
        return f"{self.data_commit[:SHA_WIDTH]}-{self.stablemate[:SHA_WIDTH]}"

    def relative(self) -> Path:
        return Path(self.benchmark, self.task, self.key, str(self.n))

    def __str__(self) -> str:
        return self.relative().as_posix()


def git_head(repo: Path) -> str:
    """HEAD of the repository at *repo*, or `""` when it is not one or has no commit."""
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def repo_children(data: Path) -> list[Path]:
    """The visible child directories of *data*, sorted by name."""
    if not data.is_dir():
        return []
    return sorted(child for child in data.iterdir() if child.is_dir() and not child.name.startswith("."))


def data_commit(data: Path) -> str:
    """HEAD of *data*, or a digest of each child repository's HEAD, or `""` when any has no commit."""
    if (data / ".git").exists():
        return git_head(data)
    children = repo_children(data)
    if not children:
        return ""
    lines = []
    for child in children:
        head = git_head(child)
        if not head:
            return ""
        lines.append(f"{child.name} {head}\n")
    return hashlib.sha1("".join(lines).encode("utf-8")).hexdigest()


def workspace_dir(root: Path, name: RunName) -> Path:
    return root / paths.WORKSPACE / name.relative()


def result_dir(root: Path, name: RunName) -> Path:
    return root / paths.RESULTS / name.relative()


def _taken(root: Path, name: RunName) -> int:
    highest = 0
    for tree in (paths.WORKSPACE, paths.RESULTS):
        parent = (root / tree / name.relative()).parent
        if parent.is_dir():
            highest = max([highest, *(int(p.name) for p in parent.iterdir() if p.name.isdigit())])
    return highest


def reserve(root: Path, name: RunName) -> RunName:
    """*name* with the next unused `n`, its workspace folder created."""
    n = _taken(root, name) + 1
    while True:
        claimed = RunName(name.benchmark, name.task, name.data_commit, name.stablemate, n)
        try:
            workspace_dir(root, claimed).mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            n += 1
            continue
        return claimed
