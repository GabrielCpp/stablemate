"""The repository manifest as the workflows read it: the typed document, or nothing when there is none to read."""
from __future__ import annotations

from workhorse._vendor.stablemate_core.manifest import read_manifest

__all__ = ["read_manifest"]
