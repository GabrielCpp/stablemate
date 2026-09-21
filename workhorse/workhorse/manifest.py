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

from workhorse._vendor.stablemate_core.config import resolve_default_cli

BACKEND_SKILL_DIR: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "copilot": ".github/skills",
}

_INSTRUCTIONS = "_instructions"
_INSTRUCTION_TAGS = "_instruction_tags"
_PROMPTS = "_prompts"
_USED_SKILLS = "_used_skills"
_SKILL_DIR = "_skill_dir"
_REPO_ROOT = "_repo_root"


def _str_map(value: Any) -> dict[str, str]:
    """The string→string pairs of a mapping, dropping anything else."""
    if not isinstance(value, Mapping):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def _str_list(value: Any) -> list[str]:
    """The strings of a sequence, dropping anything else."""
    if isinstance(value, str) or not isinstance(value, (list, tuple, set, frozenset)):
        return []
    return [v for v in value if isinstance(v, str)]


def _tag_map(value: Any) -> dict[str, list[str]]:
    """The name→tags pairs of a mapping, dropping anything else."""
    if not isinstance(value, Mapping):
        return {}
    return {
        k: [t.lower() for t in _str_list(v)]
        for k, v in value.items()
        if isinstance(k, str) and _str_list(v)
    }


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


class ContextManifest(BaseModel):
    """The `.agents/agents-context.json` farrier writes, as we read it."""

    model_config = ConfigDict(extra="ignore")

    template: dict[str, Any] = Field(default_factory=dict)
    repo: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)

    instructions: dict[str, str] = Field(default_factory=dict)
    instruction_tags: dict[str, list[str]] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    used_skills: list[str] = Field(default_factory=list)
    skill_dir: str = ""

    @field_validator("template", "repo", "vars", mode="before")
    @classmethod
    def _tolerate_mapping(cls, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @field_validator("instructions", "prompts", mode="before")
    @classmethod
    def _tolerate_str_map(cls, value: Any) -> dict[str, str]:
        return _str_map(value)

    @field_validator("instruction_tags", mode="before")
    @classmethod
    def _tolerate_tag_map(cls, value: Any) -> dict[str, list[str]]:
        return _tag_map(value)

    @field_validator("used_skills", mode="before")
    @classmethod
    def _tolerate_str_list(cls, value: Any) -> list[str]:
        return _str_list(value)

    @field_validator("skill_dir", mode="before")
    @classmethod
    def _tolerate_text(cls, value: Any) -> str:
        return _text(value)

    def project(self, *, backend: str, repo_root: Path) -> ManifestContext:
        """Project the file onto the render context for one backend and repo."""
        target_skill_dir = BACKEND_SKILL_DIR.get(backend, self.skill_dir)
        instructions = self.instructions
        if self.skill_dir and target_skill_dir and target_skill_dir != self.skill_dir:
            instructions = {
                k: v.replace(self.skill_dir, target_skill_dir, 1)
                for k, v in instructions.items()
            }
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
            instructions=instructions,
            instruction_tags={k: list(v) for k, v in self.instruction_tags.items()},
            prompts=dict(self.prompts),
            used_skills=tuple(self.used_skills),
            skill_dir=target_skill_dir or self.skill_dir,
            repo_root=str(repo_root.resolve()),
        )


@dataclass(frozen=True, slots=True)
class ManifestContext:
    """What a run carries: the manifest, resolved for this backend and this repo."""

    present: bool = False
    values: dict[str, Any] = field(default_factory=dict)
    instructions: dict[str, str] = field(default_factory=dict)
    instruction_tags: dict[str, list[str]] = field(default_factory=dict)
    prompts: dict[str, str] = field(default_factory=dict)
    used_skills: tuple[str, ...] = ()
    skill_dir: str = ""
    repo_root: str = ""

    def as_context(self) -> dict[str, Any]:
        """The context layer a run lays under every agent turn's arguments."""
        if not self.present:
            return {}
        ctx: dict[str, Any] = dict(self.values)
        ctx[_INSTRUCTIONS] = dict(self.instructions)
        ctx[_INSTRUCTION_TAGS] = {k: list(v) for k, v in self.instruction_tags.items()}
        ctx[_PROMPTS] = dict(self.prompts)
        ctx[_USED_SKILLS] = list(self.used_skills)
        if self.skill_dir:
            ctx[_SKILL_DIR] = self.skill_dir
        ctx[_REPO_ROOT] = self.repo_root
        return ctx

    @classmethod
    def from_context(cls, context: Mapping[str, Any]) -> ManifestContext:
        """Read the manifest half back out of a render context."""
        return cls(
            present=_INSTRUCTIONS in context or _PROMPTS in context,
            instructions=_str_map(context.get(_INSTRUCTIONS)),
            instruction_tags=_tag_map(context.get(_INSTRUCTION_TAGS)),
            prompts=_str_map(context.get(_PROMPTS)),
            used_skills=tuple(_str_list(context.get(_USED_SKILLS))),
            skill_dir=_text(context.get(_SKILL_DIR)),
            repo_root=_text(context.get(_REPO_ROOT)),
        )


def build_manifest_context(
    raw: dict[str, Any], *, backend: str | None = None, repo_root: str | None = None
) -> ManifestContext:
    """Parse a farrier context manifest and project it onto the render context."""
    if backend is None:
        backend = os.environ.get("AGENT_CLI") or resolve_default_cli()
    if repo_root is None:
        repo_root = os.environ.get("AGENT_REPO_DIR") or "."
    return ContextManifest.model_validate(raw).project(
        backend=backend, repo_root=Path(repo_root)
    )


def load_context_manifest(context_file: str | None) -> ManifestContext:
    """Load the per-repo farrier context manifest that library prompts render against."""
    if context_file:
        path = Path(context_file)
        if not path.is_file():
            print(
                f"error: --context-file not found: {path}\n"
                "Run `make agent-install` to generate .agents/agents-context.json.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        repo_dir = os.environ.get("AGENT_REPO_DIR", ".")
        agents_dir = Path(repo_dir) / ".agents"
        cli = (os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()
        per_cli = agents_dir / f"agents-context.{cli}.json"
        path = per_cli if per_cli.is_file() else agents_dir / "agents-context.json"
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
    "BACKEND_SKILL_DIR",
    "ContextManifest",
    "ManifestContext",
    "build_manifest_context",
    "load_context_manifest",
]
