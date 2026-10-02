"""Which files under a book folder belong to the book: none inside a hidden folder, where tools keep their own state."""
from __future__ import annotations

from pathlib import Path


def in_hidden_folder(path: Path, folder: Path) -> bool:
    """Whether *path* sits inside a hidden folder somewhere below *folder*."""
    return any(part.startswith(".") for part in path.relative_to(folder).parts[:-1])


def files_in_book(folder: Path, suffixes: tuple[str, ...] = (".md",)) -> list[Path]:
    """Every file under *folder* with one of *suffixes*, sorted, skipping hidden folders without entering them."""
    found: list[Path] = []
    for directory, subdirs, files in folder.walk():
        subdirs[:] = [name for name in subdirs if not name.startswith(".")]
        found.extend(directory / name for name in files if name.endswith(suffixes))
    return sorted(found)
