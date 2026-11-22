"""`ostler book branch` and `ostler book land`: the book branch of a code branch, opened and landed in the artifacts repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ostler._vendor.stablemate_core import book_branch, books, config, worktree
from ostler._vendor.stablemate_core.manifest import load_manifest, locate_manifest


def cmd_branch(args: argparse.Namespace, start: Path) -> int:
    try:
        if books.book_in_repo(start):
            print(books.book_home(start))
            return 0
        name = args.branch or _head(start)
        if name:
            _refuse_base(start, name)
        print(book_branch.open_book_branch(start, name))
    except config.ConfigError as refused:
        print(f"error: {refused}", file=sys.stderr)
        return 2
    return 0


def cmd_land(args: argparse.Namespace, start: Path) -> int:
    try:
        name = args.branch or _head(start)
        if not name:
            raise config.ConfigError(f"cannot land a book branch for {start}: it is on a detached HEAD")
        if books.book_in_repo(start):
            print(f"nothing {name}: the book rides the code's branch")
            return 0
        landing, retired = book_branch.close_book_branch(name)
    except config.ConfigError as refused:
        print(f"error: {refused}", file=sys.stderr)
        return 2
    top = config.artifacts_toplevel()
    base = _head(top) if top is not None else None
    print(f"{landing.action} {name} on '{base}': {landing.reason}")
    for file in landing.files:
        print(f"  {file}")
    if retired is not None and retired.action == "kept":
        print(f"kept the worktree: {retired.reason}")
    return 0 if landing.action in ("landed", "rebased", "nothing") else 1


def _refuse_base(start: Path, name: str) -> None:
    top = config.artifacts_toplevel()
    if top is not None and _inside(start, top):
        raise config.ConfigError(f"{start} is inside the artifacts repository, which is not a code branch with a book branch")
    if name == _base_of(start):
        raise config.ConfigError(
            f"'{name}' is the base branch of this repository, so a change on it commits its book on the artifacts base"
        )


def _base_of(start: Path) -> str | None:
    folder = config.repository_identity(start).folder
    found = locate_manifest(folder)
    declared = load_manifest(found).repo.base_branch if found is not None else None
    if declared:
        return declared
    for candidate in ("main", "master"):
        if _line(folder, "rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}"):
            return candidate
    return None


def _inside(start: Path, top: Path) -> bool:
    resolved = start.resolve()
    return resolved == top.resolve() or top.resolve() in resolved.parents


def _head(folder: Path) -> str | None:
    return _line(folder, "symbolic-ref", "--quiet", "--short", "HEAD")


def _line(folder: Path, *args: str) -> str | None:
    done = worktree.git(folder, *args)
    return (done.stdout.strip() or None) if done is not None and done.returncode == 0 else None
