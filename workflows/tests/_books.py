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


SHARED_FILES = ("services/shared/accounts.py", "services/shared/answers.py")
IMPORTS_SHARED = "from ..shared.accounts import ACCOUNTS\nfrom services.shared.answers import ANSWER\n"
BYTECODE = ("services/{name}/__pycache__/service.cpython-312.pyc", "services/shared/__pycache__/accounts.cpython-312.pyc")


def import_shared(root: Path, name: str) -> tuple[str, ...]:
    """Make the book `services/<name>` of *root* import a shared folder, and leave compiled files under both folders. Returns the shared files, relative to *root*."""
    book = root / "services" / name
    book.mkdir(parents=True, exist_ok=True)
    (book / "service.py").write_text(IMPORTS_SHARED, encoding="utf-8")
    for rel in SHARED_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("ACCOUNTS = ANSWER = 1\n", encoding="utf-8")
    for rel in BYTECODE:
        target = root / rel.format(name=name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x00")
    return SHARED_FILES


def write_todo_book(root: Path) -> None:
    """The executable todo book of ostler's own fixtures, as `services/api/` of *root*; its pointers name `app.py`."""
    shutil.copytree(TODO_BOOK / "services", root / "services", ignore=shutil.ignore_patterns("__pycache__"))
