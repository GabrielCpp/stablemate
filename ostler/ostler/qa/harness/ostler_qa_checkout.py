"""The copy of the checkout a scenario's commands run in.

Git keeps the app's own files, which each scenario gets a fresh copy of. It ignores
dependency folders, build output and local data, which the copy links to instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path


def _kept_and_ignored_paths(root: Path) -> tuple[list[str], list[str]] | None:
    """The paths git keeps under `root` and the ignored ones, or None when `root` is no git checkout."""
    git = shutil.which("git")
    if git is None:
        return None
    listings: list[list[str]] = []
    for flags in (["--cached", "--others"], ["--others", "--ignored", "--directory"]):
        try:
            done = subprocess.run(
                [git, "-C", str(root), "ls-files", "-z", "--exclude-standard", *flags],
                capture_output=True, check=False,
            )
        except OSError:
            return None
        if done.returncode != 0:
            return None
        listings.append(list(dict.fromkeys(n for n in done.stdout.decode().split("\0") if n)))
    return listings[0], _outermost(listings[1])


def _outermost(names: list[str]) -> list[str]:
    """The entries no listed directory already holds, since git can name a directory and its files both."""
    kept: list[str] = []
    for name in sorted(names):
        if not (kept and kept[-1].endswith("/") and name.startswith(kept[-1])):
            kept.append(name)
    return kept


def _ignore_git_and_qa_dir(qa_dir: Path) -> Callable[[str, list[str]], set[str]]:
    """A copytree filter that leaves out `.git` and the QA dir."""

    def skipped(where: str, names: list[str]) -> set[str]:
        here = Path(where)
        return {name for name in names if name == ".git" or (here / name).resolve() == qa_dir}

    return skipped


def _copy_entry(source: Path, target: Path, qa_dir: Path) -> None:
    """Copy one listed path: a link as a link, a nested checkout as a tree, a file as a file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        target.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True, ignore=_ignore_git_and_qa_dir(qa_dir), dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def copy_checkout(root: Path, qa_dir: Path, into: Path) -> None:
    """Copy what git keeps under `root` into `into` and link what it ignores, or copy the whole tree outside a git checkout.

    Linking the ignored entries lets a command find what the runbook built without
    paying for a copy of each, so a scenario world costs the app's own files rather
    than the whole disk. Nothing under `qa_dir` is copied or linked.
    """
    shutil.rmtree(into, ignore_errors=True)
    listed = _kept_and_ignored_paths(root) if root.is_dir() else None
    if listed is None:
        if root.is_dir():
            shutil.copytree(root, into, symlinks=True, ignore=_ignore_git_and_qa_dir(qa_dir))
        into.mkdir(parents=True, exist_ok=True)
        return
    kept, ignored = listed
    into.mkdir(parents=True, exist_ok=True)
    for name in kept:
        source = root / name
        if os.path.lexists(source) and not source.is_relative_to(qa_dir):
            _copy_entry(source, into / name, qa_dir)
    for name in ignored:
        source = root / name
        if not source.is_relative_to(qa_dir):
            (into / name).parent.mkdir(parents=True, exist_ok=True)
            (into / name).symlink_to(source)
