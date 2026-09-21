from __future__ import annotations
import json
import logging
import os
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import (
    ChainableUndefined,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    make_logging_undefined,
)

from workhorse._vendor.stablemate_core.config import resolve_default_cli
from workhorse.manifest import ManifestContext
from workhorse.references import resolve_instruction

_undefined_logger = logging.getLogger("workhorse.templates")
if not _undefined_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[template] ⚠ %(message)s"))
    _undefined_logger.addHandler(_handler)
    _undefined_logger.setLevel(logging.WARNING)
    _undefined_logger.propagate = False

ResilientUndefined = make_logging_undefined(
    logger=_undefined_logger, base=ChainableUndefined
)


def _flatten(names: Iterable[Any]) -> Iterator[str]:
    """Yield reference names from either calling convention, skipping empties."""
    for name in names:
        if isinstance(name, str):
            if name:
                yield name
        elif isinstance(name, Iterable):
            yield from _flatten(name)


def _farrier_globals(
    context: dict[str, Any], workflow_dir: Path, *, quiet: bool = False
) -> dict[str, Any]:
    """Return Jinja2 globals for the farrier template helpers, resolved at run time."""
    manifest = ManifestContext.from_context(context)
    instructions = manifest.instructions
    instruction_tags = manifest.instruction_tags
    prompts = manifest.prompts
    used_skills = set(manifest.used_skills)
    skill_dir_value = manifest.skill_dir

    run_dir_value = context.get("_run_dir", "")

    def workhorse_var(name: str) -> Any:  # noqa: ANN202
        return context.get(name, "")

    def get_node_output(node_id: str, key: str, default: Any = "") -> Any:  # noqa: ANN202
        """Read a key from a previously-run node's output.json on disk."""
        if not run_dir_value:
            return default
        output_file = Path(run_dir_value) / node_id / "output.json"
        if not output_file.exists():
            return default
        try:
            data = json.loads(output_file.read_text(encoding="utf-8"))
            return data.get(key, default)
        except (json.JSONDecodeError, OSError):
            return default

    def skill_dir() -> str:
        return skill_dir_value if skill_dir_value else str(workflow_dir)

    manifest_present = manifest.present

    def unresolved(kind: str, name: str) -> None:
        """Report a reference that rendered as prose instead of a path."""
        if manifest_present and not quiet:
            _undefined_logger.warning(
                "%s '%s' did not resolve against the context manifest — the prompt "
                "will carry the placeholder text instead of a path",
                kind,
                name,
            )

    def instruction_ref(name: str = "") -> str:
        resolved = resolve_instruction(instructions, name)
        if resolved is not None:
            return resolved
        unresolved("skill", name)
        return f"generated {name} instruction file when installed"

    def prompt_ref(name: str = "") -> str:
        if name in prompts:
            return prompts[name]
        unresolved("prompt", name)
        return f"generated {name} prompt when installed"

    def _as_list(paths: Iterable[str]) -> str:
        """The one rendering of a resolved set: backticked paths, comma-joined."""
        return ", ".join(f"`{path}`" for path in paths)

    def _rendered(names: Iterable[Any], lookup: Any) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for name in _flatten(names):
            path = lookup(name)
            if path is not None and path not in seen:
                seen.add(path)
                out.append(path)
        return _as_list(out)

    def instruction_refs(*names: Any) -> str:
        return _rendered(names, lambda n: resolve_instruction(instructions, n))

    def prompt_refs(*names: Any) -> str:
        return _rendered(names, prompts.get)

    def find_by_tags(*tags: Any) -> str:
        """The installed skills tagged with **all** of *tags*, as a reference list."""
        wanted = {tag.lower() for tag in _flatten(tags)}
        if not wanted:
            return ""
        matched: set[str] = set()
        for name, owned in instruction_tags.items():
            if not wanted <= set(owned):
                continue
            path = resolve_instruction(instructions, name)
            if path is not None:
                matched.add(path)
        return _as_list(sorted(matched))

    def is_using_instruction(name: str = "", *_args: Any, **_kwargs: Any) -> bool:
        return name in used_skills

    def agent_cli() -> str:
        return (os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()

    def skill_load_ref(skill_name: str, skill_path: str = "") -> str:
        """Return the harness-native instruction for loading a skill."""
        resolved = resolve_instruction(instructions, skill_name)
        if resolved is None:
            unresolved("skill", skill_name)
        path = resolved or skill_path or f"{skill_dir()}/{skill_name}/SKILL.md"
        if agent_cli() == "claude":
            return f"/{PurePosixPath(path).parent.name or skill_name}"
        return f"Read `{path}` and follow its instructions"

    def skill_path_ref(skill_name: str, relative: str) -> str:
        """Return the path of a file that ships inside an installed skill."""
        resolved = resolve_instruction(instructions, skill_name)
        if resolved is None:
            unresolved("skill", skill_name)
        parent = PurePosixPath(resolved).parent if resolved else None
        base = str(parent) if parent and str(parent) != "." else f"{skill_dir()}/{skill_name}"
        return f"{base}/{relative}"

    return {
        "workhorse_var": workhorse_var,
        "agent_cli": agent_cli,
        "skill_load_ref": skill_load_ref,
        "skill_path_ref": skill_path_ref,
        "get_node_output": get_node_output,
        "skill_dir": skill_dir,
        "instruction_ref": instruction_ref,
        "instruction_file": instruction_ref,
        "skill_file": instruction_ref,
        "prompt_file": prompt_ref,
        "prompt_ref": prompt_ref,
        "instruction_refs": instruction_refs,
        "instruction_files": instruction_refs,
        "skill_files": instruction_refs,
        "prompt_refs": prompt_refs,
        "prompt_files": prompt_refs,
        "find_by_tags": find_by_tags,
        "isUsingInstruction": is_using_instruction,
    }


def _flavor_override(
    template_path: Path, context: dict[str, Any], workflow_dir: Path
) -> tuple[str, str] | None:
    """Locate a repo-authored flavor override for this node's prompt, if any."""
    node_cwd = context.get("_node_cwd")
    repo_root = node_cwd if node_cwd else ManifestContext.from_context(context).repo_root
    if not repo_root:
        return None
    node_name = template_path.name
    root = Path(repo_root) / ".agents" / "flavors" / workflow_dir.name
    owner = template_path.parent.parent
    for flavor_dir in (root / owner, root):
        if (flavor_dir / node_name).is_file():
            return str(flavor_dir), node_name
    return None


BODY_PREFIX = "body"


def render(template_path: str | Path, context: dict[str, Any], workflow_dir: str | Path) -> str:
    """Render a Jinja2 template file relative to workflow_dir with the given context."""
    workflow_dir = Path(workflow_dir)
    template_path = Path(template_path)
    body_dir = str(context.get("_body_dir") or "")

    if template_path.is_absolute():
        search_paths = [str(template_path.parent)]
        template_name = template_path.name
    else:
        template_name = str(template_path)
        search_paths = [str(workflow_dir)]
        override = _flavor_override(template_path, context, workflow_dir)
        if override is not None:
            flavor_dir, node_name = override
            search_paths = [flavor_dir, str(workflow_dir)]
            template_name = node_name

    loader = FileSystemLoader(search_paths)
    body_loader = (
        ChoiceLoader([PrefixLoader({BODY_PREFIX: FileSystemLoader(body_dir)}), loader])
        if body_dir
        else loader
    )

    env = Environment(
        loader=body_loader,
        undefined=ResilientUndefined,
        keep_trailing_newline=True,
    )
    env.globals.update(_farrier_globals(context, workflow_dir))
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def render_string(
    template_str: str, context: dict[str, Any], *, quiet: bool = False
) -> str:
    """Render an inline Jinja2 template string (an agent turn's cwd/args/add_dirs)."""
    env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)
    workflow_dir = Path(ManifestContext.from_context(context).skill_dir or ".")
    env.globals.update(_farrier_globals(context, workflow_dir, quiet=quiet))
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
