"""Scratch that belongs to a machine, not to a repo."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from workhorse._vendor.stablemate_core.base_cache import cache_root

SCRATCH_DIRNAME = "scratch"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(subject: Path) -> str:
    """A readable, collision-free directory name for an absolute path."""
    resolved = Path(subject).resolve()
    name = _UNSAFE.sub("-", resolved.name).strip("-") or "root"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:10]
    return f"{name}-{digest}"


def scratch_dir(kind: str, subject: Path | str) -> Path:
    """Create and return this machine's scratch directory for `kind` over `subject`."""
    path = cache_root() / SCRATCH_DIRNAME / kind / _slug(Path(subject))
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ["SCRATCH_DIRNAME", "scratch_dir"]
