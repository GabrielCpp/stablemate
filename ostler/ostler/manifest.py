"""The repository manifest as ostler reads it: the typed document, or nothing when there is none to read."""

from __future__ import annotations

from ostler._vendor.stablemate_core.manifest import (
    LEGACY_MANIFEST_NAMES,
    MANIFEST_NAME,
    read_manifest,
)

MANIFEST_FILENAMES = (MANIFEST_NAME, *LEGACY_MANIFEST_NAMES)


__all__ = ["MANIFEST_FILENAMES", "read_manifest"]
