"""The per-repo context manifest: what farrier installed, as render context.

`make agent-install` writes a JSON manifest into the target repo's `.agents/`
describing which skills and prompts were installed and where. Library prompts render
against it — `instruction_ref("story-docs")`, `isUsingInstruction(...)`,
`template.*` — so a workflow can name a skill without knowing the repo's layout or
which agent CLI it was installed for.

Lives at the top level rather than inside either engine because both load one: the
YAML front-end reads it from `--context-file` into the outer layer of every node's
context, and the Python driver takes the same dict on its `RunEnv`. The reshaping
below (`_`-prefixed reserved keys) is read by the helpers in
:mod:`workhorse.templates`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Canonical skill directory per backend — must match farrier's install layout.
BACKEND_SKILL_DIR: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "copilot": ".github/skills",
}


def build_manifest_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a farrier context manifest into starting-context keys.

    The manifest's ``template``/``repo``/``vars`` become top-level context values
    (so ``{{ template.x }}`` / ``{{ repo.y }}`` resolve), while the path maps and
    the selected-skills set are stashed under reserved ``_``-prefixed keys read by
    the template helpers in workhorse/templates.py.

    When the active backend (``AGENT_CLI``) differs from the backend the manifest
    was generated for, instruction paths are rewritten from the manifest's
    ``skill_dir`` prefix to the active backend's directory.  All three backends
    share the ``{skill_dir}/{prefix}-{name}/SKILL.md`` structure, so a simple
    prefix substitution is sufficient.
    """
    ctx: dict[str, Any] = {}
    for key in ("template", "repo", "vars"):
        value = raw.get(key)
        if isinstance(value, dict):
            ctx[key] = value

    backend = os.environ.get("AGENT_CLI", "claude")
    manifest_skill_dir = raw.get("skill_dir") or ""
    target_skill_dir = BACKEND_SKILL_DIR.get(backend, manifest_skill_dir)

    raw_instructions: dict[str, str] = raw.get("instructions") or {}
    if (
        manifest_skill_dir
        and target_skill_dir
        and target_skill_dir != manifest_skill_dir
    ):
        ctx["_instructions"] = {
            k: v.replace(manifest_skill_dir, target_skill_dir, 1)
            for k, v in raw_instructions.items()
        }
    else:
        ctx["_instructions"] = raw_instructions

    ctx["_prompts"] = raw.get("prompts") or {}
    ctx["_used_skills"] = raw.get("used_skills") or []
    if target_skill_dir or manifest_skill_dir:
        ctx["_skill_dir"] = target_skill_dir or manifest_skill_dir

    # Absolute repo root, so the renderer can locate hand-authored prompt flavor
    # overrides at <repo>/.agents/flavors/<workflow>/<node>.md (see templates.render).
    # The agent runs with its cwd at the repo root (AGENT_REPO_DIR); default to cwd.
    ctx["_repo_root"] = str(Path(os.environ.get("AGENT_REPO_DIR") or ".").resolve())
    return ctx


def load_context_manifest(context_file: str | None) -> dict[str, Any]:
    """Load the per-repo farrier context manifest that library prompts render against.

    Resolution order: an explicit ``--context-file`` (which MUST exist — a typo'd
    path is a hard error), else auto-detect the per-assistant manifest for the active
    CLI (``$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json``), then the generic
    ``$AGENT_REPO_DIR/.agents/agents-context.json``. The per-assistant file makes a
    Codex/Copilot run resolve ``instruction_ref`` to its own adapter files
    (``.github/skills`` etc.) rather than Claude's. When none is present the run
    proceeds with an empty manifest (the farrier helpers degrade to placeholders /
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
        cli = os.environ.get("AGENT_CLI", "claude").strip().lower()
        per_cli = agents_dir / f"agents-context.{cli}.json"
        path = per_cli if per_cli.is_file() else agents_dir / "agents-context.json"
        if not path.is_file():
            return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read context manifest {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(raw, dict):
        print(f"error: context manifest {path} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return build_manifest_context(raw)


__all__ = ["BACKEND_SKILL_DIR", "build_manifest_context", "load_context_manifest"]
