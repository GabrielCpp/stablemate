"""Finding the base library."""

from __future__ import annotations

import os
from pathlib import Path

from . import base_cache
from .config import load_home_config
from .layout import is_library_dir

__all__ = [
    "BASE_DIR_ENV",
    "CHECKOUT_SUBPATH",
    "base_library_dir",
    "ensure_base_library_dir",
    "is_library_dir",
]

BASE_DIR_ENV = "STABLEMATE_BASE_DIR"

CHECKOUT_SUBPATH = "base-library"


def base_library_dir() -> Path | None:
    """The base library root, or None when it cannot be located."""
    explicit = _explicit_base()
    if explicit is not None:
        return explicit

    cached = base_cache.cached_base()
    if cached is not None and is_library_dir(cached):
        return cached.resolve()

    return None


def _explicit_base() -> Path | None:
    """Routes 1-3 only: a base some human named."""
    env = os.environ.get(BASE_DIR_ENV)
    if env:
        candidate = Path(env).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    home = load_home_config()
    if home.base_dir:
        candidate = Path(home.base_dir).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    if home.stablemate_dir:
        candidate = Path(home.stablemate_dir).expanduser() / CHECKOUT_SUBPATH
        if is_library_dir(candidate):
            return candidate.resolve()

    return None


def ensure_base_library_dir(*, ref: str, refresh: bool = False, quiet: bool = False) -> Path | None:
    """:func:`base_library_dir`, but allowed to populate the cache at ``ref`` — and, with ``refresh``, to move it there."""
    explicit = _explicit_base()
    if explicit is not None:
        return explicit

    fetch = base_cache.refresh_cached_base if refresh else base_cache.ensure_cached_base
    cached = fetch(ref=ref, quiet=quiet)
    if cached is not None and is_library_dir(cached):
        return cached.resolve()
    return None
