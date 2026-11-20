"""Mirror the base library farrier ships into a shared cache, so every tool and venv sees one copy."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from platformdirs import user_cache_dir

from .layout import is_library_dir

logger = logging.getLogger(__name__)

BASE_SUBPATH = "base-library"

STAMP_FILE = ".digest"

CACHE_DIR_ENV = "STABLEMATE_CACHE_DIR"


def cache_root() -> Path:
    """The shared cache dir."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(user_cache_dir("stablemate"))


def cached_library_dir() -> Path:
    return cache_root() / "library"


def cached_stamp(clone: Path | None = None) -> str | None:
    """The digest of the base the cache holds, or None."""
    root = clone or cached_library_dir()
    try:
        return (root / STAMP_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def cached_base() -> Path | None:
    """The cached base library if already on disk AND usable, else None."""
    base = cached_library_dir() / BASE_SUBPATH
    return base if is_library_dir(base) else None


def mirror_base(source: Path, *, stamp: str, quiet: bool = False) -> Path | None:
    """Make the cache hold ``source``, stamped ``stamp``, and return the cached base."""
    existing = cached_base()
    if existing is not None and cached_stamp() == stamp:
        return existing
    if not is_library_dir(source):
        logger.warning("the base library to mirror at %s holds no library/", source)
        return existing

    clone = cached_library_dir()
    clone.parent.mkdir(parents=True, exist_ok=True)
    tmp = clone.parent / f".library-mirror-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        shutil.copytree(
            source, tmp / BASE_SUBPATH, ignore=shutil.ignore_patterns("__pycache__")
        )
        (tmp / STAMP_FILE).write_text(f"{stamp}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("could not copy the base library into %s: %s", clone, exc)
        shutil.rmtree(tmp, ignore_errors=True)
        return existing

    superseded = clone.parent / f".library-old-{os.getpid()}"
    shutil.rmtree(superseded, ignore_errors=True)
    try:
        if clone.exists():
            clone.rename(superseded)
        tmp.rename(clone)
    except OSError as exc:
        logger.warning("could not swap the base library into %s: %s", clone, exc)
        shutil.rmtree(tmp, ignore_errors=True)
        if superseded.is_dir() and not clone.exists():
            superseded.rename(clone)
        return cached_base() or existing
    shutil.rmtree(superseded, ignore_errors=True)

    if not quiet:
        print(f"[stablemate] base library mirrored to {clone} ({stamp[:12]})")
    return cached_base()
