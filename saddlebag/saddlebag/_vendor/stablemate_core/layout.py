"""What a library directory looks like on disk."""

from __future__ import annotations

from pathlib import Path


def is_library_dir(path: Path) -> bool:
    """A usable library root holds ``library/`` — the skills and prompts."""
    return (path / "library").is_dir()
