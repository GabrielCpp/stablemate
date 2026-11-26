"""Where farrier keeps one repository's generated machine state."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from farrier._vendor.stablemate_core.base_cache import farrier_state_dir, repo_state_name

CONTEXT_MANIFEST_FILE = "agents-context.json"
CONTEXT_MANIFEST_FILE_FMT = "agents-context.{}.json"


def repo_state_dir(repo: Path, repo_config: Mapping[str, Any] | None = None) -> Path:
    """The folder holding *repo*'s context manifests."""
    configured = (repo_config or {}).get("name")
    return farrier_state_dir(repo_state_name(repo, str(configured) if configured else None))
