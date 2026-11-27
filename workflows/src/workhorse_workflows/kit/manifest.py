"""The repository manifest as the workflows read it: the typed document, or nothing when there is none to read."""
from __future__ import annotations

from pathlib import Path

from workhorse._vendor.stablemate_core.config import ConfigError
from workhorse._vendor.stablemate_core.manifest import read_manifest


def selects_skills(repo: Path) -> bool:
    """Whether the repo's agents.yml names any skill or pack for farrier to install."""
    try:
        manifest = read_manifest(repo)
    except ConfigError:
        return False
    return manifest is not None and bool(manifest.skills or manifest.packs)


__all__ = ["read_manifest", "selects_skills"]
