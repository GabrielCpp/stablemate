from __future__ import annotations
import json
import logging
import os
import sys
from collections.abc import Callable, Iterable
from functools import cache
from pathlib import Path
from typing import Any

from jinja2 import (
    BaseLoader,
    ChainableUndefined,
    ChoiceLoader,
    DictLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    make_logging_undefined,
)

from workhorse._vendor.stablemate_core.config import resolve_default_cli
from workhorse._vendor.stablemate_core.skill_refs import (
    RETIRED_HELPERS,
    RetiredHelper,
    SkillCatalog,
    SkillRefs,
    repo_root,
    scan_catalog,
)
from workhorse.manifest import ManifestContext

NODE_ADD_DIRS = "_node_add_dirs"

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


def _node_add_dirs(context: dict[str, Any], cwd: Path) -> list[Path]:
    value = context.get(NODE_ADD_DIRS)
    if not isinstance(value, (list, tuple)):
        return []
    return [(cwd / str(directory)).resolve() for directory in value if directory]


def agent_cli() -> str:
    return (os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()


def turn_catalog(cwd: Path, add_dirs: Iterable[Path] = ()) -> SkillCatalog:
    """The skills the default harness loads for a turn started in `cwd` with `add_dirs`."""
    return scan_catalog(
        agent_cli(), cwd, home=Path.home(), added_dirs=add_dirs, root=repo_root(cwd)
    )


def skill_refs(context: dict[str, Any], *, quiet: bool = False) -> SkillRefs:
    """The skill reference helpers for one turn, bound to what its harness loads from where it starts."""
    start = context.get("_node_cwd") or ManifestContext.from_context(context).repo_root
    cwd = Path(start or os.getcwd()).resolve()
    catalog = turn_catalog(cwd, _node_add_dirs(context, cwd))

    def placeholder(name: str) -> str:
        return f"generated {name} skill when installed"

    return SkillRefs(
        catalog, agent_cli(), cwd, repo_root(cwd), Path.home(), placeholder if quiet else None
    )


def _retired(name: str) -> Callable[..., str]:
    def call(*_args: Any, **_kwargs: Any) -> str:
        raise RetiredHelper(name)

    return call


def template_globals(context: dict[str, Any], *, quiet: bool = False) -> dict[str, Any]:
    """The globals every prompt renders with: the run's values and the skill reference helpers."""
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

    @cache
    def refs() -> SkillRefs:
        return skill_refs(context, quiet=quiet)

    def skill_link(name: str) -> str:
        return refs().skill_link(name)

    def skill_path(name: str, relative: str = "") -> str:
        return refs().skill_path(name, relative)

    def skill_command(name: str) -> str:
        return refs().skill_command(name)

    def find_by_tags(*tags: str) -> str:
        return refs().find_by_tags(*tags)

    def has_skill(name: str) -> bool:
        return refs().has_skill(name)

    return {
        **{name: _retired(name) for name in RETIRED_HELPERS},
        "workhorse_var": workhorse_var,
        "agent_cli": agent_cli,
        "get_node_output": get_node_output,
        "skill_link": skill_link,
        "skill_path": skill_path,
        "skill_command": skill_command,
        "find_by_tags": find_by_tags,
        "has_skill": has_skill,
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
    candidates = dict.fromkeys((root / owner, root))
    for flavor_dir in candidates:
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

    env = _environment(
        _stack(body_dir, FileSystemLoader(search_paths)), context, workflow_dir
    )
    return env.get_template(template_name).render(**context)


def _stack(body_dir: str, *loaders: BaseLoader) -> BaseLoader:
    """The loaders a prompt resolves through, `body:` first when a body directory is mounted."""
    parts: list[BaseLoader] = list(loaders)
    if body_dir:
        parts.insert(0, PrefixLoader({BODY_PREFIX: FileSystemLoader(body_dir)}))
    return parts[0] if len(parts) == 1 else ChoiceLoader(parts)


def _environment(
    loader: BaseLoader, context: dict[str, Any], workflow_dir: Path
) -> Environment:
    """The one environment every prompt renders in, whatever the text came from."""
    env = Environment(
        loader=loader, undefined=ResilientUndefined, keep_trailing_newline=True
    )
    env.globals.update(template_globals(context))
    return env


def render_text(
    label: str, text: str, context: dict[str, Any], workflow_dir: str | Path
) -> str:
    """Render a prompt written in the state's own source, in the same environment a prompt file gets."""
    workflow_dir = Path(workflow_dir)
    name = f"{label}.md"
    inline = DictLoader({name: text})
    files = FileSystemLoader([str(workflow_dir)])
    override = _flavor_override(Path(name), context, workflow_dir)
    loaders = (
        [FileSystemLoader([override[0]]), inline, files]
        if override is not None
        else [inline, files]
    )
    body_dir = str(context.get("_body_dir") or "")
    env = _environment(_stack(body_dir, *loaders), context, workflow_dir)
    return env.get_template(name).render(**context)


def render_string(
    template_str: str, context: dict[str, Any], *, quiet: bool = False
) -> str:
    """Render an inline Jinja2 template string (an agent turn's cwd/args/add_dirs)."""
    env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)
    env.globals.update(template_globals(context, quiet=quiet))
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
