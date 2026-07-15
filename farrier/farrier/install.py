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

@dataclass(frozen=True)
class Layer:
    """One library root in the resolution stack.

    ``name`` labels the layer in provenance banners and error messages. Without it,
    an overlay silently shadowing a base skill is invisible — you would open the
    base copy, edit it, and watch the overlay's copy get rendered instead.
    """

    root: Path
    name: str


# Library content resolves across an ordered stack of layers, highest precedence
# first: the overlay (--library / $FARRIER_LIBRARY_DIR / home config), then the base
# library shipped as the `stablemate-library` wheel. A higher layer shadows a lower
# one name-for-name, which is how a private overlay overrides a base skill, pack or
# workflow without forking it. Populated by ``set_layers()`` in ``main()``; a module
# global because the rendering helpers below reference it directly.
LAYERS: list[Layer] = []

BASE_LAYER_NAME = "stablemate-library (base)"

# OS-appropriate user config dir (~/.config/farrier on Linux,
# ~/Library/Application Support/farrier on macOS, %APPDATA%\farrier on Windows).
CONFIG_PATH = Path(user_config_dir("farrier")) / "config.toml"


def base_library_dir() -> Path | None:
    """The base library root, or None when the `stablemate-library` wheel is absent.

    Discovered with an *optional* import on purpose. The base package depends on
    farrier (its workflows drive this CLI), so a hard dependency the other way would
    close a cycle — and it would drag every content edit into a farrier release. With
    the wheel absent, farrier behaves exactly as it did before: overlay-only.
    """
    try:
        from stablemate_library import base_dir
    except ImportError:
        return None
    return base_dir()


def set_layers(overlay: Path | None) -> None:
    """Point the resolution stack at the overlay (if any), then the base (if installed)."""
    global LAYERS
    layers: list[Layer] = []
    if overlay is not None:
        layers.append(Layer(root=overlay, name=str(overlay)))
    base = base_library_dir()
    if base is not None:
        layers.append(Layer(root=base, name=BASE_LAYER_NAME))
    LAYERS = layers


def layer_dirs(*parts: str) -> list[tuple[Layer, Path]]:
    """(layer, dir) for every layer holding ``<root>/<parts>``, in precedence order."""
    found: list[tuple[Layer, Path]] = []
    for layer in LAYERS:
        candidate = layer.root.joinpath(*parts)
        if candidate.is_dir():
            found.append((layer, candidate))
    return found


def find_in_layers(*parts: str) -> tuple[Layer, Path] | None:
    """The highest-precedence layer holding ``<root>/<parts>``, or None."""
    for layer in LAYERS:
        candidate = layer.root.joinpath(*parts)
        if candidate.exists():
            return layer, candidate
    return None


def searched_layers() -> str:
    """The layer stack, for the 'here is where I looked' half of an error message."""
    if not LAYERS:
        return "  (no library layers — none configured, and no base library installed)"
    return "\n".join(f"  - {layer.name}" for layer in LAYERS)


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
    """A usable library root holds content: ``library/`` (skills, prompts) or ``workflows/``.

    ``packs/`` is deliberately *not* required. The base library ships workflows,
    scaffolds and the stablemate skills with no packs at all — a repo selects from it
    directly in ``agents.yml`` (``skills: [stablemate/*]``), and packs remain a
    convenience an overlay may add.
    """
    return (path / "library").is_dir() or (path / "workflows").is_dir()


def resolve_library_dir(cli_library: Path | None) -> Path | None:
    """Resolve the *overlay* library root: --library > $FARRIER_LIBRARY_DIR > home config.

    Returns None when no overlay is configured but a base library is installed — the
    base alone is a usable library, so that is a supported setup, not an error. Exits
    with a setup hint only when there is neither an overlay nor a base, or when a
    configured path is not a usable library directory.
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
        if base_library_dir() is not None:
            return None
        raise SystemExit(
            "error: no library available — no overlay configured, and the base "
            "library is not installed.\n"
            "Install the base:\n"
            "    pip install stablemate-library\n"
            "or point farrier at an overlay library:\n"
            "    farrier config set-library <path-to-your-library>\n"
            "(or pass --library DIR / set $FARRIER_LIBRARY_DIR)."
        )

    root = candidate.expanduser().resolve()
    if not is_library_dir(root):
        raise SystemExit(
            f"error: {root} (from {source}) is not a usable library directory "
            "— it must contain library/ or workflows/."
        )
    return root


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
    # Which library layer this source was read from. None only for sources built
    # outside the layer stack (tests); everything ``load_sources`` produces has one.
    layer: Layer | None = None


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


def library_source_path(source: Source) -> str:
    """The source's path within the prompt library, for provenance banners.

    Anchored at the last ``library/`` segment so the result is machine-independent
    (e.g. ``library/skills/go/go-qa/SKILL.md``) — identical across machines and
    therefore stable under ``--check``. Falls back to ``source.rel`` if the path is
    not under a ``library/`` tree (it always is for skills/prompts).
    """
    parts = source.path.parts
    if "library" in parts:
        idx = len(parts) - 1 - parts[::-1].index("library")
        return Path(*parts[idx:]).as_posix()
    return source.rel


# A generated skill/command is a *copy* of a library source. Without a marker, an
# agent editing it "fixes" the copy — losing the change on the next `make
# agent-install`. We stamp the single source of truth into a `metadata` front-matter
# field so the edit lands in the library instead. Skills carry it natively (openskill
# format: openskill.sh/docs/creators/skill-format); Claude commands carry the same
# block — the slash-command parser (and claude-code-acp) ignores keys it does not
# recognise, so `metadata` is inert to the agent. Codex/copilot prompts are left
# untouched; aggregated Claude instruction files get an HTML-comment banner instead
# (see local_instruction_banner).
def skill_metadata_block(source: Source, dest_rel: str) -> str:
    """The `metadata:` block stamping a generated skill/command with its source.

    *dest_rel* is the generated file's repo-root-relative path — it makes the
    `resolve:` field a copy-pasteable command that turns the (machine-independent,
    library-anchored) `source:` back into this machine's absolute editable path via
    ``farrier source`` (which reuses the same library resolution as install). The
    header stays portable: no absolute path is baked in, so it is stable across
    machines and under ``--check``.

    Returns the YAML lines (newline-terminated) to splice into the front matter.
    """
    do_not_edit = (
        "generated — run the `resolve` command below for this machine's editable "
        "source path, edit that, then `make agent-install` to regenerate"
    )
    return (
        "metadata:\n"
        "  generated_by: farrier\n"
        f"  source: {library_source_path(source)}\n"
        f"  resolve: {yaml_quote(f'farrier source {dest_rel}')}\n"
        f"  do_not_edit: {yaml_quote(do_not_edit)}\n"
    )


# Aggregated instruction files (localInstructions → CLAUDE.md) cannot carry YAML
# front matter — Claude injects them into context verbatim, so a `metadata:` block
# would read as instructions. Provenance rides in a block-level HTML comment
# instead: Claude strips those before *context injection*, but anyone (human or
# agent) opening the file to edit it sees the comment raw — exactly the audience
# that must be redirected to the library source. Only the claude target gets it;
# other agents do not strip comments.
def local_instruction_banner(sources: list[Source], dest_rel: str) -> str:
    """The DO-NOT-EDIT comment prepended to generated Claude instruction files.

    *dest_rel* is the generated file's repo-root-relative path — like
    skill_metadata_block's `resolve:` field, it makes the banner's resolve line a
    copy-pasteable ``farrier source`` command that turns the library-anchored
    source paths into this machine's absolute editable paths, keeping the banner
    itself portable and stable under ``--check``.
    """
    source_lines = "\n".join(f"  {library_source_path(s)}" for s in sources)
    return (
        "<!--\n"
        "DO NOT EDIT — generated by farrier from the agent library.\n"
        "Edits here are overwritten by `make agent-install` (or: farrier --repo .).\n"
        "Edit the library source(s) instead, then regenerate:\n"
        f"{source_lines}\n"
        f"Editable paths on this machine: `farrier source {dest_rel}`\n"
        "Skill→path mapping: agents.yml → localInstructions\n"
        "-->\n\n"
    )


def banner_sources(text: str) -> list[str]:
    """Library source paths listed in a generated file's leading HTML banner.

    Last-resort provenance for `farrier source`: the banner is a snapshot from
    generation time, so it is only consulted when no agents.yml is found above
    the file — the live localInstructions mapping always wins when available.
    Returns [] when the file does not start with a farrier banner.
    """
    match = re.match(r"\A<!--\n(?P<banner>.*?)\n-->", text, flags=re.DOTALL)
    if not match or "generated by farrier" not in match.group("banner"):
        return []
    return re.findall(r"^\s+(library/\S+)$", match.group("banner"), flags=re.MULTILINE)


def mapping_skill_names(mapping: dict[str, Any]) -> list[str]:
    """The installed skill names a localInstructions mapping selects.

    A mapping names a single skill (`skill: foo`) or several (`skills: [foo,
    bar]`); multiple skills are aggregated into one generated file, separated by
    a `---` markdown rule, in listed order.
    """
    if mapping.get("skills"):
        return [str(name) for name in mapping["skills"]]
    return [str(mapping["skill"])]


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


def load_sources(root: Path, kind: str, layer: Layer | None = None) -> list[Source]:
    sources: list[Source] = []
    # Load SKILL.md files (new open skill format: <name>/SKILL.md).
    # Also support flat *.md files for backwards compatibility during migration.
    for path in sorted(
        list(root.rglob("SKILL.md"))
        + [p for p in root.rglob("*.md") if p.name != "SKILL.md"]
    ):
        rel = path.relative_to(root).as_posix()
        sources.append(
            Source(
                kind=kind, path=path, rel=rel, id=source_id(root, path), layer=layer
            )
        )
    return sources


def load_layered_sources(kind: str, *parts: str) -> list[Source]:
    """Sources of one kind across every layer, with the higher layer winning.

    Ids are computed relative to each layer's own content root, so ``stablemate/ostler``
    means the same thing in the overlay and in the base — which is exactly what makes
    shadowing work: an overlay skill with a base skill's id replaces it wholesale.
    """
    by_id: dict[str, Source] = {}
    for layer, root in layer_dirs(*parts):
        for source in load_sources(root, kind, layer):
            # layer_dirs is precedence-ordered, so the first writer of an id wins.
            by_id.setdefault(source.id, source)
    return sorted(by_id.values(), key=lambda source: source.id)


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


def frontmatter_metadata(text: str) -> dict[str, Any]:
    """Parse a generated file's YAML front matter and return its `metadata` mapping.

    Uses a real YAML parse (not the flat line-splitter in ``split_front_matter``)
    because the provenance is a *nested* block. Returns ``{}`` for a file with no
    front matter, no `metadata:` block, or malformed YAML.
    """
    match = re.match(r"\A---\n(?P<header>.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group("header")) or {}
    except yaml.YAMLError:
        return {}
    meta = data.get("metadata") if isinstance(data, dict) else None
    return meta if isinstance(meta, dict) else {}


def first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def parse_scaffold_ids(entries: Any, origin: str) -> set[str]:
    """A `scaffolds` list names scaffold definition ids (see `farrier scaffold`).

    Each entry must be a plain string id. The legacy `{source-prefix: dest-dir}`
    mapping form (from the install-time file-tree scaffolds) is rejected with a
    migration hint — placement now comes from scaffold params at invocation time.
    """
    ids: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, str):
            raise SystemExit(
                f"{origin}: scaffolds entries must be scaffold ids (strings); "
                f"got {entry!r}. File-tree scaffolds were replaced by scaffold "
                "definitions — run `farrier scaffold <id> --param key=value` and "
                "list the available ids under `scaffolds:`."
            )
        ids.add(entry)
    return ids


def load_pack(pack_id: str, seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    if pack_id in seen:
        raise SystemExit(f"Pack include cycle detected at {pack_id}")
    seen.add(pack_id)

    hit = find_in_layers("packs", f"{pack_id}.yml")
    if hit is None:
        raise SystemExit(
            f"error: unknown pack: {pack_id}\n"
            f"No library layer provides it. Searched:\n{searched_layers()}\n"
            "If this pack lives in a private overlay library, point farrier at it:\n"
            "    farrier config set-library <path-to-your-library>"
        )
    _layer, path = hit
    data = read_yaml(path)

    merged: dict[str, Any] = {
        "skills": set(data.get("skills", []) or []),
        "prompts": set(data.get("prompts", []) or []),
        "roots": set(data.get("roots", []) or []),
        "scaffolds": parse_scaffold_ids(data.get("scaffolds"), f"pack {pack_id}"),
        "workflows": set(data.get("workflows", []) or []),
    }
    for include in data.get("includes", []) or []:
        child = load_pack(str(include), seen)
        for key, values in child.items():
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
) -> dict[str, Any]:
    """Resolve repo_url / branch / agents-dir for the launcher scaffolding.

    Precedence: explicit `agents.yml` `workflow:` block, then the repo's own
    git origin + DEFAULT branch (master/main — NOT the branch currently checked
    out), then a clearly-marked placeholder. REPO_BRANCH is the trunk the worker
    clones and the coder workflow targets/merges PRs into, so it must be the
    long-lived integration branch, not the install-time HEAD. An explicit repo URL
    selects authenticated remote checkout; otherwise local runs clone a read-only
    bind mount of the host repository.
    """
    workflow_cfg = config.get("workflow") or {}
    if not isinstance(workflow_cfg, dict):
        raise SystemExit("workflow must be a YAML mapping when present")

    repo_url = workflow_cfg.get("repoUrl") or workflow_cfg.get("repo_url")
    remote_checkout = bool(repo_url)
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
        "remote_checkout": remote_checkout,
    }


def render_agents_mk(workflows: list[str], meta: dict[str, Any]) -> str:
    """Generic, workflow-name-parameterized make launcher (.agents/agents.mk).

    ALWAYS generated: its regeneration targets (`agent-install`/`agent-check`)
    are useful for a skills/prompts-only repo too, and a root Makefile can then
    `include` it unconditionally. The workflow-run configuration and targets
    (`agent-run`, `agent-native`, `agent-build`, …) are only emitted when >= 1
    workflow is installed.

    Mirrors the assembler Makefile (COMPOSE = base + override layering, ENVV with
    WORKFLOW_DIR / REPO_SRC / REPO_BRANCH / REPO_NAME, native via uv run) but uses
    NEUTRAL `agent-*` target names and a `WF` variable defaulting to the first
    installed workflow. No 'hrnet' / 'research' / 'assembler' hardcoding.
    """
    has_wf = bool(workflows)
    default_wf = workflows[0] if has_wf else ""
    workflow_list = " ".join(workflows) if has_wf else "(none — skills/prompts only)"

    if has_wf:
        usage = f"""#   make agent-run                 # Docker + local clone (default WF={default_wf})
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
#   make agent-check               # verify adapters are up to date (no writes)"""
    else:
        usage = """#   make agent-install             # regenerate the agent adapters from the library
#   make agent-check               # verify adapters are up to date (no writes)
#
# No workflows are installed in this repo, so the workflow-run targets
# (agent-run / agent-native / agent-build / …) are omitted. Add a workflow to
# this repo's agents.yml and re-run `make agent-install` to get them."""

    header = f"""# Agent launcher — workhorse quick start (generated).
#
# Generated by farrier (the prompt-library installer). Do not edit by hand;
# re-run `make agent-install` to regenerate. Include it from a root Makefile:
#
#   include .agents/agents.mk
#
# Installed workflows: {workflow_list}
#
# Usage:
{usage}
"""

    core = """
AGENTS_DIR     ?= $(shell farrier config show library_dir)
# Public stablemate checkout (workhorse runtime + farrier installer source).
# Needed only for Docker runs and SRC=1 local-source runs.
STABLEMATE_DIR ?= $(shell farrier config show stablemate_dir)

# farrier regenerates these adapters from the prompt library. Default uses the
# installed farrier binary. SRC=1 runs the local source under $(STABLEMATE_DIR)/farrier.
# The library CONTENT is located via `farrier config set-library`; when a
# vigilant-octo checkout exists at $(AGENTS_DIR) we pass --library explicitly.
ifeq ($(SRC),1)
FARRIER ?= uv run --project $(STABLEMATE_DIR)/farrier farrier
endif
FARRIER ?= farrier
FARRIER_LIB_ARG := $(if $(wildcard $(AGENTS_DIR)/library),--library "$(AGENTS_DIR)",)
"""

    wf_vars = ""
    wf_targets = ""
    phony_wf = ""
    if has_wf:
        placeholder = meta["repo_url"].startswith("REPLACE_ME")
        repo_url_line = (
            f"REPO_URL     ?= {meta['repo_url']}"
            if not placeholder
            else f"# REPO_URL: set me to the git remote (only used by GitHub-default runs,\n"
            f"# not the default local bind-mount clone). Auto-detection found no origin.\n"
            f"REPO_URL     ?= {meta['repo_url']}"
        )
        wf_vars = f"""
LOCAL_WORKER   := $(STABLEMATE_DIR)/workhorse
# WF selects which workflow to run; defaults to the first selected.
WF           ?= {default_wf}
# AGENT_CLI selects the agent backend: claude (default) | codex | copilot. Native
# runs check that this CLI is on PATH and forward it to workhorse; it also selects
# the per-assistant context manifest below.
AGENT_CLI    ?= claude
# Workflows run straight from the library — not copied into this repo. A workflow may
# live in the configured overlay OR in the base library wheel (site-packages), so the
# launcher does NOT build a path: it passes the workflow NAME and lets workhorse resolve
# it across the same layers farrier uses. Set WORKFLOW_DIR to pin a specific checkout.
WORKFLOW_DIR ?=
WORKFLOW_ARG := $(if $(WORKFLOW_DIR),$(WORKFLOW_DIR)/workflow.yaml,$(WF))
# Per-repo context manifest the library prompts render against (generated by
# `make agent-install`). Prefer the per-assistant manifest for $(AGENT_CLI) so a
# Codex/Copilot run resolves instruction_ref to its own adapters; fall back to the
# generic one. workhorse also auto-detects this from AGENT_REPO_DIR + AGENT_CLI.
CONTEXT_FILE ?= $(firstword $(wildcard $(CURDIR)/.agents/agents-context.$(AGENT_CLI).json) $(CURDIR)/.agents/agents-context.json)
REPO_NAME    ?= {meta["repo_name"]}
REPO_BRANCH  ?= {meta["branch"]}
{repo_url_line}
REPO_CONFIG  ?= $(CURDIR)/agents.yml
# Compose project name (default = first compose file's directory) → volume prefix.
PROJECT      ?= local-worker
# Native runs use the installed workhorse binary by default.
# SRC=1 runs workhorse from the local stablemate source checkout via uv.
# An explicit WORKHORSE=... overrides both.
ifeq ($(SRC),1)
WORKHORSE         ?= uv run --project $(LOCAL_WORKER) workhorse
WORKHORSE_VERSION ?= $(shell grep -m1 '^version' $(LOCAL_WORKER)/pyproject.toml 2>/dev/null | cut -d'"' -f2) (local source: $(LOCAL_WORKER))
endif
WORKHORSE         ?= workhorse
WORKHORSE_VERSION ?= $(shell workhorse --version 2>/dev/null || echo unknown) (installed)

# Optional run knobs forwarded to workhorse (native targets):
#   RUN_ID      names the stable run dir (<workflow>-<RUN_ID>); default "default".
#   PARAMS      inline JSON of workflow params, e.g. '{{"program":"hrnet-research"}}'.
#   PARAMS_FILE path to a JSON file of workflow params (same effect as PARAMS).
AGENT_ARGS := $(if $(RUN_ID),--run-id "$(RUN_ID)") $(if $(PARAMS),--params '$(PARAMS)') $(if $(PARAMS_FILE),--params-file "$(PARAMS_FILE)")

# Layer the local-run override on top of the generic worker compose. Each
# installed workflow is its own named service in local.compose.yaml (sharing one
# build via a YAML anchor) — $(WF) below selects which one runs.
COMPOSE := docker compose -p $(PROJECT) \\
\t-f $(LOCAL_WORKER)/compose.yaml \\
\t-f $(CURDIR)/.agents/local.compose.yaml
ENVV := PROJECT="$(PROJECT)" LOCAL_WORKER="$(LOCAL_WORKER)" STABLEMATE_DIR="$(STABLEMATE_DIR)" AGENTS_DIR="$(AGENTS_DIR)" REPO_SRC="$(CURDIR)" REPO_URL="$(REPO_URL)" REPO_CONFIG="$(REPO_CONFIG)" REPO_BRANCH="$(REPO_BRANCH)" REPO_NAME="$(REPO_NAME)"

# Per-workflow run log + pid (under the gitignored .agents/runs/).
RUNS_DIR     := $(CURDIR)/.agents/runs
LOG          := $(RUNS_DIR)/$(WF).log
PID          := $(RUNS_DIR)/$(WF).pid
"""
        phony_wf = " agent-run agent-native agent-native-bg agent-build agent-hello agent-logs agent-container-logs agent-stop agent-down agent-clean agent-reseed-auth agent-artifacts"
        wf_targets = """
agent-run: ## Run the selected workflow (Docker, local clone). Override with WF=<name>
\t@mkdir -p $(RUNS_DIR)
\t@bash -o pipefail -c '$(ENVV) $(COMPOSE) up --abort-on-container-exit --exit-code-from $(WF) $(WF) 2>&1 | tee "$(LOG)"'

agent-native: ## Run natively (no Docker, pipx) on THIS tree; logs tee'd to .agents/runs/$(WF).log
\t@mkdir -p $(RUNS_DIR)
\t@command -v $(AGENT_CLI) >/dev/null || { echo "error: '$(AGENT_CLI)' CLI not on PATH (set AGENT_CLI=claude|codex|copilot)"; exit 1; }
\t@echo "using workhorse-agent $(WORKHORSE_VERSION) (AGENT_CLI=$(AGENT_CLI))"
\tPYTHONUNBUFFERED=1 AGENT_CLI="$(AGENT_CLI)" AGENT_REPO_DIR="$(CURDIR)" $(WORKHORSE) \\
\t\t--workflow $(WORKFLOW_ARG) --context-file $(CONTEXT_FILE) --runs-dir $(RUNS_DIR) $(AGENT_ARGS) 2>&1 | tee $(LOG)

agent-native-bg: ## Detached native run; saves pid to .agents/runs/$(WF).pid (watch: make agent-logs)
\t@mkdir -p $(RUNS_DIR)
\t@command -v $(AGENT_CLI) >/dev/null || { echo "error: '$(AGENT_CLI)' CLI not on PATH (set AGENT_CLI=claude|codex|copilot)"; exit 1; }
\t@echo "using workhorse-agent $(WORKHORSE_VERSION) (AGENT_CLI=$(AGENT_CLI))"
\t@PYTHONUNBUFFERED=1 AGENT_CLI="$(AGENT_CLI)" AGENT_REPO_DIR="$(CURDIR)" nohup $(WORKHORSE) \\
\t\t--workflow $(WORKFLOW_ARG) --context-file $(CONTEXT_FILE) --runs-dir $(RUNS_DIR) $(AGENT_ARGS) >$(LOG) 2>&1 </dev/null & \\
\t\techo $$! >$(PID); echo "started native run (pid $$(cat $(PID))) — follow: make agent-logs WF=$(WF) ; stop: make agent-stop WF=$(WF)"

agent-build: ## Rebuild the worker image, then run the workflow
\t@mkdir -p $(RUNS_DIR)
\t@bash -o pipefail -c '$(ENVV) $(COMPOSE) up --build --abort-on-container-exit --exit-code-from $(WF) $(WF) 2>&1 | tee "$(LOG)"'

agent-hello: ## Smoke-test the worker + auth with the hello-world workflow
\tWORKFLOW_DIR="$(AGENTS_DIR)/workflows/hello-world" PROJECT="$(PROJECT)" docker compose -p $(PROJECT) -f $(LOCAL_WORKER)/compose.yaml up --abort-on-container-exit

agent-logs: ## Follow the current run's log (.agents/runs/$(WF).log)
\t@mkdir -p $(RUNS_DIR); touch $(LOG); tail -n +1 -F $(LOG)

agent-container-logs: ## Follow the Docker worker container's logs
\tdocker logs -f $(PROJECT)-$(WF)-1

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
"""

    return f"""{header}{core}{wf_vars}
.DEFAULT_GOAL := help

.PHONY: help{phony_wf} agent-install agent-check

help: ## Show available targets
\t@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \\
\t\tawk 'BEGIN{{FS=":.*?## "}}{{printf "  \\033[36m%-22s\\033[0m %s\\n", $$1, $$2}}'
{wf_targets}
agent-install: ## Regenerate the agent adapters/skills/workflows from the prompt library
\t$(FARRIER) --repo "$(CURDIR)" $(FARRIER_LIB_ARG)

agent-check: ## Verify generated agent adapters are up to date (no writes)
\t@$(FARRIER) --repo "$(CURDIR)" --check $(FARRIER_LIB_ARG) \\
\t\t&& echo "✓ agent files are up to date" \\
\t\t|| {{ echo "↑ files above would be rewritten by 'make agent-install'"; exit 1; }}
"""


def render_local_compose(workflows: list[str], meta: dict[str, Any]) -> str:
    """Generic local-run compose override (.agents/local.compose.yaml).

    One named service per installed workflow (e.g. `coder:`, `author:`), sharing
    a single build definition — and image tag, so compose builds it only once —
    via the `x-agent-build`/`x-agent-image` anchors below. An explicit
    ``workflow.repoUrl`` clones the remote with the configured token; otherwise
    each service clones a read-only bind mount of the host working tree.
    """
    src_target = f"/mnt/{kebab(meta['repo_name'])}-src"
    remote_checkout = bool(meta.get("remote_checkout"))
    agents = meta.get("agents") or {}
    claude_enabled = bool(agents.get("claude"))
    if remote_checkout:
        repo_environment = (
            f"      # Explicit agents.yml workflow.repoUrl: clone the remote repository.\n"
            f"      REPO_URL: ${{REPO_URL:-{meta['repo_url']}}}\n"
            "      AGENT_CONFIG_FILE: /repo-config/agents.yml\n"
        )
        repo_source_mount = (
            "      - type: bind\n"
            f"        source: ${{REPO_CONFIG:-{meta.get('repo_config_default', './agents.yml')}}}\n"
            "        target: /repo-config/agents.yml\n"
            "        read_only: true\n"
        )
        checkout_description = (
            "# Each service clones the remote configured by agents.yml workflow.repoUrl.\n"
            "# Workflow scripts own authentication using opaque envPassthrough values;\n"
            "# Farrier does not interpret credential configuration.\n"
            "# Each clone lives in that workflow's own workspace volume.\n"
        )
    else:
        repo_environment = (
            "      # No explicit workflow.repoUrl: clone the read-only host checkout.\n"
            f"      REPO_URL: {src_target}\n"
        )
        repo_source_mount = (
            "      - type: bind\n"
            f"        source: ${{REPO_SRC:-{meta.get('repo_src_default', '.')}}}\n"
            f"        target: {src_target}\n"
            "        read_only: true\n"
        )
        checkout_description = (
            "# Each service clones this repo from a READ-ONLY bind mount of your working\n"
            "# tree instead of GitHub, so the host working tree is never mutated.\n"
            "# Each clone lives in that workflow's own workspace volume.\n"
        )
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

    claude_environment_block = ""
    claude_credentials_mount = ""
    if claude_enabled:
        claude_environment_block = (
            "      CLAUDE_CODE_OAUTH_TOKEN: ${CLAUDE_CODE_OAUTH_TOKEN:-}\n"
        )
        claude_credentials_mount = """      # Claude subscription credentials — seeded into /claude-state by the workhorse entrypoint.
      - type: bind
        source: ${HOME}/.claude/.credentials.json
        target: /mnt/claude-credentials.json
        read_only: true
"""

    # Docker-outside-of-Docker: lets the coder container bring up this product's
    # own dev stack (docker compose) for QA against the story's `## Verification
    # setup` stack (see coder/prompts/qa-story.md's qa_stack handling), as a
    # sibling container on the host daemon. Only coder needs this — author never
    # runs a dev stack.
    docker_sock_block = (
        "      - type: bind\n"
        "        source: /var/run/docker.sock\n"
        "        target: /var/run/docker.sock\n"
    )

    services = "".join(
        f"""  {wf}:
    image: *agent-image
    build: *agent-build
    # Run the workflow container as nobody from process start; mounted volumes
    # must already be writable by this container user.
    user: "nobody"
    extra_hosts:
      # Lets the container's groom-sidecar — installed as an editable uv tool
      # when the GROOM_SRC bind below is set — reach a loopback-bound `groom`
      # dashboard on the host, regardless of which docker network this compose
      # project uses.
      #
      # NOTE (native Linux Docker Engine): host-gateway resolves to the
      # docker bridge's own gateway IP (e.g. 172.17.0.1), NOT the host's real
      # loopback interface — that equivalence only holds on Docker Desktop's
      # (Mac/Windows) VM-proxied host.docker.internal. `groom serve` therefore
      # defaults to binding 0.0.0.0 (reachable over the bridge); if you override
      # it with --host, use the bridge IP, not 127.0.0.1.
      - "host.docker.internal:host-gateway"
    environment:
{claude_environment_block}      # Workflow runtime.
      WORKFLOW_PATH: /workflow/workflow.yaml
      AGENT_RUNS_DIR: /runs
      DISABLE_AUTOUPDATER: "1"
{repo_environment}
      REPO_BRANCH: ${{REPO_BRANCH:-{meta["branch"]}}}
      # Repository name → /workspace/$REPO_NAME inside the container.
      REPO_NAME: ${{REPO_NAME:-{meta["repo_name"]}}}
      # Scripts (e.g. author's load-config.py) resolve the consuming repo via
      # this var rather than CWD — mirrors the native `agent-run` target's
      # AGENT_REPO_DIR="$(CURDIR)", but here CWD is /app (the image's WORKDIR),
      # not the checkout_workspace() clone under /workspace.
      AGENT_REPO_DIR: /workspace/${{REPO_NAME:-{meta["repo_name"]}}}
{passthrough_block}    volumes:
{claude_credentials_mount}      - type: bind
        source: ${{AGENTS_DIR:-{meta["agents_dir"]}}}/workflows/{wf}
        target: /workflow
{repo_source_mount}
      # Optional: host directory containing a .code-workspace file, for
      # multi-repo runs (or non-git sibling folders that can't be cloned — see
      # workhorse/workhorse/scriptutil.py's checkout_workspace()). Uncomment and
      # set WORKSPACE_DIR_HOST; point the workspace-file env var (e.g.
      # CODER_WORKSPACE, forwarded via envPassthrough above) at this mount's
      # target below, not the host path.
      # - type: bind
      #   source: ${{WORKSPACE_DIR_HOST:?Set WORKSPACE_DIR_HOST}}
      #   target: /mnt/workspace-host
      # Optional: the groom-sidecar (dashboard monitoring + live reload). groom is
      # not baked into the image; uncomment this and set GROOM_SRC to your host
      # `groom/` checkout (e.g. .../stablemate/groom) to have the entrypoint
      # install it as an editable uv tool from the bind. Edits then reach the
      # sidecar via a `reload` over the socket (or `docker restart`) with no image
      # rebuild — the `pipx install --editable` model. Omit it and the workflow
      # runs without a sidecar.
      # - type: bind
      #   source: ${{GROOM_SRC:?Set GROOM_SRC to your host groom/ checkout}}
      #   target: /mnt/groom-src
      #   read_only: true
      - type: volume
        source: workspace-{wf}
        target: /workspace
      - type: volume
        source: claude-state
        target: /claude-state
      - type: volume
        source: runs
        target: /runs
{docker_sock_block if wf == "coder" else ""}
"""
        for wf in workflows
    )

    # Each workflow gets its OWN repo checkout volume — author and coder must
    # never share a `/workspace/<repo>` clone. They run independently and on
    # different schedules; a shared volume means whichever one starts second
    # inherits (and can reset-clobber) the other's in-progress working tree.
    # claude-state/runs stay shared: they're keyed by workflow via env
    # (AGENT_RUNS_DIR subpaths, per-session Claude state), not by volume.
    workspace_volumes = "".join(f"  workspace-{wf}:\n" for wf in workflows)

    return f"""# Local-run override for the agent launcher (generated).
#
# Generated by farrier. Layered on top of the shared workhorse compose file:
#   docker compose -f <local-worker>/compose.yaml -f .agents/local.compose.yaml up <WF>
# (the `make agent-run WF=<name>` target does this for you).
#
# One named service per installed workflow ({", ".join(workflows)}), all sharing
# a single build definition and image tag via the anchors below — the image is
# built once no matter how many workflow services run (`docker compose up
# {" ".join(workflows)}` runs them together from this one file).
#
{checkout_description}# Workflow workspace volumes are never shared.
# checkout_workspace() only fast-forwards a clean checkout to the configured
# committed state on $REPO_BRANCH; if the container's copy has uncommitted
# changes or commits not yet on origin/$REPO_BRANCH (e.g. a run that blocked
# mid-way), it leaves the checkout alone so that work survives a restart.
x-agent-image: &agent-image ${{PROJECT:-local-worker}}-agent
x-agent-build: &agent-build
  # Build context is the uv workspace ROOT, not the workhorse dir — the
  # Dockerfile needs the workspace's pyproject.toml/uv.lock (workhorse is a
  # workspace member and has no lock file of its own).
  context: ${{STABLEMATE_DIR:?Set STABLEMATE_DIR (see agents.mk)}}
  dockerfile: workhorse/Dockerfile

services:
{services}
volumes:
{workspace_volumes}"""


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
        self.repo_context.setdefault("name", kebab(repo.name))
        self.repo_context["prefix"] = prefix
        self.repo_context["root"] = repo.as_posix()
        self.template_values = template_values
        self.skills = skills
        self.prompts = prompts
        self.skill_lookup = build_lookup(skills, prefix)
        self.prompt_lookup = build_lookup(prompts, prefix)

    def skill_source(self, name: str) -> Source:
        source = self.optional_skill_source(name)
        if source is None:
            raise SystemExit(f"Unknown selected skill reference: {name}")
        return source

    def optional_skill_source(self, name: str) -> Source | None:
        key = name.replace(".", "-")
        source = self.skill_lookup.get(key)
        if source is None and self.prefix and not key.startswith(f"{self.prefix}-"):
            # A repo-prefixed overlay skill (e.g. acme-developer) stays
            # addressable by its generic name ("developer") so shared workflow
            # prompts can reference the repo's overlay without knowing the repo.
            source = self.skill_lookup.get(f"{self.prefix}-{key}")
        return source

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
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {yaml_quote(description)}\n"
            f"{skill_metadata_block(source, output_path.relative_to(self.repo).as_posix())}"
            "---\n"
            "\n"
            f"{body}\n"
        )

    def command_description(
        self, source: Source, header: dict[str, str], body: str
    ) -> str:
        """The `description` for a generated Claude command's front matter.

        Prefer an explicit library `description:`; otherwise fall back to the body's
        first heading (what shows in claude-code-acp's slash-command menu). This is
        the prompt analogue of ``skill_description``.
        """
        if header.get("description"):
            return header["description"]
        return first_heading(body, public_name(self.prefix, source))

    def generated_command(self, source: Source, target: str, output_path: Path) -> str:
        """Render a library prompt into a Claude slash command WITH front matter.

        Without a `description` in the front matter, claude-code-acp has nothing to
        advertise over ACP and the command never appears in Zed's autocomplete. So,
        like ``generated_skill``, we emit a header carrying the slash-command keys the
        parser recognises (description / argument-hint / model / allowed-tools) plus
        the same `metadata:` provenance block skills get. Farrier-internal keys
        (`agent`, `name`) are intentionally dropped: the command name comes from the
        filename, and `agent` only selected the backend at render time.
        """
        header, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        header = {
            key: self.render_templates(value, target, output_path)
            for key, value in header.items()
        }
        body = self.render_templates(body, target, output_path).strip()
        lines = [
            "---",
            f"description: {yaml_quote(self.command_description(source, header, body))}",
        ]
        # Pass through the optional slash-command keys when the library author set
        # them (accepting both kebab and camelCase spellings in the source).
        for key, aliases in (
            ("argument-hint", ("argument-hint", "argumentHint")),
            ("model", ("model",)),
            ("allowed-tools", ("allowed-tools", "allowedTools")),
        ):
            value = next((header[a] for a in aliases if header.get(a)), None)
            if value:
                lines.append(f"{key}: {yaml_quote(value)}")
        dest_rel = output_path.relative_to(self.repo).as_posix()
        lines.append(skill_metadata_block(source, dest_rel).rstrip("\n"))
        lines.append("---")
        return "\n".join(lines) + "\n\n" + f"{body}\n"

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
                root_hit = find_in_layers("library", "roots", f"{root}.md")
                if root_hit is not None:
                    _root_layer, root_path = root_hit
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
                output_path = self.prompt_output_path(source.id, "claude")
                outputs[output_path] = self.generated_command(
                    source, "claude", output_path
                )

        # Workflows are NOT installed/copied — they run directly from whichever library
        # layer holds them (see render_agents_mk: the launcher passes the workflow NAME
        # and workhorse resolves it across the same layers).
        # Validate the selection is known so a typo still fails loudly here.
        for workflow in workflows:
            if find_in_layers("workflows", workflow) is None:
                raise SystemExit(
                    f"error: unknown workflow: {workflow}\n"
                    f"No library layer provides it. Searched:\n{searched_layers()}"
                )

        # The launcher (.agents/agents.mk) is generated for EVERY repo: its
        # agent-install/agent-check targets are useful even with no workflow, and
        # a root Makefile can then include it unconditionally. render_agents_mk
        # only emits the workflow-run targets when >= 1 workflow is installed.
        meta = dict(workflow_meta or {})
        meta.setdefault("repo_url", "REPLACE_ME-git-remote-url")
        meta.setdefault("branch", "main")
        meta.setdefault("agents_dir", DEFAULT_AGENTS_DIR)
        meta.setdefault("repo_name", kebab(self.repo.name))
        meta["agents"] = dict(agents)
        ordered = sorted(workflows)
        outputs[self.repo / LAUNCHER_AGENTS_MK] = render_agents_mk(ordered, meta)

        # The per-repo context manifest + local compose override are what make a
        # run-from-library work, so they are only emitted when a workflow exists.
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
            outputs[self.repo / LAUNCHER_COMPOSE] = render_local_compose(ordered, meta)

        # Only emit a thin root Makefile when the repo has none — never clobber a
        # user-authored Makefile. When one already exists, the generated launcher
        # is wired into it instead via ensure_makefile_include() at install time
        # (an idempotent include block), so its agent targets are reachable either
        # way. Both paths run regardless of workflows, since the launcher is too.
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
        sources: list[Source] = []
        for skill_name in skill_names:
            source = self.skill_source(skill_name)
            sources.append(source)
            _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
            part = self.render_templates(body, target, output_path).strip()
            if part:
                parts.append(part)
        rendered = "\n\n---\n\n".join(parts)
        # Claude strips block-level HTML comments before loading CLAUDE.md, so the
        # banner never reaches the agent's context; other targets would feed it in.
        banner = ""
        if target == "claude":
            dest_rel = output_path.relative_to(self.repo).as_posix()
            banner = local_instruction_banner(sources, dest_rel)

        readme = output_path.parent / "README.md"
        if readme_mode == "none" or not readme.exists():
            return banner + rendered
        # `import` mode references the sibling README via Claude's `@` import
        # directive, so its content is pulled in by reference instead of being
        # copied into this file (keeps always-loaded files lean, single source
        # of truth). The `@` directive is Claude-specific; other targets fall
        # back to inlining the body.
        if readme_mode == "import" and target == "claude":
            return f"{banner}{rendered}\n\n## Local README\n\n@README.md\n"
        readme_body = self.render_templates(
            readme.read_text(encoding="utf-8"), target, output_path
        )
        return f"{banner}{rendered}\n\n## Local README\n\n{readme_body.strip()}\n"

    def validate_workflow_dependencies(self, workflow_name: str) -> list[str]:
        """Check that a workflow's dependencies are satisfied by selected skills/prompts.

        Returns a list of missing dependencies (empty if all satisfied).
        """
        hit = find_in_layers("workflows", workflow_name)
        if hit is None:
            return []
        _layer, workflow_root = hit
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
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    selection: dict[str, Any] = {
        "skills": set(),
        "prompts": set(),
        "roots": set(),
        "scaffolds": set(),
        "workflows": set(),
    }
    for pack in config.get("packs", []) or []:
        loaded = load_pack(str(pack))
        for key, values in loaded.items():
            selection[key].update(values)

    selection["scaffolds"].update(
        parse_scaffold_ids(config.get("scaffolds"), "agents.yml")
    )
    for key in ["skills", "prompts", "roots", "workflows"]:
        selection[key].update(config.get(key, []) or [])

    return (
        selection["skills"],
        selection["prompts"],
        selection["roots"],
        selection["scaffolds"],
        selection["workflows"],
    )


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
        _scaffold_ids,  # consumed by `farrier scaffold`, not by install
        workflows,
    ) = collect_selection(config)
    exclude = config.get("exclude") or {}

    skills = selected_sources(
        load_layered_sources("skill", "library", "skills"),
        include_skills,
        set(exclude.get("skills", []) or []),
    )
    prompts = selected_sources(
        load_layered_sources("prompt", "library", "prompts"),
        include_prompts,
        set(exclude.get("prompts", []) or []),
    )
    if not skills and not prompts and not workflows:
        raise SystemExit(
            "Selected packs did not match any skills, prompts, or workflows"
        )

    renderer = Renderer(
        repo, prefix, repo_config, collect_template_values(config), skills, prompts
    )
    workflow_meta = resolve_workflow_meta(
        config, repo, str(repo_config.get("name") or kebab(repo.name))
    )
    workflow_meta["repo_src_default"] = repo.as_posix()
    workflow_meta["repo_config_default"] = (repo / "agents.yml").as_posix()
    outputs = renderer.render(agents, roots, workflows, workflow_meta)

    for mapping in config.get("localInstructions", []) or []:
        skill_names = mapping_skill_names(mapping)
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
            if not directory.exists():
                raise SystemExit(
                    f"Local instruction path does not exist: {rel} "
                    "(create it first — e.g. `farrier scaffold <id>`)"
                )
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


# Managed .gitignore rules for the generated `.agents/` directory. Generated
# adapter outputs (context manifests, runs/, skills/, prompts/, workflows/) are
# ignored, but hand-authored files are tracked: the launcher Makefile and prompt
# *flavor* overrides under `.agents/flavors/`. `/.agents/*` matches only the direct
# children one level deep, so the negated `flavors/` subtree's deeper files stay
# tracked. This supersedes a bare `.agents` line, which ignored the whole directory
# and stopped git descending — making `.agents/flavors/` impossible to track.
AGENTS_GITIGNORE_BLOCK = (
    "/.agents/*",
    "!/.agents/agents.mk",
    "!/.agents/flavors/",
)


def ensure_agents_gitignore(repo: Path) -> bool:
    """Install/upgrade the managed `.agents/` ignore block in the repo's .gitignore.

    Idempotent: returns True only when the file was actually modified. Strips any
    legacy standalone `.agents` wholesale-ignore line (so git descends into
    `.agents/` and the hand-authored `flavors/` subtree can be tracked) and any
    prior copy of the managed block, then re-appends the block at the end.
    """
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    managed = set(AGENTS_GITIGNORE_BLOCK) | {".agents", ".agents/", "/.agents"}
    kept = [ln for ln in existing.splitlines() if ln.strip() not in managed]
    body = "\n".join(kept).rstrip("\n")
    prefix = f"{body}\n\n" if body else ""
    desired = prefix + "\n".join(AGENTS_GITIGNORE_BLOCK) + "\n"
    if desired == existing:
        return False
    gitignore.write_text(desired, encoding="utf-8")
    return True


MAKEFILE_INCLUDE_MARKER = "# >>> farrier: agent launcher include (generated) >>>"
MAKEFILE_INCLUDE_END = "# <<< farrier: agent launcher include <<<"


def ensure_makefile_include(repo: Path) -> bool:
    """Ensure the repo's existing root Makefile includes the generated launcher.

    When a repo already ships its own root Makefile, farrier must not clobber it —
    but the agent targets (`agent-run`/`agent-install`/`agent-check`/…) live in the
    generated ``.agents/agents.mk``, so the root Makefile has to ``include`` it to
    surface them. This appends a marked ``include .agents/agents.mk`` block at the
    *end* of the file, so the repo's own first target stays the default goal.

    Idempotent: returns True only when the file was modified. No-ops when the
    include line is already present, or when no root Makefile exists (the caller
    writes a thin one carrying the include in that case).
    """
    makefile = repo / LAUNCHER_ROOT_MAKEFILE
    if not makefile.exists():
        return False
    include_line = f"include {LAUNCHER_AGENTS_MK}"
    existing = makefile.read_text(encoding="utf-8")
    if include_line in {line.strip() for line in existing.splitlines()}:
        return False
    prefix = existing if existing.endswith("\n") else existing + "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    block = (
        f"{MAKEFILE_INCLUDE_MARKER}\n"
        "# Surfaces agent-run / agent-install / agent-check etc. from the generated\n"
        "# launcher. Re-created by `farrier install`; remove this block to opt out.\n"
        f"{include_line}\n"
        f"{MAKEFILE_INCLUDE_END}\n"
    )
    makefile.write_text(prefix + block, encoding="utf-8")
    return True


def install_outputs(repo: Path, outputs: dict[Path, str]) -> None:
    remove_targets(repo)
    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        write_text(path, content)
    # Workflow runs write logs/artifacts under .agents/runs (see render_agents_mk
    # RUNS_DIR). Keep them out of version control. Only relevant when a workflow
    # launcher was generated.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_agents_gitignore(repo):
        print("Updated .agents .gitignore rules")
    # When the repo already had a root Makefile, farrier left it untouched above —
    # wire the generated launcher into it so its agent targets are reachable.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_makefile_include(repo):
        print("Added agent launcher include to root Makefile")


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
    set_layers(resolve_library_dir(args.library))
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


def find_agents_config(start: Path) -> Path | None:
    """The nearest agents.yml at or above *start* (the repo config), or None."""
    for directory in [start, *start.parents]:
        candidate = directory / "agents.yml"
        if candidate.is_file():
            return candidate
    return None


def mapped_instruction_sources(generated: Path) -> list[str] | None:
    """Resolve a generated local-instruction file via its repo's agents.yml.

    The file's HTML banner is a generation-time snapshot; `agents.yml →
    localInstructions` is the live mapping and may have been edited since. So
    resolution walks up to the repo's agents.yml, finds the mapping targeting
    this file's directory, and turns its installed skill names into library
    source paths with the same selection/prefix machinery install uses. When
    several mappings target the directory the last one wins, mirroring install.

    Returns library-relative source paths; None when the file is not a local
    instruction file or no agents.yml exists above it (caller may fall back to
    the banner); exits when agents.yml exists but no longer maps this file —
    the file is stale, and pointing at its old sources would invite edits that
    the next install silently discards.
    """
    if generated.name not in ("CLAUDE.md", "AGENTS.md", "CODEX.md"):
        return None
    config_path = find_agents_config(generated.parent)
    if config_path is None:
        return None
    repo = config_path.parent
    config = read_yaml(config_path)
    directory = generated.parent
    skill_names: list[str] = []
    for mapping in config.get("localInstructions", []) or []:
        for rel in mapping.get("paths", []) or []:
            if (repo / rel).resolve() == directory:
                skill_names = mapping_skill_names(mapping)
    if not skill_names:
        raise SystemExit(
            f"error: {generated} is not mapped by {config_path} → "
            "localInstructions — the mapping was removed or moved, so this file "
            "is stale. Re-run `farrier --repo .` (or `make agent-install`) to "
            "regenerate or remove it."
        )
    repo_config = config.get("repo") or {}
    prefix = kebab(
        str(repo_config.get("prefix") or repo_config.get("name") or repo.name)
    )
    include_skills, _, _, _, _ = collect_selection(config)
    exclude = config.get("exclude") or {}
    skills = selected_sources(
        load_layered_sources("skill", "library", "skills"),
        include_skills,
        set(exclude.get("skills", []) or []),
    )
    renderer = Renderer(repo, prefix, repo_config, {}, skills, [])
    return [
        library_source_path(renderer.skill_source(name)) for name in skill_names
    ]


def _run_source(args: argparse.Namespace) -> int:
    """Resolve a generated file back to its editable library source path(s).

    Skills/commands carry a machine-independent, `library/`-anchored
    `metadata.source` in front matter; local instruction files resolve through
    their repo's agents.yml (see mapped_instruction_sources). Either way the
    relative path is joined under the library root resolved exactly as
    ``install`` does (`--library` > `$FARRIER_LIBRARY_DIR` > home config), so
    the printed path is the real editable source on *this* machine.
    """
    generated = args.file.resolve()
    if not generated.is_file():
        raise SystemExit(f"error: {args.file} is not a file")
    set_layers(resolve_library_dir(args.library))
    text = generated.read_text(encoding="utf-8")
    # Skills/commands stamp one source in front matter. Local instruction files
    # resolve through the repo's agents.yml — the live mapping — and only fall
    # back to their generation-time HTML banner when no agents.yml is found.
    rel_source = frontmatter_metadata(text).get("source")
    if rel_source:
        rel_sources = [rel_source]
    else:
        rel_sources = mapped_instruction_sources(generated)
        if rel_sources is None:
            rel_sources = banner_sources(text)
            if rel_sources:
                print(
                    f"note: no agents.yml found above {args.file}; resolving from "
                    "the file's banner, which may be stale.",
                    file=sys.stderr,
                )
    if not rel_sources:
        raise SystemExit(
            f"error: {args.file} has no `metadata.source` front matter and no "
            "farrier banner — it is not a farrier-generated file."
        )
    for rel in rel_sources:
        hit = find_in_layers(rel)
        if hit is None or not hit[1].is_file():
            raise SystemExit(
                f"error: source '{rel}' does not exist in any library layer.\n"
                f"Searched:\n{searched_layers()}\n"
                "The generated file may predate a library move/rename — check "
                "`farrier config show library_dir`."
            )
        layer, abs_source = hit
        # With more than one layer, *which* copy you are about to edit is the whole
        # question — an overlay shadowing the base means the base copy is inert.
        # stdout stays the bare path so callers can `$(farrier source ...)` it.
        if len(LAYERS) > 1:
            print(f"note: resolved from layer {layer.name}", file=sys.stderr)
        print(abs_source)
    return 0


# ── farrier scaffold ──────────────────────────────────────────────────────────
# Scaffold definitions are YAML files under the library's `scaffolds/` directory.
# Each `scaffolds/*.yml` maps one or more scaffold ids to a definition:
#
#   go-service:
#     description: Seed a Go service folder.
#     params:
#       dir: api                # default value; `~` (null) = required, no default
#     tree:
#       $dir/.gitignore: |      # string value = inline file content
#         bin/
#       $dir/README.md: { url: 'https://raw.githubusercontent.com/...' }
#       $dir/docs:              # null (bare key) or {} = empty directory
#
# `$param` / `${param}` placeholders substitute in tree paths (strictly — an
# unknown param is an error) and in inline content (leniently, so literal `$`
# in file bodies survives). Downloaded content is written verbatim. Two built-in
# params are always available unless shadowed: `repo_name` (the target repo's
# directory name, kebab-cased) and `repo_title` (title-cased words).
#
# Scaffolded files are SEEDS: an existing file is never overwritten, so the
# command is safe to re-run and the repo owns every file after first write.

SCAFFOLD_TREE_FILE_KEYS = {"url"}


def load_scaffold_defs() -> dict[str, dict[str, Any]]:
    """All scaffold definitions across the layers, keyed by scaffold id.

    A duplicate id *within one layer* is a hard error — ids are the public lookup key
    (`farrier scaffold <id>`), like skill names. Across layers it is not an error but
    the point: an overlay redefining a base scaffold id shadows it, same as for skills.
    """
    defs: dict[str, dict[str, Any]] = {}
    origin: dict[str, Path] = {}
    for layer, scaffolds_dir in layer_dirs("scaffolds"):
        layer_origin: dict[str, Path] = {}
        for path in sorted(
            list(scaffolds_dir.glob("*.yml")) + list(scaffolds_dir.glob("*.yaml"))
        ):
            data = read_yaml(path)
            for scaffold_id, definition in data.items():
                sid = str(scaffold_id)
                if sid in layer_origin:
                    raise SystemExit(
                        f"Duplicate scaffold id {sid!r} in layer {layer.name}: "
                        f"defined in {layer_origin[sid]} and {path}"
                    )
                if not isinstance(definition, dict) or not isinstance(
                    definition.get("tree"), dict
                ):
                    raise SystemExit(
                        f"Scaffold {sid!r} in {path} must be a mapping with a "
                        "`tree:` mapping"
                    )
                layer_origin[sid] = path
                # layer_dirs is precedence-ordered: a lower layer never overwrites
                # an id a higher one already claimed.
                if sid not in defs:
                    defs[sid] = definition
                    origin[sid] = path
    return defs


def resolve_scaffold_params(
    scaffold_id: str, definition: dict[str, Any], overrides: dict[str, str], repo: Path
) -> dict[str, str]:
    """Merge declared param defaults with CLI overrides; reject unknown params,
    require a value for every default-less (null) param."""
    declared = definition.get("params") or {}
    if not isinstance(declared, dict):
        raise SystemExit(f"Scaffold {scaffold_id!r}: params must be a YAML mapping")

    unknown = sorted(set(overrides) - set(declared))
    if unknown:
        accepted = ", ".join(sorted(declared)) or "(none)"
        raise SystemExit(
            f"Scaffold {scaffold_id!r} does not accept param(s): "
            f"{', '.join(unknown)}. Accepted params: {accepted}"
        )

    params: dict[str, str] = {}
    missing: list[str] = []
    for name, default in declared.items():
        if name in overrides:
            params[name] = overrides[name]
        elif default is None:
            missing.append(name)
        else:
            params[name] = str(default)
    if missing:
        raise SystemExit(
            f"Scaffold {scaffold_id!r} requires --param for: {', '.join(missing)}"
        )

    repo_name = kebab(repo.name)
    params.setdefault("repo_name", repo_name)
    params.setdefault("repo_title", repo_name.replace("-", " ").title())
    return params


def flatten_scaffold_tree(
    scaffold_id: str, tree: dict[str, Any], base: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """Flatten a nested `tree:` mapping into ({rel path: file spec}, [empty dirs]).

    A file spec is either a string (inline content) or a `{url: ...}` mapping.
    Any other mapping value is a nested directory; an empty mapping or a null
    value (a bare `dir:` key) is an empty directory. Keys may themselves
    contain `/` separators.
    """
    files: dict[str, Any] = {}
    dirs: list[str] = []
    for key, value in tree.items():
        rel = f"{base}{key}".strip("/")
        if value is None:
            dirs.append(rel)
        elif isinstance(value, str):
            files[rel] = value
        elif isinstance(value, dict):
            if SCAFFOLD_TREE_FILE_KEYS & set(value):
                extra = set(value) - SCAFFOLD_TREE_FILE_KEYS
                if extra:
                    raise SystemExit(
                        f"Scaffold {scaffold_id!r}: file node {rel!r} has "
                        f"unsupported key(s): {', '.join(sorted(extra))}"
                    )
                files[rel] = value
            elif not value:
                dirs.append(rel)
            else:
                sub_files, sub_dirs = flatten_scaffold_tree(
                    scaffold_id, value, f"{rel}/"
                )
                files.update(sub_files)
                dirs.extend(sub_dirs)
        else:
            raise SystemExit(
                f"Scaffold {scaffold_id!r}: tree node {rel!r} must be file "
                f"content (string), a {{url: ...}} mapping, a sub-tree "
                f"mapping, or null/{{}} (empty directory) — got "
                f"{type(value).__name__}"
            )
    return files, dirs


def substitute_scaffold_path(scaffold_id: str, rel: str, params: dict[str, str]) -> str:
    """Substitute `$param` placeholders in a tree path. Strict: an unknown or
    malformed placeholder is an error (paths have no legitimate `$`)."""
    from string import Template

    try:
        resolved = Template(rel).substitute(params)
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: cannot resolve path {rel!r}: {exc}"
        ) from exc
    resolved = resolved.strip("/")
    parts = Path(resolved).parts
    if not resolved or Path(resolved).is_absolute() or ".." in parts:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: path {rel!r} resolves outside the repo: "
            f"{resolved!r}"
        )
    return resolved


def fetch_scaffold_url(scaffold_id: str, rel: str, url: str) -> str:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: failed to download {rel!r} from {url}: {exc}"
        ) from exc


def available_scaffold_ids(repo: Path, defs: dict[str, dict[str, Any]]) -> set[str]:
    """The scaffold ids this repo may use.

    With an `agents.yml`, the repo's `scaffolds:` list unioned with every
    selected pack's `scaffolds:` list is the catalog. Without one (bootstrapping
    a repo from scratch), every library definition is available.
    """
    config_path = repo / "agents.yml"
    if not config_path.is_file():
        return set(defs)
    config = read_yaml(config_path)
    _, _, _, scaffold_ids, _ = collect_selection(config)
    return scaffold_ids


def parse_param_overrides(entries: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for entry in entries or []:
        key, sep, value = entry.partition("=")
        if not sep or not key.strip():
            raise SystemExit(f"--param must be key=value (got {entry!r})")
        overrides[key.strip()] = value
    return overrides


def _list_scaffolds(
    defs: dict[str, dict[str, Any]], available: set[str], repo: Path
) -> int:
    ids = sorted(set(defs) & available)
    if not ids:
        print(
            "No scaffolds available. Library defines: "
            + (", ".join(sorted(defs)) or "(none)")
            + f". Add ids to the `scaffolds:` list in {repo / 'agents.yml'}."
        )
        return 0
    for sid in ids:
        definition = defs[sid]
        description = str(definition.get("description") or "").strip()
        print(f"{sid}" + (f" — {description}" if description else ""))
        for name, default in (definition.get("params") or {}).items():
            suffix = "(required)" if default is None else f"(default: {default})"
            print(f"    --param {name}=...  {suffix}")
    return 0


def _run_scaffold(args: argparse.Namespace) -> int:
    set_layers(resolve_library_dir(args.library))
    repo = args.repo.resolve()
    defs = load_scaffold_defs()
    available = available_scaffold_ids(repo, defs)

    if args.list or not args.id:
        return _list_scaffolds(defs, available, repo)

    scaffold_id = args.id
    if scaffold_id not in defs:
        raise SystemExit(
            f"Unknown scaffold: {scaffold_id!r}. Library defines: "
            + (", ".join(sorted(defs)) or "(none)")
        )
    if scaffold_id not in available:
        raise SystemExit(
            f"Scaffold {scaffold_id!r} is not enabled for this repo — add it to "
            f"the `scaffolds:` list in {repo / 'agents.yml'} (or select a pack "
            "that provides it)."
        )

    definition = defs[scaffold_id]
    params = resolve_scaffold_params(
        scaffold_id, definition, parse_param_overrides(args.param), repo
    )
    files, dirs = flatten_scaffold_tree(scaffold_id, definition["tree"])

    from string import Template

    created = 0
    for rel in sorted(dirs):
        resolved = substitute_scaffold_path(scaffold_id, rel, params)
        target = repo / resolved
        if target.is_dir():
            print(f"exists (kept): {resolved}/")
            continue
        target.mkdir(parents=True, exist_ok=True)
        print(f"created: {resolved}/")
    for rel, spec in sorted(files.items()):
        resolved = substitute_scaffold_path(scaffold_id, rel, params)
        target = repo / resolved
        # Seed semantics: never clobber a file the repo already owns.
        if target.exists():
            print(f"exists (kept): {resolved}")
            continue
        if isinstance(spec, dict):
            content = fetch_scaffold_url(scaffold_id, resolved, str(spec["url"]))
        else:
            content = Template(spec).safe_substitute(params)
        write_text(target, content)
        print(f"created: {resolved}")
        created += 1
    print(f"Scaffolded {scaffold_id!r}: {created} file(s) created in {repo}")
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

    # source
    source_p = sub.add_parser(
        "source",
        help="Print the editable library source path of a generated skill/command",
    )
    source_p.add_argument(
        "file", type=Path, help="Path to a generated SKILL.md / command .md"
    )
    source_p.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )

    # scaffold
    scaffold_p = sub.add_parser(
        "scaffold",
        help="Seed repository files from a library scaffold definition",
    )
    scaffold_p.add_argument(
        "id",
        nargs="?",
        default=None,
        help="Scaffold id (omit to list the available scaffolds)",
    )
    scaffold_p.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a scaffold parameter (repeatable)",
    )
    scaffold_p.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scaffold into (default: cwd)",
    )
    scaffold_p.add_argument(
        "--list",
        action="store_true",
        help="List the scaffolds available to this repo and their params",
    )
    scaffold_p.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
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
    _SUBCOMMANDS = {"install", "config", "version", "source", "scaffold"}
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

    if args.command == "source":
        return _run_source(args)

    if args.command == "scaffold":
        return _run_scaffold(args)

    return _run_install(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
