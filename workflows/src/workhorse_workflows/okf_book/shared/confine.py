"""What a writer's turn changed in the tree, read from git before and after it.

A turn may write only under `docs/`. Code keeps each change inside the service's book, and puts
back every other path the turn changed.
"""
from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

_GIT_TIMEOUT = 60


class Snapshot(BaseModel):
    """Each path git reports as changed or untracked, mapped to the sha256 of its content, empty when it is gone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    digests: dict[str, str]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=_GIT_TIMEOUT
    ).stdout


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def snapshot(root: Path) -> Snapshot:
    listed = _git(root, "status", "--porcelain", "-uall", "--no-renames", "-z").split("\0")
    paths = [entry[3:] for entry in listed if len(entry) > 3]
    return Snapshot(digests={path: _digest(root / path) for path in paths})


def changed_since(root: Path, before: Snapshot) -> tuple[str, ...]:
    """Every path whose content differs from what `before` recorded, sorted."""
    after = snapshot(root)
    paths = set(before.digests) | set(after.digests)
    return tuple(sorted(p for p in paths if before.digests.get(p) != after.digests.get(p)))


def _tracked(root: Path, path: str) -> bool:
    return bool(_git(root, "ls-tree", "--name-only", "HEAD", "--", path).strip())


def restore(root: Path, paths: Iterable[str], before: Snapshot) -> tuple[str, ...]:
    """Put each path back as HEAD has it. A path that was already dirty before the turn is left, and returned."""
    left: list[str] = []
    for path in paths:
        if path in before.digests:
            left.append(path)
        elif _tracked(root, path):
            _ = _git(root, "checkout", "HEAD", "--", path)
        else:
            (root / path).unlink(missing_ok=True)
    return tuple(left)


def in_book(service: str, path: str) -> bool:
    """True for a path in the service's book."""
    return path.startswith(f"{(FEATURES_DIR / service).as_posix()}/")


def book_changes(root: Path, service: str, before: Snapshot) -> tuple[str, ...]:
    """The paths inside the service's book whose content changed since `before`."""
    return tuple(path for path in changed_since(root, before) if in_book(service, path))


def _is_under(root: Path, path: str, folder: Path) -> bool:
    return (root / path).resolve().is_relative_to(folder.resolve())


def put_back_outside(root: Path, service: str, before: Snapshot, run_dir: Path) -> tuple[str, ...]:
    """Restore every path the turn changed outside the service's book, the run's own directory aside, and return them."""
    stray = tuple(
        path for path in changed_since(root, before) if not in_book(service, path) and not _is_under(root, path, run_dir)
    )
    _ = restore(root, stray, before)
    return stray
