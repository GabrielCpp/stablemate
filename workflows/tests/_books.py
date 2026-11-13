"""A Python service book on disk: the folder an author's repo holds under `services/`."""

from __future__ import annotations

import shutil
from pathlib import Path

import ostler

TODO_BOOK = Path(ostler.__file__).resolve().parent.parent / "tests" / "fixtures" / "book_todo"


def write_book(root: Path, name: str, *, screens: bool = False) -> None:
    book = root / "services" / name
    book.mkdir(parents=True, exist_ok=True)
    (book / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")
    if screens:
        (book / "screens").mkdir(exist_ok=True)
        (book / "screens" / "__init__.py").write_text("", encoding="utf-8")


def write_todo_book(root: Path) -> None:
    """The executable todo book of ostler's own fixtures, as `services/api/` of *root*; its pointers name `app.py`."""
    shutil.copytree(TODO_BOOK / "services", root / "services", ignore=shutil.ignore_patterns("__pycache__"))
