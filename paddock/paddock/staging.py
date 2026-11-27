"""Staging a benchmark's data: clone its repositories into a round's workspace."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from paddock import names
from paddock.errors import RunError
from paddock.loader import Benchmark

logger = logging.getLogger(__name__)


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)


def clone_repo(data: Path, stage: Path) -> None:
    """Clone the repository *data* into *stage* at its HEAD, with no remote to push the round's work to."""
    if git("status", "--porcelain", cwd=data).stdout.strip():
        logger.warning("%s has uncommitted changes; the run copies its HEAD and will not see them", data)
    cloned = git("clone", "--quiet", "--no-hardlinks", str(data), str(stage), cwd=data.parent)
    if cloned.returncode != 0:
        raise RunError(f"could not copy {data} to {stage}: {cloned.stderr.strip()}")
    for remote in git("remote", cwd=stage).stdout.split():
        if git("remote", "remove", remote, cwd=stage).returncode != 0:
            raise RunError(f"could not strip remote {remote!r} from the copy of {data}")


def copy_data(data: Path, stage: Path) -> None:
    """Clone *data* into *stage*: one repository as is, a folder of repositories one per name."""
    if (data / ".git").exists():
        clone_repo(data, stage)
        return
    children = names.repo_children(data)
    stage.mkdir(parents=True)
    for child in children:
        clone_repo(child, stage / child.name)


def check_data(benchmark: Benchmark) -> None:
    """Refuse a `data/` that is neither a repository nor a folder of them."""
    data = benchmark.data
    if (data / ".git").exists():
        return
    for child in names.repo_children(data):
        if not (child / ".git").exists():
            raise RunError(f"benchmark {benchmark.name!r}: {child} is not a git repository")
