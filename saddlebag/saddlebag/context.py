"""Ambient context inferred from where saddlebag is run."""

from __future__ import annotations

from pathlib import Path


def infer_project(start: Path | str | None = None) -> str | None:
    """The project saddlebag operates in by default."""
    path = (Path(start) if start is not None else Path.cwd()).resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent.name or None
    return path.name or None
