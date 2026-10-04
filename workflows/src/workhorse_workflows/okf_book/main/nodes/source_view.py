"""The copy of a surface's product source the writer reads, so it reads exactly what the run measured.

The copy leaves out the tests, test doubles and fixtures no page may cite, and keeps each file at its
repository path. It lives in the working tree, where a confined writer in a linked worktree can still
read it, and its folder ignores itself, so git reports no change for it and the writer's turn cannot
commit it. A copy of the repository root leaves out the copy itself.
"""
from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from ostler.refs import is_test_source
from workhorse_workflows.okf_book.main.nodes.turn_budget import countable_files

VIEW_DIR = ".okf-book-source"


def source_view_folder(root: Path, source_folder: str) -> Path:
    """Where the copy of the repository's `source_folder` sits."""
    return root / VIEW_DIR / source_folder


def build_source_view(root: Path, source_folder: str) -> Path:
    """Copy the product files under `source_folder` afresh, and return the copy's folder."""
    folder = root / source_folder
    view = source_view_folder(root, source_folder)
    shutil.rmtree(view, ignore_errors=True)
    view.mkdir(parents=True)
    _ = (root / VIEW_DIR / ".gitignore").write_text("*\n", encoding="utf-8")
    for path in countable_files(folder):
        relative = path.relative_to(folder)
        if VIEW_DIR not in relative.parts and not is_test_source(relative.as_posix()):
            (view / relative).parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copy2(path, view / relative)
    return view


def turn_folder(root: Path, name: str) -> Path:
    """A folder of the working tree a confined turn can read, which git reports no change for. Its name starts with a dot, so no copied source folder shares it."""
    folder = root / VIEW_DIR / f".{name}"
    folder.mkdir(parents=True, exist_ok=True)
    _ = (root / VIEW_DIR / ".gitignore").write_text("*\n", encoding="utf-8")
    return folder


def kept_for_turn(root: Path, name: str, files: Sequence[Path]) -> tuple[Path, ...]:
    """Copy each of *files* into the turn's folder and return where each copy sits. A file that does not exist is left out of the folder, and its copy's path is still returned."""
    folder = turn_folder(root, name)
    copies = tuple(folder / path.name for path in files)
    for path, copy in zip(files, copies, strict=True):
        if path.is_file():
            _ = shutil.copy2(path, copy)
    return copies
