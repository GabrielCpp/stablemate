"""The copy of a surface's product source the writer reads, so it reads exactly what the run measured.

The copy leaves out the tests, test doubles and fixtures no page may cite, and keeps each file at its
repository path. It lives in the repository's git folder, so git reports no change for it and the
writer's turn cannot commit it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ostler.refs import is_test_source
from workhorse_workflows.kit import open_repo
from workhorse_workflows.okf_book.main.nodes.turn_budget import countable_files

VIEW_DIR = "okf-book-source"


def source_view_folder(root: Path, source_folder: str) -> Path:
    """Where the copy of the repository's `source_folder` sits."""
    return Path(open_repo(root).git_dir) / VIEW_DIR / source_folder


def build_source_view(root: Path, source_folder: str) -> Path:
    """Copy the product files under `source_folder` afresh, and return the copy's folder."""
    folder = root / source_folder
    view = source_view_folder(root, source_folder)
    shutil.rmtree(view, ignore_errors=True)
    view.mkdir(parents=True)
    for path in countable_files(folder):
        relative = path.relative_to(folder)
        if not is_test_source(relative.as_posix()):
            (view / relative).parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copy2(path, view / relative)
    return view
