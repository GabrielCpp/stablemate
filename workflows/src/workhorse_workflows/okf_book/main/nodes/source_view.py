"""The folders of the working tree a confined turn reads beside its book: the files kept for a turn, under a folder that ignores itself.

Git reports no change for that folder, so a turn cannot commit what it holds.
"""
from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

VIEW_DIR = ".okf-book-source"


def turn_folder(root: Path, name: str) -> Path:
    """A folder of the working tree a confined turn can read, which git reports no change for."""
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
