from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Any

from jinja2 import (
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    make_logging_undefined,
)

# Template references are routinely filled from upstream agent (LLM) output, so a
# missing variable or an attribute read on a wrong-typed value (e.g. `{{ qa_result.notes }}`
# when `qa_result` came back as a bare string) is a runtime fact of life — not an
# author bug worth killing the whole run over. We therefore render such references
# as empty (and chainable, so `a.b.c` doesn't explode mid-path) instead of raising,
# but log every occurrence so the malformed/missing reference stays visible in the
# run output. (This replaces StrictUndefined, which raised and aborted the run.)
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


def _farrier_globals(context: dict[str, Any], workflow_dir: Path) -> dict[str, Any]:
    """Return Jinja2 globals for the farrier template helpers, resolved at run time.

    Workflows (and their prompts) now run **directly from the agent library** —
    farrier no longer renders/copies them into a repo. Instead it emits a per-repo
    **context manifest** (``.agents/agents-context.json``) that the runner loads and
    merges into the workflow context under reserved keys:

      - ``_instructions``: ``{name: repo-root-relative skill path}``
      - ``_prompts``:      ``{name: repo-root-relative prompt path}``
      - ``_used_skills``:  the set of skills selected for this repo
      - ``_skill_dir``:    repo-root-relative skills directory

    These helpers reproduce what farrier used to resolve at install time, but from
    the manifest in ``context``. Paths are repo-root-relative because the agent runs
    with its working directory at the repo root (``AGENT_REPO_DIR``); the library
    prompt's physical location is irrelevant.
    """
    instructions: dict[str, str] = context.get("_instructions") or {}
    prompts: dict[str, str] = context.get("_prompts") or {}
    used_skills = set(context.get("_used_skills") or [])
    skill_dir_value = context.get("_skill_dir")

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

    def instruction_ref(name: str = "") -> str:
        return instructions.get(name, f"generated {name} instruction file when installed")

    def prompt_ref(name: str = "") -> str:
        return prompts.get(name, f"generated {name} prompt when installed")

    def is_using_instruction(name: str = "", *_args: Any, **_kwargs: Any) -> bool:
        return name in used_skills

    return {
        "workhorse_var": workhorse_var,
        "get_node_output": get_node_output,
        "skill_dir": skill_dir,
        "instruction_ref": instruction_ref,
        "instruction_file": instruction_ref,
        "skill_file": instruction_ref,
        "prompt_file": prompt_ref,
        "prompt_ref": prompt_ref,
        "isUsingInstruction": is_using_instruction,
    }


def _flavor_override(
    template_path: Path, context: dict[str, Any], workflow_dir: Path
) -> tuple[str, str] | None:
    """Locate a repo-authored flavor override for this node's prompt, if any.

    A consuming repo extends a base prompt by dropping a same-named file at
    ``<repo_root>/.agents/flavors/<workflow>/<node>.md`` — no config or selection,
    presence alone activates it. The override ``{% extends "prompts/<node>.md" %}``
    and fills the base's named blocks; plain (no such file) leaves the base
    untouched (the blocks extend to nothing). Returns ``(flavor_dir, node_name)``
    when an override exists, else ``None``.

    When the agent node declares a ``cwd`` (e.g. to run in a specific repo), the
    flavor is looked up relative to that per-node CWD rather than the global
    ``_repo_root`` — so each repo in a multi-repo workflow can provide its own
    flavor independently of the orchestrating repo.
    """
    node_cwd = context.get("_node_cwd")
    repo_root = node_cwd if node_cwd else context.get("_repo_root")
    if not repo_root:
        return None
    node_name = template_path.name
    flavor_dir = Path(repo_root) / ".agents" / "flavors" / workflow_dir.name
    if (flavor_dir / node_name).is_file():
        return str(flavor_dir), node_name
    return None


def render(template_path: str | Path, context: dict[str, Any], workflow_dir: str | Path) -> str:
    """Render a Jinja2 template file relative to workflow_dir with the given context.

    A repo may override a node prompt via a flavor file (see :func:`_flavor_override`);
    when present it is rendered instead, with the base prompt on the loader path so its
    ``{% extends %}`` resolves. Otherwise the base prompt renders exactly as authored.
    """
    workflow_dir = Path(workflow_dir)
    template_path = Path(template_path)

    # Support both absolute paths and paths relative to the workflow directory
    if template_path.is_absolute():
        search_paths = [str(template_path.parent)]
        template_name = template_path.name
    else:
        template_name = str(template_path)
        search_paths = [str(workflow_dir)]
        override = _flavor_override(template_path, context, workflow_dir)
        if override is not None:
            flavor_dir, node_name = override
            # Flavor dir first so the override entry resolves there; workflow_dir
            # second so the override's `{% extends "prompts/<node>.md" %}` finds the base.
            search_paths = [flavor_dir, str(workflow_dir)]
            template_name = node_name

    env = Environment(
        loader=FileSystemLoader(search_paths),
        undefined=ResilientUndefined,
        keep_trailing_newline=True,
    )
    env.globals.update(_farrier_globals(context, workflow_dir))
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def render_string(template_str: str, context: dict[str, Any]) -> str:
    """Render an inline Jinja2 template string (used for node args/cwd/commands).

    Exposes the same farrier helpers as :func:`render` so node args in a
    library-resident ``workflow.yaml`` can use ``instruction_ref``/``template.*``
    the same way prompts do.
    """
    env = Environment(undefined=ResilientUndefined)
    workflow_dir = Path(context.get("_skill_dir") or ".")
    env.globals.update(_farrier_globals(context, workflow_dir))
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
