"""The repository manifest as ostler reads it: the typed document, or nothing when there is none to read."""

from __future__ import annotations

from pathlib import Path

from ostler._vendor.stablemate_core.manifest import (
    LEGACY_MANIFEST_NAMES,
    MANIFEST_NAME,
    load_manifest,
    locate_manifest,
)
from ostler._vendor.stablemate_core.schema import Manifest

MANIFEST_FILENAMES = (MANIFEST_NAME, *LEGACY_MANIFEST_NAMES)


def read_manifest(root: Path) -> Manifest | None:
    """The manifest directly in *root*, or ``None`` when there is none.

    A manifest that fails validation raises :class:`ConfigError` naming its key paths. A re-read
    of a file that broke after a good load keeps the last good document.
    """
    path = locate_manifest(root)
    if path is None:
        return None
    return load_manifest(path)
