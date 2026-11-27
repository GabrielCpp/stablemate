"""The per-repo context manifest: the repo's agents.yml, as render context."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workhorse._vendor.stablemate_core.config import ConfigError
from workhorse._vendor.stablemate_core.manifest import read_manifest

_REPO_ROOT = "_repo_root"


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class ManifestContext:
    """What a run carries: the manifest, resolved for this backend and this repo."""

    present: bool = False
    values: dict[str, Any] = field(default_factory=dict)
    repo_root: str = ""

    def as_context(self) -> dict[str, Any]:
        """The context layer a run lays under every agent turn's arguments."""
        if not self.present:
            return {}
        ctx: dict[str, Any] = dict(self.values)
        ctx[_REPO_ROOT] = self.repo_root
        return ctx

    @classmethod
    def from_context(cls, context: Mapping[str, Any]) -> ManifestContext:
        """Read the manifest half back out of a render context."""
        return cls(
            present=_REPO_ROOT in context,
            repo_root=_text(context.get(_REPO_ROOT)),
        )


def load_context_manifest() -> ManifestContext:
    """Read the agents.yml of the repo at AGENT_REPO_DIR (else cwd) as the context library prompts render against."""
    repo_dir = Path(os.environ.get("AGENT_REPO_DIR") or ".")
    try:
        manifest = read_manifest(repo_dir)
    except ConfigError:
        return ManifestContext()
    if manifest is None:
        return ManifestContext()
    template = manifest.template.mapping()
    repo = {**manifest.repo.mapping(), "root": "."}
    values = {
        key: value
        for key, value in (("template", template), ("repo", repo), ("vars", template))
        if value
    }
    return ManifestContext(present=True, values=values, repo_root=str(repo_dir.resolve()))


__all__ = [
    "ManifestContext",
    "load_context_manifest",
]
