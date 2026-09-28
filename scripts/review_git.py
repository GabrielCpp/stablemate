"""The git reads the review gate makes, none of which touch the live index."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path


def git(repo: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def git_path(repo: Path, name: str) -> Path:
    return repo / git(repo, "rev-parse", "--git-path", name)


def _succeeds(repo: Path, *args: str) -> bool:
    probe = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    return probe.returncode == 0


def tree_exists(repo: Path, tree: str) -> bool:
    return _succeeds(repo, "cat-file", "-e", f"{tree}^{{tree}}")


def is_ancestor(repo: Path, commit: str, head: str) -> bool:
    return _succeeds(repo, "merge-base", "--is-ancestor", commit, head)


def snapshot_tree(repo: Path) -> str:
    with tempfile.TemporaryDirectory() as scratch:
        index = Path(scratch) / "index"
        live_index = git_path(repo, "index")
        if live_index.is_file():
            shutil.copy2(live_index, index)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        git(repo, "add", "-A", env=env)
        return git(repo, "write-tree", env=env)


def first_parent_commits(repo: Path, since: str, head: str) -> list[str]:
    return git(repo, "rev-list", "--reverse", "--first-parent", f"{since}..{head}").split()
