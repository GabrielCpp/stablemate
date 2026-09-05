"""The per-repo context manifest: what farrier installed, as render context.

`make agent-install` writes a JSON manifest into the target repo's `.agents/`
describing which skills and prompts were installed and where. Library prompts render
against it — `instruction_ref("story-docs")`, `isUsingInstruction(...)`,
`template.*` — so a workflow can name a skill without knowing the repo's layout or
which agent CLI it was installed for.

Two types, because the file and the render context are two different shapes:
:class:`ContextManifest` is farrier's file, read tolerantly; :class:`ManifestContext`
is what a run carries — the same information projected onto the render context, with
the per-backend path rewrite applied. The reserved ``_``-prefixed context keys are
spelled in this module and nowhere else: :meth:`ManifestContext.as_context` writes
them and :meth:`ManifestContext.from_context` reads them back, which is what the
helpers in :mod:`workhorse.templates` and :mod:`workhorse.references` call.

Lives at the top level rather than inside the engine because the run loads one: the
CLI reads it from `--context-file` and the Python driver takes it on its `RunEnv`,
laid under every agent turn's arguments.
"""

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

# Canonical skill directory per backend — must match farrier's install layout.
BACKEND_SKILL_DIR: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "copilot": ".github/skills",
}

# The reserved context keys. A run's context is one flat bag shared with the
# workflow's own variables, so the manifest's half is namespaced by a leading
# underscore. Naming them here — rather than as literals at each read — is what makes
# the convention checkable: `_SKILL_DIR` has usages, `"_skill_dir"` has occurrences.
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
    """The name→tags pairs of a mapping, dropping anything else.

    Tolerant like its siblings, and lowercasing as it goes: the tags are matched
    against a prompt's query words, and a manifest written by an older farrier (or by
    hand) must not turn `Web` into a tag nothing can ask for.
    """
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
    """The `.agents/agents-context.json` farrier writes, as we read it.

    Tolerant on purpose: this is another tool's file, so an unknown key is ignored
    and a wrong-typed one degrades to its default rather than raising. A manifest
    that grows a field workhorse has never heard of must not end a week-long run,
    and neither must one whose `used_skills` arrived as a string.
    """

    model_config = ConfigDict(extra="ignore")

    #: Rendered straight into the context, so `{{ template.x }}` / `{{ repo.y }}`
    #: resolve. Their contents are the *repo's* vocabulary, not workhorse's.
    template: dict[str, Any] = Field(default_factory=dict)
    repo: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)

    #: name → repo-root-relative path, for `instruction_ref` / `prompt_ref`.
    instructions: dict[str, str] = Field(default_factory=dict)
    #: The same names → the `tags:` their library source declares, for `find_by_tags`.
    #: Absent for a skill that declares none, and for a manifest written before tags
    #: existed — a prompt that queries by tag then matches nothing, which is the same
    #: answer it gets on a repo that installed no skill of that kind.
    instruction_tags: dict[str, list[str]] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    #: The skills selected for this repo, behind `isUsingInstruction`.
    used_skills: list[str] = Field(default_factory=list)
    #: Repo-root-relative directory the manifest's own skills were installed under.
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
        """Project the file onto the render context for one backend and repo.

        When the active backend (``AGENT_CLI``) differs from the backend the manifest
        was generated for, instruction paths are rewritten from the manifest's
        ``skill_dir`` prefix to the active backend's directory. All three backends
        share the ``{skill_dir}/{prefix}-{name}/SKILL.md`` structure, so a simple
        prefix substitution is sufficient.
        """
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
            # Not rewritten per backend: a tag says what a skill is *about*, and
            # only the paths differ between one CLI's install layout and another's.
            instruction_tags={k: list(v) for k, v in self.instruction_tags.items()},
            prompts=dict(self.prompts),
            used_skills=tuple(self.used_skills),
            skill_dir=target_skill_dir or self.skill_dir,
            # Absolute, so the renderer can locate hand-authored prompt flavor
            # overrides at <repo>/.agents/flavors/<workflow>/<node>.md.
            repo_root=str(repo_root.resolve()),
        )


@dataclass(frozen=True, slots=True)
class ManifestContext:
    """What a run carries: the manifest, resolved for this backend and this repo.

    The default instance is the manifest-free case — hello-world and most tests —
    and it is a real value rather than ``None`` so no caller branches on absence.
    ``present`` is what tells the two apart: a run with no manifest adds no context
    keys at all, and its unresolved references are normal rather than a symptom.
    """

    present: bool = False
    #: The manifest's own `template`/`repo`/`vars`, destined for Jinja by name.
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
        """Read the manifest half back out of a render context.

        The reader half of :meth:`as_context`, and the only one: every helper that
        needs the manifest at render time goes through here rather than reaching for
        a reserved key by name. ``values`` is not recovered — once merged, those are
        ordinary context variables the templates read by their own names.
        """
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
    """Parse a farrier context manifest and project it onto the render context.

    ``backend`` and ``repo_root`` default to ``None`` and are resolved from
    ``AGENT_CLI`` / ``AGENT_REPO_DIR`` here — the edge — rather than deeper down,
    where a caller could not influence them and a test would have to set the
    environment to reach the other branch. An unset ``AGENT_CLI`` falls to the
    config's ``default_cli``, the same rung ``get_backend`` lands on, so the manifest
    is projected for the CLI the run is actually driving.
    """
    if backend is None:
        backend = os.environ.get("AGENT_CLI") or resolve_default_cli()
    if repo_root is None:
        repo_root = os.environ.get("AGENT_REPO_DIR") or "."
    return ContextManifest.model_validate(raw).project(
        backend=backend, repo_root=Path(repo_root)
    )


def load_context_manifest(context_file: str | None) -> ManifestContext:
    """Load the per-repo farrier context manifest that library prompts render against.

    Resolution order: an explicit ``--context-file`` (which MUST exist — a typo'd
    path is a hard error), else auto-detect the per-assistant manifest for the active
    CLI (``$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json``), then the generic
    ``$AGENT_REPO_DIR/.agents/agents-context.json``. The per-assistant file makes a
    Codex/Copilot run resolve ``instruction_ref`` to its own adapter files
    (``.github/skills`` etc.) rather than Claude's. When none is present the run
    proceeds with an absent manifest (the farrier helpers degrade to placeholders /
    ``False``) — manifest-free workflows like hello-world need no repo context.
    Workflows that DO need it (e.g. coder) always pass ``--context-file`` via the
    generated Makefile, so the miss is caught there."""
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
