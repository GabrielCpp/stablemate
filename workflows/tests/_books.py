"""A Python service book on disk: the folder an author's repo holds under `services/`."""

from __future__ import annotations

from pathlib import Path


def write_book(root: Path, name: str, *, screens: bool = False) -> None:
    book = root / "services" / name
    book.mkdir(parents=True, exist_ok=True)
    (book / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")
    if screens:
        (book / "screens").mkdir(exist_ok=True)
        (book / "screens" / "__init__.py").write_text("", encoding="utf-8")
