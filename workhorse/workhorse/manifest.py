"""The per-repo context manifest: what farrier installed, as render context."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from workhorse._vendor.stablemate_core.base_cache import farrier_state_dir, repo_state_name
from workhorse._vendor.stablemate_core.config import ConfigError
from workhorse._vendor.stablemate_core.manifest import read_manifest
from workhorse._vendor.stablemate_core.profiles import resolve_default_cli

_REPO_ROOT = "_repo_root"


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


class ContextManifest(BaseModel):
    """The `agents-context.json` farrier writes into its per-repo state folder, as we read it."""

    model_config = ConfigDict(extra="ignore")

    template: dict[str, Any] = Field(default_factory=dict)
    repo: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)

    @field_validator("template", "repo", "vars", mode="before")
    @classmethod
    def _tolerate_mapping(cls, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def project(self, *, repo_root: Path) -> ManifestContext:
        """Project the file onto the render context for one repo, every path where farrier rendered it."""
        values = {
            key: value
            for key, value in (
                ("template", self.template),
                ("repo", self.repo),
                ("vars", self.vars),
            )
            if value
        }
        return ManifestContext(
            present=True,
            values=values,
            repo_root=str(repo_root.resolve()),
        )


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


def build_manifest_context(raw: dict[str, Any], *, repo_root: str | None = None) -> ManifestContext:
    """Parse a farrier context manifest and project it onto the render context."""
    if repo_root is None:
        repo_root = os.environ.get("AGENT_REPO_DIR") or "."
    return ContextManifest.model_validate(raw).project(repo_root=Path(repo_root))


def context_dir(repo_dir: Path | None = None) -> Path:
    """The folder the manifests are read from: the run's own copy in a container, else the repo's state folder."""
    staged = os.environ.get("AGENT_CONTEXT_DIR")
    if staged and repo_dir is None:
        return Path(staged)
    repo_dir = repo_dir or Path(os.environ.get("AGENT_REPO_DIR") or ".")
    try:
        manifest = read_manifest(repo_dir)
    except ConfigError:
        manifest = None
    configured = manifest.repo.name if manifest is not None else None
    return farrier_state_dir(repo_state_name(repo_dir, configured))


def load_context_manifest(context_file: str | None) -> ManifestContext:
    """Load the per-repo farrier context manifest that library prompts render against."""
    if context_file:
        path = Path(context_file)
        if not path.is_file():
            print(
                f"error: --context-file not found: {path}\n"
                "Run `make agent-install` to generate agents-context.json.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        state_dir = context_dir()
        cli = (os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()
        per_cli = state_dir / f"agents-context.{cli}.json"
        path = per_cli if per_cli.is_file() else state_dir / "agents-context.json"
        if not path.is_file():
            return ManifestContext()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read context manifest {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(raw, dict):
        print(f"error: context manifest {path} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return build_manifest_context(raw)


__all__ = [
    "ContextManifest",
    "ManifestContext",
    "build_manifest_context",
    "context_dir",
    "load_context_manifest",
]
