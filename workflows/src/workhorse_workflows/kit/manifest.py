"""The repository manifest as the workflows read it: the typed document, or nothing when there is none to read."""
from __future__ import annotations

from pathlib import Path

from workhorse._vendor.stablemate_core.manifest import load_manifest, locate_manifest
from workhorse._vendor.stablemate_core.schema import Manifest


def read_manifest(root: str | Path) -> Manifest | None:
    """The manifest directly in *root*, or ``None`` when there is none.

    A manifest that fails validation raises :class:`ConfigError` naming its key paths. A re-read
    of a file that broke after a good load keeps the last good document.
    """
    path = locate_manifest(Path(root))
    if path is None:
        return None
    return load_manifest(path)


__all__ = ["read_manifest"]
