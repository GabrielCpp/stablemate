"""Helpers for the workhorse integration."""

from __future__ import annotations

import os
import stat
from pathlib import Path

WORKHORSE_DIR = ".workhorse"


def write_private(path: Path | str, text: str) -> Path:
    """Write ``text`` to ``path`` with ``0600`` permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    owner_only = stat.S_IRUSR | stat.S_IWUSR
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, owner_only)
    os.fchmod(fd, owner_only)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
