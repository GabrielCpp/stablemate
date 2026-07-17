"""Finding the base library. One resolution order, shared by every tool.

This was ~40 near-identical lines in workhorse's ``main.py`` and farrier's ``layers.py``,
each with its own copy of the predicate and a comment admitting the copy. They must not
disagree: a base one tool can see and the other cannot is indistinguishable, from the
outside, from the library being broken.
"""

from __future__ import annotations

import os
from pathlib import Path

from stablemate_core import base_cache
from stablemate_core.config import get_config_value
from stablemate_core.layout import is_library_dir

__all__ = ["BASE_DIR_ENV", "CHECKOUT_SUBPATH", "base_library_dir", "is_library_dir"]

# An explicit on-disk path. The highest-precedence route, and the one that makes a base
# reachable from a tool installed in its own isolated pipx venv.
BASE_DIR_ENV = "STABLEMATE_BASE_DIR"

# Where the library sits inside a stablemate checkout. The base library is data laid out
# directly under this directory — `library/`, `scaffolds/`, `workflows/` — not nested in
# a Python package.
CHECKOUT_SUBPATH = "base-library"


def base_library_dir() -> Path | None:
    """The base library root, or None when it cannot be located.

    Resolution order, highest precedence first:

    1. ``$STABLEMATE_BASE_DIR`` — an explicit path to the content on disk.
    2. The ``base_dir`` key in the shared config (``<tool> config set-base <path>``) —
       the persisted form of that same override.
    3. Derived from a configured ``stablemate_dir`` checkout (``<checkout>/base-library``),
       for running against a source tree.
    4. The shared cache, fetched from git on first use.

    LOOKUP ONLY — never fetches. A resolution that downloads 16M as a side effect is a
    trap: ``config show`` would trigger it, and so would any test that resolves a path.
    Populating the cache is an explicit ``ensure_cached_base()`` call, made where a
    missing library is the actual problem.

    The cache is deliberately last: routes 1-3 each name a base a human chose, and a
    downloaded copy must never shadow a checkout someone is editing.

    Discovery, never a declared dependency. The base is data with no package to import —
    there is nothing here that could make a tool depend on library content, which is what
    keeps content versioning on its own clock. With none of the above resolving, a tool
    behaves exactly as it did before a base existed: overlay-only. A configured-but-invalid
    override is skipped rather than raised on — the base is additive, and failing soft
    keeps an overlay-only setup working.
    """
    env = os.environ.get(BASE_DIR_ENV)
    if env:
        candidate = Path(env).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    configured = get_config_value("base_dir")
    if isinstance(configured, str) and configured:
        candidate = Path(configured).expanduser()
        if is_library_dir(candidate):
            return candidate.resolve()

    checkout = get_config_value("stablemate_dir")
    if isinstance(checkout, str) and checkout:
        candidate = Path(checkout).expanduser() / CHECKOUT_SUBPATH
        if is_library_dir(candidate):
            return candidate.resolve()

    # Called through the module rather than a `from ... import cached_base` binding: a
    # direct binding is frozen at import, so patching base_cache.cached_base would not
    # affect this call and a test would silently exercise the real cache instead.
    cached = base_cache.cached_base()
    if cached is not None and is_library_dir(cached):
        return cached.resolve()

    return None
