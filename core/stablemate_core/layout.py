"""What a library directory looks like on disk.

Its own module so ``base_cache`` and ``discovery`` can both use it without importing
each other (discovery reads the cache; the cache validates what it fetched).
"""

from __future__ import annotations

from pathlib import Path


def is_library_dir(path: Path) -> bool:
    """A usable library root holds content: ``library/`` (skills, prompts) or ``workflows/``.

    ``packs/`` is deliberately *not* required. The base library ships workflows,
    scaffolds and the stablemate skills with no packs at all — a repo selects from it
    directly in ``agents.yml`` (``skills: [stablemate/*]``), and packs remain a
    convenience an overlay may add.
    """
    return (path / "library").is_dir() or (path / "workflows").is_dir()
