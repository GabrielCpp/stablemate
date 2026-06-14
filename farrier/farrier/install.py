#!/usr/bin/env python3
"""farrier — render the agent prompt library into a repository.

The source library is intentionally agent-neutral. farrier renders the selected
packs into the file layouts expected by Codex, Claude, and GitHub Copilot.

farrier ships no library content of its own. It locates the library directory
(the `agents/` tree containing `library/`, `packs/`, `scaffolds/`, `workflows/`)
with this precedence:

  1. ``--library DIR`` flag
  2. ``$FARRIER_LIBRARY_DIR`` environment variable
  3. ``library_dir`` in the home config file (see ``farrier config``)

Set it once with ``farrier config set-library <path-to>/vigilant-octo/agents``.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined
from platformdirs import user_config_dir

# Library content roots. Populated by ``set_library_globals()`` once the library
# directory is resolved in ``main()``. They are module globals because the
# rendering helpers below reference them directly.
AGENTS: Path = None  # type: ignore[assignment]
LIBRARY: Path = None  # type: ignore[assignment]
PACKS: Path = None  # type: ignore[assignment]
SKILLS: Path = None  # type: ignore[assignment]
PROMPTS: Path = None  # type: ignore[assignment]
ROOTS: Path = None  # type: ignore[assignment]
SCAFFOLDS: Path = None  # type: ignore[assignment]
WORKFLOWS: Path = None  # type: ignore[assignment]

# OS-appropriate user config dir (~/.config/farrier on Linux,
# ~/Library/Application Support/farrier on macOS, %APPDATA%\farrier on Windows).
CONFIG_PATH = Path(user_config_dir("farrier")) / "config.toml"


def set_library_globals(root: Path) -> None:
    """Point the library content globals at the resolved library directory."""
    global AGENTS, LIBRARY, PACKS, SKILLS, PROMPTS, ROOTS, SCAFFOLDS, WORKFLOWS
    AGENTS = root
    LIBRARY = root / "library"
    PACKS = root / "packs"
    SKILLS = LIBRARY / "skills"
    PROMPTS = LIBRARY / "prompts"
    ROOTS = LIBRARY / "roots"
    SCAFFOLDS = root / "scaffolds"
    WORKFLOWS = root / "workflows"


def read_config() -> dict[str, Any]:
    """Read the home config file; return ``{}`` when it does not exist."""
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _write_config_key(key: str, value: str) -> None:
    """Persist a single key to the home config file, preserving other keys."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = read_config()
    cfg[key] = value
    lines = []
    for k, v in cfg.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{k} = "{escaped}"\n')
    CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


def write_library_dir(path: Path) -> None:
    """Persist ``library_dir`` to the home config file."""
    _write_config_key("library_dir", str(path))


def write_stablemate_dir(path: Path) -> None:
    """Persist ``stablemate_dir`` to the home config file."""
    _write_config_key("stablemate_dir", str(path))


def resolve_stablemate_dir() -> "Path | None":
    """Return the configured stablemate checkout path, or None if unset."""
    configured = read_config().get("stablemate_dir")
    if configured:
        return Path(configured).expanduser().resolve()
    return None


def is_library_dir(path: Path) -> bool:
    """A directory is a usable library root when it holds library/ and packs/."""
    return (path / "library").is_dir() and (path / "packs").is_dir()


def resolve_library_dir(cli_library: Path | None) -> Path:
    """Resolve the library root: --library > $FARRIER_LIBRARY_DIR > home config.

    Raises SystemExit with a setup hint when nothing resolves or the resolved
    path is not a usable library directory.
    """
    candidate: Path | None = None
    source = ""
    if cli_library is not None:
        candidate, source = cli_library, "--library"
    elif os.environ.get("FARRIER_LIBRARY_DIR"):
        candidate, source = (
            Path(os.environ["FARRIER_LIBRARY_DIR"]),
            "$FARRIER_LIBRARY_DIR",
        )
    else:
        configured = read_config().get("library_dir")
        if configured:
            candidate, source = Path(configured), f"{CONFIG_PATH}"

    if candidate is None:
        raise SystemExit(
            "error: no library directory configured.\n"
            "Set it once with:\n"
            "    farrier config set-library <path-to>/vigilant-octo/agents\n"
            "or pass --library DIR / set $FARRIER_LIBRARY_DIR."
        )

    root = candidate.expanduser().resolve()
    if not is_library_dir(root):
        raise SystemExit(
            f"error: {root} (from {source}) is not a usable library directory "
            "— it must contain library/ and packs/."
        )
    return root


# Scaffold outputs whose basename is in this set are SEEDS: written only when the
# target does not already exist, so a repository can evolve them after the first
# scaffold without the installer clobbering local edits on the next run. They are
# also exempt from --check drift detection — once the file exists, the repo owns
# it. Used for per-service .gitignore files seeded alongside docs/, api/, app/,
# pulumi/, and web/ scaffolds.
SEED_SCAFFOLD_BASENAMES = {".gitignore"}

WORKFLOW_SKIP_PARTS = {
    "__pycache__",
    ".runs",
    ".state",
    ".codex-home",
}

TARGET_DIRS = [
    ".agents/skills",
    ".agents/prompts",
    ".claude/skills",
    ".claude/commands",
    ".github/instructions",
    ".github/prompts",
]

# Launcher scaffolding generated when >= 1 workflow is installed. These are
# always-owned generated files (registered for --check and cleanup). The thin
# root Makefile is special-cased: it is only written when no root Makefile
# already exists, and is never removed by cleanup (a user may hand-author it).
LAUNCHER_AGENTS_MK = ".agents/agents.mk"
LAUNCHER_COMPOSE = ".agents/local.compose.yaml"
LAUNCHER_CONTEXT_MANIFEST = ".agents/agents-context.json"
# Per-assistant context manifests (one per enabled agent) so a Codex/Copilot run
# resolves instruction_ref to its own adapters. Selected by AGENT_CLI at run time;
# the generic LAUNCHER_CONTEXT_MANIFEST above stays the primary assistant's copy.
LAUNCHER_CONTEXT_MANIFEST_FMT = ".agents/agents-context.{}.json"
LAUNCHER_ROOT_MAKEFILE = "Makefile"
# Default relative path from the target repo to the vigilant-octo agents dir
# (the prompt-library *content*). Overridable per-repo via agents.yml:
# workflow.agentsDir.
DEFAULT_AGENTS_DIR = "$(abspath $(CURDIR)/../vigilant-octo/agents)"
# Default relative path to the public `stablemate` checkout (holds the workhorse
# runtime source and the farrier installer source — needed only for Docker runs
# and SRC=1 local-source runs). Overridable via the STABLEMATE_DIR make var.
DEFAULT_STABLEMATE_DIR = "$(abspath $(CURDIR)/../stablemate)"


def get_git_remote(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def _git_out(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    out = result.stdout.strip()
    if result.returncode == 0 and out:
        return out
    return None


def get_default_branch(repo: Path) -> str | None:
    """Resolve the repo's DEFAULT (long-lived) branch — master or main — NOT the
    branch currently checked out.

    REPO_BRANCH names the integration branch the worker clones and the coder
    workflow opens PRs against and merges into; it must be the repo's trunk, not
    whatever feature/throwaway branch the installer happened to run from. We probe,
    in order: origin's published default (`origin/HEAD`), then the conventional
    local `main` / `master`, and let the caller fall back to "main".
    """
    # origin's default branch, e.g. "origin/main" → "main".
    head = _git_out(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.split("/", 1)[-1]
    # No published origin/HEAD — fall back to the conventional trunk names that
    # actually exist (local or on origin).
    for name in ("main", "master"):
        for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
            if _git_out(repo, "rev-parse", "--verify", "--quiet", ref) is not None:
                return name
    return None


@dataclass(frozen=True)
class Source:
    kind: str
    path: Path
    rel: str
    id: str


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing config: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a YAML mapping: {path}")
    return data


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def is_seed_output(path: Path) -> bool:
    """A seed output is created once, then owned by the repo (never overwritten)."""
    return path.name in SEED_SCAFFOLD_BASENAMES


def kebab(value: str) -> str:
    value = value.removesuffix(".prompt").removesuffix(".instructions")
    value = value.replace(".", "-").replace("_", "-")
    value = re.sub(r"[^a-zA-Z0-9/-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-").lower()
    return value


def normalize_pattern(pattern: str) -> str:
    """Normalize a user-facing glob without destroying glob characters."""
    return (
        pattern.removesuffix(".md")
        .removesuffix(".prompt")
        .removesuffix(".instructions")
        .replace(".", "-")
        .replace("_", "-")
        .lower()
    )


def strip_known_suffix(path: Path) -> str:
    name = path.name
    if name.endswith(".prompt.md"):
        return name.removesuffix(".prompt.md")
    if name.endswith(".instructions.md"):
        return name.removesuffix(".instructions.md")
    return path.stem


def source_id(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    # For SKILL.md files in directories, use the parent directory name as the skill name.
    # For any other .md files, use the old flat-file logic for backwards compatibility.
    if rel.name == "SKILL.md":
        parts = [kebab(part) for part in rel.parent.parts]
    else:
        parts = [kebab(part) for part in rel.with_name(strip_known_suffix(rel)).parts]
    return "/".join(parts)


def public_id(source: Source) -> str:
    return kebab(Path(source.id).name)


def public_name(prefix: str, source: Source) -> str:
    base = public_id(source)
    if base == prefix or base.startswith(f"{prefix}-"):
        return base
    return f"{prefix}-{base}"


def load_sources(root: Path, kind: str) -> list[Source]:
    sources: list[Source] = []
    # Load SKILL.md files (new open skill format: <name>/SKILL.md).
    # Also support flat *.md files for backwards compatibility during migration.
    for path in sorted(
        list(root.rglob("SKILL.md"))
        + [p for p in root.rglob("*.md") if p.name != "SKILL.md"]
    ):
        rel = path.relative_to(root).as_posix()
        sources.append(Source(kind=kind, path=path, rel=rel, id=source_id(root, path)))
    return sources


def load_scaffold_sources(root: Path) -> list[Source]:
    sources: list[Source] = []
    if not root.exists():
        return sources
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        sources.append(Source(kind="scaffold", path=path, rel=rel, id=rel))
    return sources


def split_front_matter(content: str) -> tuple[dict[str, str], str]:
    match = re.match(
        r"\A---\n(?P<header>.*?)\n---\n\n?(?P<body>.*)\Z",
        content,
        flags=re.DOTALL,
    )
    if not match:
        return {}, content

    header: dict[str, str] = {}
    for line in match.group("header").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        header[key.strip()] = value.strip().strip('"').strip("'")
    return header, match.group("body")


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def parse_scaffold_entries(entries: Any) -> tuple[set[str], dict[str, str]]:
    """Split a `scaffolds` list into glob patterns and source→dest folder maps.

    Each entry is either a scalar glob (selected, output via namespace strip) or a
    single-key mapping `{src-prefix: dest-dir}` that both selects the matching
    source(s) and retargets their output under `dest-dir`. The mapping form lets a
    repository point a folder-agnostic scaffold (e.g. a Flutter `.gitignore`) at
    whatever folder that project actually uses — `app`, `mobile`, etc. — instead of
    a name baked into the library path.
    """
    patterns: set[str] = set()
    mappings: dict[str, str] = {}
    for entry in entries or []:
        if isinstance(entry, dict):
            for src, dest in entry.items():
                mappings[str(src).strip("/")] = str(dest).strip("/")
        else:
            patterns.add(str(entry))
    return patterns, mappings


def load_pack(pack_id: str, seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    if pack_id in seen:
        raise SystemExit(f"Pack include cycle detected at {pack_id}")
    seen.add(pack_id)

    path = PACKS / f"{pack_id}.yml"
    if not path.exists():
        raise SystemExit(f"Unknown pack: {pack_id}")
    data = read_yaml(path)

    scaffold_patterns, scaffold_map = parse_scaffold_entries(data.get("scaffolds"))
    merged: dict[str, Any] = {
        "skills": set(data.get("skills", []) or []),
        "prompts": set(data.get("prompts", []) or []),
        "roots": set(data.get("roots", []) or []),
        "scaffolds": scaffold_patterns,
        "scaffold_map": scaffold_map,
        "workflows": set(data.get("workflows", []) or []),
    }
    for include in data.get("includes", []) or []:
        child = load_pack(str(include), seen)
        for key, values in child.items():
            # Sets merge with .update(set); the scaffold dest map merges with
            # .update(dict). A later pack's mapping overrides an earlier one.
            merged[key].update(values)
    return merged


def should_skip_workflow_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return (
        any(part in WORKFLOW_SKIP_PARTS for part in rel.parts) or path.suffix == ".pyc"
    )


def extract_workflow_dependencies(workflow_root: Path) -> tuple[set[str], set[str]]:
    """Extract skill and prompt names referenced in workflow prompts via instruction_ref/prompt_ref.

    Returns: (skill_names, prompt_names)
    """
    skills = set()
    prompts = set()

    prompts_dir = workflow_root / "prompts"
    if not prompts_dir.exists():
        return skills, prompts

    for prompt_file in prompts_dir.glob("*.md"):
        content = prompt_file.read_text(encoding="utf-8")

        # Find all instruction_ref("name") calls
        for match in re.finditer(r'instruction_ref\("([^"]+)"\)', content):
            skills.add(match.group(1))

        # Find all prompt_ref("name") calls
        for match in re.finditer(r'prompt_ref\("([^"]+)"\)', content):
            prompts.add(match.group(1))

    return skills, prompts


def matches(source: Source, patterns: set[str]) -> bool:
    candidates = {
        source.id,
        public_id(source),
        source.rel,
        source.rel.removesuffix(".md"),
        source.rel.removesuffix(".prompt.md"),
        source.rel.removesuffix(".instructions.md"),
    }
    for pattern in patterns:
        all_patterns = {pattern, normalize_pattern(pattern)}
        for candidate in candidates:
            if any(fnmatch.fnmatch(candidate.lower(), item) for item in all_patterns):
                return True
    return False


def selected_sources(
    all_sources: list[Source],
    include_patterns: set[str],
    exclude_patterns: set[str],
) -> list[Source]:
    selected = [
        source
        for source in all_sources
        if matches(source, include_patterns) and not matches(source, exclude_patterns)
    ]
    return sorted(selected, key=lambda item: item.id)


def build_lookup(sources: list[Source], prefix: str) -> dict[str, Source]:
    lookup: dict[str, Source] = {}
    for source in sources:
        keys = {
            source.id,
            public_id(source),
            public_name(prefix, source),
            source.rel,
            source.rel.removesuffix(".md"),
            source.rel.removesuffix(".prompt.md"),
        }
        for key in keys:
            normalized = key.replace(".", "-")
            existing = lookup.get(normalized)
            if existing and existing != source:
                raise SystemExit(
                    f"Ambiguous selected source id {normalized!r}: "
                    f"{existing.rel} and {source.rel}"
                )
            lookup[normalized] = source
    return lookup


def relative_reference(from_file: Path, to_file: Path) -> str:
    return os.path.relpath(to_file, from_file.parent).replace(os.sep, "/")


def collect_template_values(config: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in ["vars", "template"]:
        configured = config.get(key) or {}
        if not isinstance(configured, dict):
            raise SystemExit(f"{key} must be a YAML mapping when present")
        values.update(configured)
    return values


def resolve_workflow_meta(
    config: dict[str, Any], repo: Path, repo_name: str
) -> dict[str, str]:
    """Resolve repo_url / branch / agents-dir for the launcher scaffolding.

    Precedence: explicit `agents.yml` `workflow:` block, then the repo's own
    git origin + DEFAULT branch (master/main — NOT the branch currently checked
    out), then a clearly-marked placeholder. REPO_BRANCH is the trunk the worker
    clones and the coder workflow targets/merges PRs into, so it must be the
    long-lived integration branch, not the install-time HEAD. The default run mode
    is a local read-only bind-mount clone, so a placeholder URL is fine for
    `make agent-run` (it is only used by GitHub-default workflow runs).
    """
    workflow_cfg = config.get("workflow") or {}
    if not isinstance(workflow_cfg, dict):
        raise SystemExit("workflow must be a YAML mapping when present")

    repo_url = workflow_cfg.get("repoUrl") or workflow_cfg.get("repo_url")
    branch = workflow_cfg.get("branch")
    agents_dir = workflow_cfg.get("agentsDir") or workflow_cfg.get("agents_dir")

    # Host env vars to forward into the Docker run (interpolated from the local
    # env at `docker compose up` time). E.g. a GitHub token for opening PRs.
    env_passthrough = (
        workflow_cfg.get("envPassthrough") or workflow_cfg.get("env_passthrough") or []
    )
    if not isinstance(env_passthrough, list):
        raise SystemExit("workflow.envPassthrough must be a list of env var names")
    env_passthrough = [str(name) for name in env_passthrough]

    if not repo_url:
        repo_url = get_git_remote(repo)
    if not branch:
        branch = get_default_branch(repo)

    return {
        "repo_url": str(repo_url) if repo_url else "REPLACE_ME-git-remote-url",
        "branch": str(branch) if branch else "main",
        "agents_dir": str(agents_dir) if agents_dir else DEFAULT_AGENTS_DIR,
        "repo_name": repo_name,
        "env_passthrough": env_passthrough,
    }


def render_agents_mk(workflows: list[str], meta: dict[str, str]) -> str:
    """Generic, workflow-name-parameterized make launcher (.agents/agents.mk).

    Mirrors the assembler Makefile (COMPOSE = base + override layering, ENVV with
    WORKFLOW_DIR / REPO_SRC / REPO_BRANCH / REPO_NAME, native via uv run) but uses
    NEUTRAL `agent-*` target names and a `WF` variable defaulting to the first
    installed workflow. No 'hrnet' / 'research' / 'assembler' hardcoding.
    """
    default_wf = workflows[0]
    workflow_list = " ".join(workflows)
    placeholder = meta["repo_url"].startswith("REPLACE_ME")
    repo_url_line = (
        f"REPO_URL     ?= {meta['repo_url']}"
        if not placeholder
        else f"# REPO_URL: set me to the git remote (only used by GitHub-default runs,\n"
        f"# not the default local bind-mount clone). Auto-detection found no origin.\n"
        f"REPO_URL     ?= {meta['repo_url']}"
    )
    return f"""# Multi-workflow agent launcher — workhorse quick start (generated).
#
# Generated by farrier (the prompt-library installer). Do not edit by hand;
# re-run `make agent-install` to regenerate. Include it from a root Makefile:
#
#   include .agents/agents.mk
#
# The agent runs the workflow DIRECTLY FROM THE LIBRARY ($(AGENTS_DIR)/workflows/<WF>)
# — workflows are never installed/copied into this repo. Per-repo specifics come
# from .agents/agents-context.json (generated by `make agent-install`), which the
# prompts render against at run time. The Docker path uses your Claude subscription
# (seeded from ~/.claude/.credentials.json) and persists the agent's work, sessions,
# and run artifacts (under the repo-local .agents/runs). Native runs honour AGENT_CLI
# (claude|codex|copilot); the Docker path is Claude-oriented for now.
#
# Local mode (default): the container clones THIS repo from a read-only bind
# mount (see .agents/local.compose.yaml) — no SSH key, token, or network needed,
# and the host working tree is never mutated. The clone uses your latest
# committed state on $(REPO_BRANCH).
#
# Installed workflows: {workflow_list}
#
# Native mode uses the installed `workhorse` binary by default.
# SRC=1 runs workhorse from the local stablemate source checkout ($(LOCAL_WORKER)) via uv.
#
# Usage:
#   make agent-run                 # Docker + local clone (default WF={default_wf})
#   make agent-run WF=<name>       # pick another installed workflow
#   make agent-native              # native (no Docker) on THIS working tree (foreground)
#   make agent-native AGENT_CLI=copilot   # run on Codex/Copilot instead of Claude (native only)
#   make agent-native-bg           # native, detached — saves pid; watch with agent-logs
#   make agent-native SRC=1        # native from local stablemate source ($(LOCAL_WORKER))
#   make agent-logs                # follow the current run log (.agents/runs/<WF>.log)
#   make agent-stop                # stop a detached native run (agent-native-bg)
#   make agent-build               # rebuild image + run
#   make agent-hello               # smoke-test with hello-world
#   make agent-container-logs      # follow the Docker container logs
#   make agent-down                # stop containers (keep volumes)
#   make agent-reseed-auth         # clear auth + re-seed credentials
#   make agent-clean               # wipe ALL volumes
#   make agent-artifacts           # copy run artifacts into ./.agents/runs
#   make agent-install             # regenerate these adapters from the library
#   make agent-check               # verify adapters are up to date (no writes)

AGENTS_DIR     ?= $(shell farrier config show library_dir)
# Public stablemate checkout (workhorse runtime + farrier installer source).
# Needed only for Docker runs and SRC=1 local-source runs.
STABLEMATE_DIR ?= $(shell farrier config show stablemate_dir)
LOCAL_WORKER   := $(STABLEMATE_DIR)/workhorse
# WF selects which workflow to run; defaults to the first selected.
WF           ?= {default_wf}
# AGENT_CLI selects the agent backend: claude (default) | codex | copilot. Native
# runs check that this CLI is on PATH and forward it to workhorse; it also selects
# the per-assistant context manifest below.
AGENT_CLI    ?= claude
# Workflows run straight from the library — not copied into this repo.
WORKFLOW_DIR ?= $(AGENTS_DIR)/workflows/$(WF)
# Per-repo context manifest the library prompts render against (generated by
# `make agent-install`). Prefer the per-assistant manifest for $(AGENT_CLI) so a
# Codex/Copilot run resolves instruction_ref to its own adapters (.github/skills,
# etc.); fall back to the generic one. workhorse also auto-detects this from
# AGENT_REPO_DIR + AGENT_CLI when --context-file is omitted.
CONTEXT_FILE ?= $(firstword $(wildcard $(CURDIR)/.agents/agents-context.$(AGENT_CLI).json) $(CURDIR)/.agents/agents-context.json)
REPO_NAME    ?= {meta["repo_name"]}
REPO_BRANCH  ?= {meta["branch"]}
{repo_url_line}
# Compose project name (default = first compose file's directory) → volume prefix.
PROJECT      ?= local-worker
# Native runs use the installed workhorse binary by default.
# SRC=1 runs workhorse from the local stablemate source checkout via uv.
# An explicit WORKHORSE=... overrides both.
# WORKHORSE_VERSION is the informational version printed at startup.
ifeq ($(SRC),1)
WORKHORSE         ?= uv run --project $(LOCAL_WORKER) workhorse
WORKHORSE_VERSION ?= $(shell grep -m1 '^version' $(LOCAL_WORKER)/pyproject.toml 2>/dev/null | cut -d'"' -f2) (local source: $(LOCAL_WORKER))
endif
WORKHORSE         ?= workhorse
WORKHORSE_VERSION ?= $(shell workhorse --version 2>/dev/null || echo unknown) (installed)

# farrier regenerates these adapters from the prompt library. Default uses the
# installed farrier binary. SRC=1 runs the local source under $(STABLEMATE_DIR)/farrier.
# The library CONTENT is located via the user's `farrier config set-library` home
# config; when a vigilant-octo checkout exists at $(AGENTS_DIR) we pass --library
# explicitly so no global config is required. First-time setup:
#   pipx install farrier && farrier config set-library /path/to/vigilant-octo/agents
#   farrier config set-stablemate /path/to/stablemate
ifeq ($(SRC),1)
FARRIER ?= uv run --project $(STABLEMATE_DIR)/farrier farrier
endif
FARRIER ?= farrier
FARRIER_LIB_ARG := $(if $(wildcard $(AGENTS_DIR)/library),--library "$(AGENTS_DIR)",)

# Optional run knobs forwarded to workhorse (native targets):
#   RUN_ID      names the stable run dir (<workflow>-<RUN_ID>); default "default".
#   PARAMS      inline JSON of workflow params, e.g. '{{"program":"hrnet-research"}}'.
#   PARAMS_FILE path to a JSON file of workflow params (same effect as PARAMS).
AGENT_ARGS := $(if $(RUN_ID),--run-id "$(RUN_ID)") $(if $(PARAMS),--params '$(PARAMS)') $(if $(PARAMS_FILE),--params-file "$(PARAMS_FILE)")

# Layer the local-run override on top of the generic worker compose.
COMPOSE := docker compose \\
\t-f $(LOCAL_WORKER)/compose.yaml \\
\t-f $(CURDIR)/.agents/local.compose.yaml
ENVV := WORKFLOW_DIR="$(WORKFLOW_DIR)" REPO_SRC="$(CURDIR)" REPO_BRANCH="$(REPO_BRANCH)" REPO_NAME="$(REPO_NAME)"

# Per-workflow run log + pid (under the gitignored .agents/runs/).
RUNS_DIR     := $(CURDIR)/.agents/runs
LOG          := $(RUNS_DIR)/$(WF).log
PID          := $(RUNS_DIR)/$(WF).pid

.DEFAULT_GOAL := help

.PHONY: help agent-run agent-native agent-native-bg agent-build agent-hello agent-logs agent-container-logs agent-stop agent-down agent-clean agent-reseed-auth agent-artifacts agent-install agent-check

help: ## Show available targets
\t@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \\
\t\tawk 'BEGIN{{FS=":.*?## "}}{{printf "  \\033[36m%-22s\\033[0m %s\\n", $$1, $$2}}'

agent-run: ## Run the selected workflow (Docker, local clone). Override with WF=<name>
\t@mkdir -p $(RUNS_DIR)
\t$(ENVV) $(COMPOSE) up --abort-on-container-exit 2>&1 | tee $(LOG)

agent-native: ## Run natively (no Docker, pipx) on THIS tree; logs tee'd to .agents/runs/$(WF).log
\t@mkdir -p $(RUNS_DIR)
\t@command -v $(AGENT_CLI) >/dev/null || {{ echo "error: '$(AGENT_CLI)' CLI not on PATH (set AGENT_CLI=claude|codex|copilot)"; exit 1; }}
\t@echo "using workhorse-agent $(WORKHORSE_VERSION) (AGENT_CLI=$(AGENT_CLI))"
\tPYTHONUNBUFFERED=1 AGENT_CLI="$(AGENT_CLI)" AGENT_REPO_DIR="$(CURDIR)" $(WORKHORSE) \\
\t\t--workflow $(WORKFLOW_DIR)/workflow.yaml --context-file $(CONTEXT_FILE) --runs-dir $(RUNS_DIR) $(AGENT_ARGS) 2>&1 | tee $(LOG)

agent-native-bg: ## Detached native run; saves pid to .agents/runs/$(WF).pid (watch: make agent-logs)
\t@mkdir -p $(RUNS_DIR)
\t@command -v $(AGENT_CLI) >/dev/null || {{ echo "error: '$(AGENT_CLI)' CLI not on PATH (set AGENT_CLI=claude|codex|copilot)"; exit 1; }}
\t@echo "using workhorse-agent $(WORKHORSE_VERSION) (AGENT_CLI=$(AGENT_CLI))"
\t@PYTHONUNBUFFERED=1 AGENT_CLI="$(AGENT_CLI)" AGENT_REPO_DIR="$(CURDIR)" nohup $(WORKHORSE) \\
\t\t--workflow $(WORKFLOW_DIR)/workflow.yaml --context-file $(CONTEXT_FILE) --runs-dir $(RUNS_DIR) $(AGENT_ARGS) >$(LOG) 2>&1 </dev/null & \\
\t\techo $$! >$(PID); echo "started native run (pid $$(cat $(PID))) — follow: make agent-logs WF=$(WF) ; stop: make agent-stop WF=$(WF)"

agent-build: ## Rebuild the worker image, then run the workflow
\t@mkdir -p $(RUNS_DIR)
\t$(ENVV) $(COMPOSE) up --build --abort-on-container-exit 2>&1 | tee $(LOG)

agent-hello: ## Smoke-test the worker + auth with the hello-world workflow
\tWORKFLOW_DIR="$(AGENTS_DIR)/workflows/hello-world" docker compose -f $(LOCAL_WORKER)/compose.yaml up --abort-on-container-exit

agent-logs: ## Follow the current run's log (.agents/runs/$(WF).log)
\t@mkdir -p $(RUNS_DIR); touch $(LOG); tail -n +1 -F $(LOG)

agent-container-logs: ## Follow the Docker worker container's logs
\tdocker logs -f $(PROJECT)-agent-1

agent-stop: ## Stop a detached native run started with agent-native-bg
\t@if [ -f $(PID) ] && kill -0 $$(cat $(PID)) 2>/dev/null; then \\
\t\tP=$$(cat $(PID)); pkill -TERM -P $$P 2>/dev/null || true; kill -TERM $$P 2>/dev/null || true; \\
\t\techo "stopped native run (pid $$P)"; rm -f $(PID); \\
\telse echo "no running native run (pidfile absent or stale)"; rm -f $(PID) 2>/dev/null || true; fi

agent-down: ## Stop/remove worker containers (keeps volumes & agent work)
\t$(ENVV) $(COMPOSE) down

agent-reseed-auth: agent-down ## Re-seed subscription creds from the host (clears sessions volume)
\t-docker volume rm $(PROJECT)_claude-state

agent-clean: ## Remove ALL worker volumes — clone, sessions, AND run artifacts
\t$(ENVV) $(COMPOSE) down -v

agent-artifacts: ## Copy run artifacts out of the runs volume into ./.agents/runs
\t@mkdir -p $(CURDIR)/.agents/runs
\tdocker run --rm \\
\t\t-v $(PROJECT)_runs:/runs:ro \\
\t\t-v $(CURDIR)/.agents/runs:/out \\
\t\talpine sh -c 'cp -a /runs/. /out/ 2>/dev/null || true; ls -la /out'

agent-install: ## Regenerate the agent adapters/skills/workflows from the prompt library
\t$(FARRIER) --repo "$(CURDIR)" $(FARRIER_LIB_ARG)

agent-check: ## Verify generated agent adapters are up to date (no writes)
\t@$(FARRIER) --repo "$(CURDIR)" --check $(FARRIER_LIB_ARG) \\
\t\t&& echo "✓ agent files are up to date" \\
\t\t|| {{ echo "↑ files above would be rewritten by 'make agent-install'"; exit 1; }}
"""


def render_local_compose(meta: dict[str, str]) -> str:
    """Generic local-run compose override (.agents/local.compose.yaml).

    Clones the repo from a read-only bind mount instead of GitHub. The bind
    mount target is /mnt/<repo-name>-src (derived from the repo, not hardcoded).
    """
    src_target = f"/mnt/{kebab(meta['repo_name'])}-src"
    # Forward declared host env vars into the container, interpolated from the
    # local env at `docker compose up` time (e.g. a GitHub token for PRs).
    passthrough = meta.get("env_passthrough") or []
    passthrough_block = ""
    if passthrough:
        passthrough_block = (
            "      # Host env vars forwarded per agents.yml workflow.envPassthrough\n"
            "      # (interpolated from the local env at `docker compose up`; empty if unset).\n"
            + "".join(f"      {name}: ${{{name}:-}}\n" for name in passthrough)
        )
    return f"""# Local-run override for the agent launcher (generated).
#
# Generated by vigilant-octo/agents/install.py. Layered on top of
# vigilant-octo/agents/local-worker/compose.yaml:
#   docker compose -f <local-worker>/compose.yaml -f .agents/local.compose.yaml up
# (the `make agent-run` target does this for you).
#
# It makes the container clone this repo from a READ-ONLY bind mount of your
# working tree instead of GitHub — so no SSH key, token, or network is needed,
# and your host working tree is never mutated (the clone lives in the workspace
# volume). The clone uses your latest *committed* state on $REPO_BRANCH.
services:
  agent:
    environment:
      # setup.sh prefers these over the workflow's GitHub defaults.
      REPO_URL: {src_target}
      REPO_BRANCH: ${{REPO_BRANCH:-{meta["branch"]}}}
      # Repository name → /workspace/$REPO_NAME inside the container.
      REPO_NAME: ${{REPO_NAME:-{meta["repo_name"]}}}
{passthrough_block}    volumes:
      - type: bind
        source: ${{REPO_SRC:-{meta.get("repo_src_default", ".")}}}
        target: {src_target}
        read_only: true
"""


# File suffixes that accept a `#`-style comment header.
_COMMENTABLE_SUFFIXES = {".py", ".sh", ".yaml", ".yml"}


def _prepend_workflow_header(content: str, source: Path, rel_in_workflow: str) -> str:
    """Prepend a DO-NOT-EDIT comment to a generated workflow file.

    Shebang lines are preserved as the first line. `.md` and `.json` files
    (and any other non-commentable type) are returned unchanged.
    """
    if source.suffix.lower() not in _COMMENTABLE_SUFFIXES:
        return content
    header = (
        f"# DO NOT EDIT — generated by farrier from the agent library.\n"
        f"# Canonical source: `farrier config show library_dir` → workflows/{rel_in_workflow}\n"
        f"# Regenerate      : make agent-install  (or: farrier --repo .)\n"
    )
    first, _, rest = content.partition("\n")
    if first.startswith("#!"):
        return first + "\n" + header + "\n" + rest
    return header + "\n" + content


def _workflow_claude_md(workflow: str) -> str:
    """Generate the CLAUDE.md dropped into each installed workflow directory."""
    return f"""\
# DO NOT EDIT — generated by farrier

All files in this directory are installed by **farrier** from the agent library.
Edits made here will be **overwritten** the next time `make agent-install` (or `farrier --repo .`) runs.

## Finding the canonical source

```
farrier config show | grep library_dir
```

The canonical source for this workflow is at `<library_dir>/workflows/{workflow}/`.

## Regenerating after an upstream change

```
farrier --repo .
```
"""


class Renderer:
    def __init__(
        self,
        repo: Path,
        prefix: str,
        repo_config: dict[str, Any],
        template_values: dict[str, Any],
        skills: list[Source],
        prompts: list[Source],
    ):
        self.repo = repo
        self.prefix = prefix
        self.repo_context = dict(repo_config)
        self.repo_context.setdefault("name", repo.name)
        self.repo_context["prefix"] = prefix
        self.repo_context["root"] = repo.as_posix()
        self.template_values = template_values
        self.skills = skills
        self.prompts = prompts
        self.skill_lookup = build_lookup(skills, prefix)
        self.prompt_lookup = build_lookup(prompts, prefix)

    def skill_source(self, name: str) -> Source:
        key = name.replace(".", "-")
        if key not in self.skill_lookup:
            raise SystemExit(f"Unknown selected skill reference: {name}")
        return self.skill_lookup[key]

    def optional_skill_source(self, name: str) -> Source | None:
        return self.skill_lookup.get(name.replace(".", "-"))

    def prompt_source(self, name: str) -> Source:
        key = name.replace(".", "-")
        if key not in self.prompt_lookup:
            raise SystemExit(f"Unknown selected prompt reference: {name}")
        return self.prompt_lookup[key]

    def optional_prompt_source(self, name: str) -> Source | None:
        return self.prompt_lookup.get(name.replace(".", "-"))

    def skill_output_path(self, name: str, target: str) -> Path:
        source = self.skill_source(name)
        generated = public_name(self.prefix, source)
        if target == "copilot-instruction":
            return (
                self.repo / ".github" / "instructions" / f"{generated}.instructions.md"
            )
        if target == "copilot":
            return self.repo / ".github" / "skills" / generated / "SKILL.md"
        if target == "codex":
            return self.repo / ".agents" / "skills" / generated / "SKILL.md"
        if target == "claude":
            return self.repo / ".claude" / "skills" / generated / "SKILL.md"
        raise SystemExit(f"Unknown skill render target: {target}")

    def prompt_output_path(self, name: str, target: str) -> Path:
        source = self.prompt_source(name)
        generated = public_name(self.prefix, source)
        if target == "copilot":
            return self.repo / ".github" / "prompts" / f"{generated}.prompt.md"
        if target == "codex":
            return self.repo / ".agents" / "prompts" / f"{generated}.prompt.md"
        if target == "claude":
            return self.repo / ".claude" / "commands" / f"{generated}.md"
        raise SystemExit(f"Unknown prompt render target: {target}")

    def skill_dir_path(self, target: str) -> Path:
        if target == "copilot":
            return self.repo / ".github" / "skills"
        if target == "codex":
            return self.repo / ".agents" / "skills"
        if target == "claude":
            return self.repo / ".claude" / "skills"
        raise SystemExit(f"Unknown skill dir target: {target}")

    def render_templates(self, content: str, target: str, from_file: Path) -> str:
        if not any(
            token in content
            for token in [
                "instruction_file(",
                "instruction_ref(",
                "skill_file(",
                "prompt_file(",
                "prompt_ref(",
                "skill_dir(",
                "isUsingInstruction(",
                "repo.",
                "template.",
                "vars.",
            ]
        ):
            return content
        env = Environment(autoescape=False, undefined=StrictUndefined)
        template = env.from_string(content)
        skill_target = "copilot-instruction" if target == "copilot" else target

        def instruction_ref(name: str) -> str:
            if self.optional_skill_source(name):
                return relative_reference(
                    from_file, self.skill_output_path(name, skill_target)
                )
            return f"generated {name} instruction file when installed"

        def prompt_ref(name: str) -> str:
            if self.optional_prompt_source(name):
                return relative_reference(
                    from_file, self.prompt_output_path(name, target)
                )
            return f"generated {name} prompt when installed"

        def skill_file(name: str) -> str:
            if self.optional_skill_source(name):
                return relative_reference(
                    from_file, self.skill_output_path(name, target)
                )
            return f"generated {name} skill when installed"

        def prompt_file_fn(name: str) -> str:
            if self.optional_prompt_source(name):
                return relative_reference(
                    from_file, self.prompt_output_path(name, target)
                )
            return f"generated {name} prompt when installed"

        def is_using_instruction(instruction_name: str) -> bool:
            """Check if this project has a specific instruction selected."""
            return self.optional_skill_source(instruction_name) is not None

        def workhorse_var(name: str) -> str:
            """Emit a runtime variable reference that workhorse will fill at run time.
            Usage in templates: {{ workhorse_var('plan_path') }}
            Output in installed file: {{ plan_path }}"""
            return "{{ " + name + " }}"

        return template.render(
            instruction_file=lambda name: (
                relative_reference(
                    from_file, self.skill_output_path(name, skill_target)
                )
                if self.optional_skill_source(name)
                else f"generated {name} instruction file when installed"
            ),
            instruction_ref=instruction_ref,
            skill_file=skill_file,
            prompt_file=prompt_file_fn,
            prompt_ref=prompt_ref,
            skill_dir=lambda: relative_reference(
                from_file, self.skill_dir_path(target)
            ),
            isUsingInstruction=is_using_instruction,
            workhorse_var=workhorse_var,
            repo=self.repo_context,
            template=self.template_values,
            vars=self.template_values,
            target=target,
        )

    def context_manifest(self, target: str) -> dict[str, Any]:
        """Per-repo manifest consumed by workhorse at run time (see workhorse/templates.py).

        Workflows now run **directly from the library** — they are never copied or
        rendered into a repo. This manifest captures exactly what the install-time
        template helpers used to resolve (``instruction_ref``/``isUsingInstruction``/
        ``template.*``/``skill_dir``), so the library-resident prompts render at run
        time. All paths are **repo-root-relative** because the agent runs with its
        working directory at the repo root (``AGENT_REPO_DIR``).
        """
        def rel(path: Path) -> str:
            return path.relative_to(self.repo).as_posix()

        instructions = {
            key: rel(self.skill_output_path(source.id, target))
            for key, source in self.skill_lookup.items()
        }
        prompts = {
            key: rel(self.prompt_output_path(source.id, target))
            for key, source in self.prompt_lookup.items()
        }
        # The manifest is a committed adapter consumed at run time with the working
        # directory AT the repo root, so pin repo.root to "." — keeping the install
        # machine's absolute path out of version control (avoids cross-machine drift).
        repo_context = {**self.repo_context, "root": "."}
        return {
            "template": self.template_values,
            "repo": repo_context,
            "vars": self.template_values,
            "instructions": instructions,
            "prompts": prompts,
            "used_skills": sorted(self.skill_lookup.keys()),
            "skill_dir": rel(self.skill_dir_path(target)),
        }

    def skill_description(
        self, source: Source, header: dict[str, str], body: str
    ) -> str:
        title = first_heading(body, public_name(self.prefix, source))
        apply_to = header.get("applyTo")
        if header.get("description"):
            return header["description"]
        if apply_to:
            return f"Use for {self.prefix} repository work involving {title}. Applies to {apply_to}."
        return f"Use for {self.prefix} repository work involving {title}."

    def generated_skill(self, source: Source, target: str, output_path: Path) -> str:
        header, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        header = {
            key: self.render_templates(value, target, output_path)
            for key, value in header.items()
        }
        body = self.render_templates(body, target, output_path).strip()
        name = public_name(self.prefix, source)
        description = self.skill_description(source, header, body)
        return f"""---
name: {name}
description: {yaml_quote(description)}
---

{body}
"""

    def render(
        self,
        agents: dict[str, bool],
        roots: set[str],
        workflows: set[str],
        workflow_meta: dict[str, str] | None = None,
    ) -> dict[Path, str]:
        outputs: dict[Path, str] = {}

        if agents.get("copilot"):
            for source in self.skills:
                output_path = self.skill_output_path(source.id, "copilot")
                outputs[output_path] = self.generated_skill(source, "copilot", output_path)

            for source in self.prompts:
                output_path = self.prompt_output_path(source.id, "copilot")
                content = self.render_templates(
                    source.path.read_text(encoding="utf-8"), "copilot", output_path
                )
                outputs[output_path] = content

            for root in roots:
                root_path = ROOTS / f"{root}.md"
                if root_path.exists():
                    for output_path in [
                        self.repo / ".github" / "copilot-instructions.md",
                        self.repo / ".github" / "agents" / "copilot-instructions.md",
                    ]:
                        content = self.render_templates(
                            root_path.read_text(encoding="utf-8"),
                            "copilot",
                            output_path,
                        )
                        outputs[output_path] = content

        if agents.get("codex"):
            for source in self.skills:
                output_path = self.skill_output_path(source.id, "codex")
                outputs[output_path] = self.generated_skill(
                    source, "codex", output_path
                )
            for source in self.prompts:
                output_path = self.prompt_output_path(source.id, "codex")
                content = self.render_templates(
                    source.path.read_text(encoding="utf-8"), "codex", output_path
                )
                outputs[output_path] = content

        if agents.get("claude"):
            for source in self.skills:
                output_path = self.skill_output_path(source.id, "claude")
                outputs[output_path] = self.generated_skill(
                    source, "claude", output_path
                )
            for source in self.prompts:
                _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
                output_path = self.prompt_output_path(source.id, "claude")
                outputs[output_path] = self.render_templates(
                    body, "claude", output_path
                )

        # Workflows are NOT installed/copied — they run directly from the library
        # (see render_agents_mk: WORKFLOW_DIR points at $(AGENTS_DIR)/workflows/$(WF)).
        # Validate the selection is known so a typo still fails loudly here.
        for workflow in workflows:
            if not (WORKFLOWS / workflow).exists():
                raise SystemExit(f"Unknown workflow: {workflow}")

        # Launcher scaffolding + the per-repo context manifest: emitted once when
        # >= 1 workflow is selected. The manifest is what makes run-from-library
        # work — workhorse renders the library prompts against it at run time.
        if workflows:
            # Emit one manifest per ENABLED assistant so a run can target the matching
            # adapters (instruction_ref → .claude/skills, .github/skills, …). AGENT_CLI
            # selects which at run time (launcher CONTEXT_FILE + workhorse auto-detect).
            enabled_assistants = [
                t for t in ("claude", "codex", "copilot") if agents.get(t)
            ]
            # The primary (first enabled) assistant also backs the generic manifest,
            # for back-compat and workhorse's AGENT_CLI-agnostic auto-detect default.
            manifest_target = enabled_assistants[0] if enabled_assistants else "claude"
            for assistant in enabled_assistants:
                outputs[self.repo / LAUNCHER_CONTEXT_MANIFEST_FMT.format(assistant)] = (
                    json.dumps(
                        self.context_manifest(assistant), indent=2, sort_keys=True
                    )
                    + "\n"
                )
            outputs[self.repo / LAUNCHER_CONTEXT_MANIFEST] = (
                json.dumps(
                    self.context_manifest(manifest_target), indent=2, sort_keys=True
                )
                + "\n"
            )
            meta = dict(workflow_meta or {})
            meta.setdefault("repo_url", "REPLACE_ME-git-remote-url")
            meta.setdefault("branch", "main")
            meta.setdefault("agents_dir", DEFAULT_AGENTS_DIR)
            meta.setdefault("repo_name", self.repo.name)
            ordered = sorted(workflows)
            outputs[self.repo / LAUNCHER_AGENTS_MK] = render_agents_mk(ordered, meta)
            outputs[self.repo / LAUNCHER_COMPOSE] = render_local_compose(meta)
            # Only emit a thin root Makefile when the repo has none — never
            # clobber a user-authored Makefile.
            root_makefile = self.repo / LAUNCHER_ROOT_MAKEFILE
            if not root_makefile.exists():
                outputs[root_makefile] = (
                    "# Thin entrypoint — includes the generated agent launcher.\n"
                    "# Generated by vigilant-octo/agents/install.py because this repo had\n"
                    "# no root Makefile. Safe to extend with your own targets; the\n"
                    "# installer will not overwrite a Makefile once it exists.\n"
                    f"include {LAUNCHER_AGENTS_MK}\n"
                )

        return outputs

    def render_local_instruction(
        self,
        skill_names: list[str],
        target: str,
        output_path: Path,
        readme_mode: str = "inline",
    ) -> str:
        parts: list[str] = []
        for skill_name in skill_names:
            source = self.skill_source(skill_name)
            _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
            part = self.render_templates(body, target, output_path).strip()
            if part:
                parts.append(part)
        rendered = "\n\n---\n\n".join(parts)

        readme = output_path.parent / "README.md"
        if readme_mode == "none" or not readme.exists():
            return rendered
        # `import` mode references the sibling README via Claude's `@` import
        # directive, so its content is pulled in by reference instead of being
        # copied into this file (keeps always-loaded files lean, single source
        # of truth). The `@` directive is Claude-specific; other targets fall
        # back to inlining the body.
        if readme_mode == "import" and target == "claude":
            return f"{rendered}\n\n## Local README\n\n@README.md\n"
        readme_body = self.render_templates(
            readme.read_text(encoding="utf-8"), target, output_path
        )
        return f"{rendered}\n\n## Local README\n\n{readme_body.strip()}\n"

    def render_scaffold(self, source: Source, output_path: Path) -> str:
        return self.render_templates(
            source.path.read_text(encoding="utf-8"), "scaffold", output_path
        )

    def validate_workflow_dependencies(self, workflow_name: str) -> list[str]:
        """Check that a workflow's dependencies are satisfied by selected skills/prompts.

        Returns a list of missing dependencies (empty if all satisfied).
        """
        workflow_root = WORKFLOWS / workflow_name
        required_skills, required_prompts = extract_workflow_dependencies(workflow_root)

        missing = []
        for skill in required_skills:
            if not self.optional_skill_source(skill):
                missing.append(
                    f"skill '{skill}' (referenced in {workflow_name} prompts)"
                )
        for prompt in required_prompts:
            if not self.optional_prompt_source(prompt):
                missing.append(
                    f"prompt '{prompt}' (referenced in {workflow_name} prompts)"
                )

        return missing


def normalize_agents(config: dict[str, Any]) -> dict[str, bool]:
    agents = config.get("agents") or {}
    if isinstance(agents, list):
        return {name: name in agents for name in ["codex", "claude", "copilot"]}
    return {
        name: bool(agents.get(name, False)) for name in ["codex", "claude", "copilot"]
    }


def collect_selection(
    config: dict[str, Any],
) -> tuple[set[str], set[str], set[str], set[str], dict[str, str], set[str]]:
    selection: dict[str, Any] = {
        "skills": set(),
        "prompts": set(),
        "roots": set(),
        "scaffolds": set(),
        "scaffold_map": {},
        "workflows": set(),
    }
    for pack in config.get("packs", []) or []:
        loaded = load_pack(str(pack))
        for key, values in loaded.items():
            selection[key].update(values)

    # Scaffolds carry both glob patterns and source→dest maps, so they are merged
    # from the parsed config rather than the plain set machinery below. Repo-level
    # mappings are applied last and override any pack-supplied defaults.
    config_patterns, config_map = parse_scaffold_entries(config.get("scaffolds"))
    selection["scaffolds"].update(config_patterns)
    selection["scaffold_map"].update(config_map)

    for key in ["skills", "prompts", "roots", "workflows"]:
        selection[key].update(config.get(key, []) or [])

    return (
        selection["skills"],
        selection["prompts"],
        selection["roots"],
        selection["scaffolds"],
        selection["scaffold_map"],
        selection["workflows"],
    )


def scaffold_mapping_for(source: Source, mappings: dict[str, str]) -> str | None:
    """Return the longest mapping key that targets this source (or None)."""
    best: str | None = None
    for key in mappings:
        if source.rel == key or source.rel.startswith(key + "/"):
            if best is None or len(key) > len(best):
                best = key
    return best


def select_scaffolds(
    sources: list[Source],
    patterns: set[str],
    mappings: dict[str, str],
    exclude_patterns: set[str],
) -> list[Source]:
    """A source is selected when a glob pattern matches it or a mapping targets it."""
    selected = [
        source
        for source in sources
        if (
            matches(source, patterns)
            or scaffold_mapping_for(source, mappings) is not None
        )
        and not matches(source, exclude_patterns)
    ]
    return sorted(selected, key=lambda item: item.id)


def scaffold_output_path(repo: Path, source: Source, mappings: dict[str, str]) -> Path:
    # An explicit mapping wins: place the source under its configured dest folder,
    # preserving any path below the matched prefix.
    key = scaffold_mapping_for(source, mappings)
    if key is not None:
        rest = source.rel[len(key) :].lstrip("/")
        return repo.joinpath(mappings[key], rest) if rest else repo / mappings[key]
    # No mapping: fall back to stripping the leading namespace segment.
    rel = Path(source.rel)
    if len(rel.parts) < 2:
        raise SystemExit(
            f"Scaffold source must include a namespace or a dest mapping: {source.rel}"
        )
    return repo.joinpath(*rel.parts[1:])


def remove_targets(repo: Path) -> None:
    for rel in TARGET_DIRS:
        path = repo / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
        ".agents/workflows",
        # Generated launcher scaffolding (always owned by the installer). The
        # root Makefile is intentionally NOT listed: a user may hand-author it,
        # and the installer must never delete or overwrite it.
        LAUNCHER_AGENTS_MK,
        LAUNCHER_COMPOSE,
        LAUNCHER_CONTEXT_MANIFEST,
    ]:
        path = repo / rel
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    # Per-assistant context manifests (agents-context.<assistant>.json) are emitted
    # only for currently-enabled assistants, so clear any prior ones by glob — a
    # disabled assistant's stale manifest must not linger.
    agents_dir = repo / ".agents"
    if agents_dir.is_dir():
        for path in agents_dir.glob("agents-context.*.json"):
            if path.is_file():
                path.unlink()


def render_expected(config: dict[str, Any], repo: Path) -> dict[Path, str]:
    repo_config = config.get("repo") or {}
    prefix = kebab(
        str(repo_config.get("prefix") or repo_config.get("name") or repo.name)
    )
    agents = normalize_agents(config)
    if not any(agents.values()):
        raise SystemExit("No agents selected in config")

    (
        include_skills,
        include_prompts,
        roots,
        include_scaffolds,
        scaffold_map,
        workflows,
    ) = collect_selection(config)
    exclude = config.get("exclude") or {}

    skills = selected_sources(
        load_sources(SKILLS, "skill"),
        include_skills,
        set(exclude.get("skills", []) or []),
    )
    prompts = selected_sources(
        load_sources(PROMPTS, "prompt"),
        include_prompts,
        set(exclude.get("prompts", []) or []),
    )
    scaffolds = select_scaffolds(
        load_scaffold_sources(SCAFFOLDS),
        include_scaffolds,
        scaffold_map,
        set(exclude.get("scaffolds", []) or []),
    )
    if not skills and not prompts and not workflows and not scaffolds:
        raise SystemExit(
            "Selected packs did not match any skills, prompts, scaffolds, or workflows"
        )

    renderer = Renderer(
        repo, prefix, repo_config, collect_template_values(config), skills, prompts
    )
    workflow_meta = resolve_workflow_meta(
        config, repo, str(repo_config.get("name") or repo.name)
    )
    workflow_meta["repo_src_default"] = repo.as_posix()
    outputs = renderer.render(agents, roots, workflows, workflow_meta)

    for source in scaffolds:
        output_path = scaffold_output_path(repo, source, scaffold_map)
        outputs[output_path] = renderer.render_scaffold(source, output_path)

    for mapping in config.get("localInstructions", []) or []:
        # A mapping may name a single skill (`skill: foo`) or several
        # (`skills: [foo, bar]`); multiple skills are aggregated into one
        # generated file, separated by a `---` markdown rule, in listed order.
        if mapping.get("skills"):
            skill_names = [str(name) for name in mapping["skills"]]
        else:
            skill_names = [str(mapping["skill"])]
        # `includeReadme` controls how a sibling README.md is folded in:
        #   inline (default) — copy the rendered README body into the file
        #   import           — reference it via Claude's `@README.md` directive
        #   none             — omit it
        # Booleans are accepted too: true → inline, false → none.
        readme_flag = mapping.get("includeReadme", "inline")
        if readme_flag is True:
            readme_mode = "inline"
        elif readme_flag is False:
            readme_mode = "none"
        else:
            readme_mode = str(readme_flag)
        if readme_mode not in ("inline", "import", "none"):
            raise SystemExit(
                f"localInstructions.includeReadme must be one of inline/import/none (got {readme_flag!r})"
            )
        for rel in mapping.get("paths", []) or []:
            directory = repo / rel
            directory_is_scaffolded = any(
                path == directory or directory in path.parents for path in outputs
            )
            if not directory.exists() and not directory_is_scaffolded:
                raise SystemExit(f"Local instruction path does not exist: {rel}")
            if agents.get("codex"):
                for filename in ["AGENTS.md", "CODEX.md"]:
                    output_path = directory / filename
                    outputs[output_path] = renderer.render_local_instruction(
                        skill_names, "codex", output_path, readme_mode
                    )
            if agents.get("claude"):
                output_path = directory / "CLAUDE.md"
                outputs[output_path] = renderer.render_local_instruction(
                    skill_names, "claude", output_path, readme_mode
                )

    return outputs


def check_outputs(repo: Path, outputs: dict[Path, str]) -> int:
    missing: list[str] = []
    changed: list[str] = []
    extra: list[str] = []
    for path, content in outputs.items():
        # Seed scaffolds (e.g. per-service .gitignore) are create-once and then
        # owned by the repository, so any local content is acceptable — never
        # report them as missing or changed.
        if is_seed_output(path):
            continue
        expected = content.rstrip() + "\n"
        if not path.exists():
            missing.append(path.relative_to(repo).as_posix())
        elif path.read_text(encoding="utf-8") != expected:
            changed.append(path.relative_to(repo).as_posix())

    expected_paths = set(outputs)
    for rel in TARGET_DIRS + [".agents/workflows"]:
        target = repo / rel
        if not target.exists():
            continue
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            if rel == ".agents/workflows" and should_skip_workflow_file(path, target):
                continue
            if path not in expected_paths:
                extra.append(path.relative_to(repo).as_posix())
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
        LAUNCHER_AGENTS_MK,
        LAUNCHER_COMPOSE,
        LAUNCHER_CONTEXT_MANIFEST,
    ]:
        path = repo / rel
        if path.exists() and path not in expected_paths:
            extra.append(path.relative_to(repo).as_posix())

    if missing or changed or extra:
        for rel in missing:
            print(f"missing: {rel}")
        for rel in changed:
            print(f"changed: {rel}")
        for rel in extra:
            print(f"extra: {rel}")
        return 1
    return 0


def ensure_gitignore_entry(repo: Path, entry: str) -> bool:
    """Append `entry` to the repo's .gitignore if not already ignored.

    Idempotent: returns True only when the file was actually modified. Matches
    on the exact stripped line so trailing-slash or comment variants don't
    cause duplicates. Creates .gitignore if it does not exist. When appending to
    a non-empty file, a blank line is inserted before the entry so it is visually
    separated from the repo's own existing rules rather than glued onto them.
    """
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if entry in {line.strip() for line in existing.splitlines()}:
        return False
    if not existing:
        prefix = ""
    else:
        prefix = existing if existing.endswith("\n") else existing + "\n"
        if not prefix.endswith("\n\n"):
            prefix += "\n"
    gitignore.write_text(f"{prefix}{entry}\n", encoding="utf-8")
    return True


def install_outputs(repo: Path, outputs: dict[Path, str]) -> None:
    remove_targets(repo)
    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        # Seed scaffolds are written only when absent so re-running the installer
        # does not clobber a repository's evolved .gitignore (or other seeds).
        if is_seed_output(path) and path.exists():
            continue
        write_text(path, content)
    # Workflow runs write logs/artifacts under .agents/runs (see render_agents_mk
    # RUNS_DIR). Keep them out of version control. Only relevant when a workflow
    # launcher was generated.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_gitignore_entry(
        repo, ".agents"
    ):
        print("Added .agents to .gitignore")


def _add_install_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to install into (default: cwd)",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to agents.yml (default: <repo>/agents.yml)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated files are current without writing",
    )
    parser.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )


def _run_install(args: argparse.Namespace) -> int:
    set_library_globals(resolve_library_dir(args.library))
    repo = args.repo.resolve()
    config_path = args.config.resolve() if args.config else repo / "agents.yml"
    config = read_yaml(config_path)
    outputs = render_expected(config, repo)
    if args.check:
        return check_outputs(repo, outputs)
    install_outputs(repo, outputs)
    print(f"Installed {len(outputs)} generated files into {repo}")
    return 0


def _run_config(args: argparse.Namespace) -> int:
    if args.config_action == "set-library":
        root = args.path.expanduser().resolve()
        if not is_library_dir(root):
            raise SystemExit(
                f"error: {root} is not a usable library directory — it must contain library/ and packs/."
            )
        write_library_dir(root)
        print(f"library_dir={root}")
        return 0

    if args.config_action == "set-stablemate":
        root = args.path.expanduser().resolve()
        write_stablemate_dir(root)
        print(f"stablemate_dir={root}")
        return 0

    # show — with a key: print bare value; without: print all as key=value
    cfg = read_config()
    if args.key:
        value = cfg.get(args.key)
        if value is None:
            raise SystemExit(f"error: '{args.key}' is not set in {CONFIG_PATH}")
        print(value)
    else:
        for key, value in cfg.items():
            print(f"{key}={value}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="farrier",
        description="Render an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters.",
    )
    sub = parser.add_subparsers(dest="command")

    # install (default)
    install_p = sub.add_parser(
        "install", help="Render/install the selected packs into a repository (default)"
    )
    _add_install_args(install_p)

    # config
    config_p = sub.add_parser("config", help="Manage the farrier home config")
    config_sub = config_p.add_subparsers(dest="config_action", required=True)
    set_lib = config_sub.add_parser(
        "set-library", help="Record the library directory in the home config"
    )
    set_lib.add_argument(
        "path", type=Path, help="Path to the library (the agents/ tree)"
    )
    set_sm = config_sub.add_parser(
        "set-stablemate", help="Record the stablemate checkout path in the home config"
    )
    set_sm.add_argument("path", type=Path, help="Path to the stablemate checkout")
    show_p = config_sub.add_parser(
        "show", help="Print all config keys as key=value lines, or a single bare value"
    )
    show_p.add_argument(
        "key",
        nargs="?",
        default=None,
        help="If given, print only the value of this key",
    )

    # version
    sub.add_parser("version", help="Print the installed farrier version")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = _build_parser()

    # Keep `farrier --repo .` working: if no recognised subcommand is given,
    # inject `install` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    _SUBCOMMANDS = {"install", "config", "version"}
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["install"] + argv

    args = parser.parse_args(argv)

    if args.command == "version":
        print(importlib.metadata.version("farrier"))
        return 0

    if args.command == "config":
        return _run_config(args)

    return _run_install(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
