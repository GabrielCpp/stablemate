"""The stablemate base library — the library layer that ships as a wheel.

This package carries content, not logic: the workflows farrier registers and
workhorse runs, the scaffolds `farrier scaffold` applies, and the `stablemate/*`
skills that document the toolchain. The only code here is :func:`base_dir`, the
accessor that tells the tools where that content landed on disk — the same shape
as ``certifi.where()`` or the ``tzdata`` package.

The tools locate this layer with an *optional* import::

    try:
        from stablemate_library import base_dir
    except ImportError:
        base_dir = None  # no base layer installed; overlay-only, as before

They must never declare a hard dependency on it: this package depends on *them*
(see pyproject), so a dependency back would close a cycle.

Layering: the base is the lowest-precedence layer. A repo's configured overlay
library (``farrier config set-library``) shadows it name-for-name, so an overlay
can override any base skill, pack or workflow by defining one with the same id.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["base_dir"]

__version__ = "0.1.0"


def base_dir() -> Path:
    """Absolute path to the base library root.

    The returned directory is a library root in farrier's sense — it holds
    ``library/``, ``scaffolds/`` and ``workflows/`` — so it can be handed to the
    same resolution code that handles a configured overlay.
    """
    return Path(__file__).parent.resolve()
