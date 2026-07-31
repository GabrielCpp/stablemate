"""What a library directory looks like on disk.

Its own module so ``base_cache`` and ``discovery`` can both use it without importing
each other (discovery reads the cache; the cache validates what it fetched).
"""

from __future__ import annotations

from pathlib import Path


def is_library_dir(path: Path) -> bool:
    """A usable library root holds ``library/`` — the skills and prompts.

    It used to accept ``workflows/`` as an alternative, back when a workflow was a
    directory of YAML a library could ship. A workflow is a Python package now, resolved
    through the ``workhorse.workflows`` entry-point group, so a directory holding only
    ``workflows/`` is not a library — it is a directory of something else.

    ``packs/`` is deliberately *not* required. The base library ships scaffolds and the
    stablemate skills with no packs at all — a repo selects from it directly in
    ``agents.yml`` (``skills: [stablemate/*]``), and packs remain a convenience an
    overlay may add.
    """
    return (path / "library").is_dir()
