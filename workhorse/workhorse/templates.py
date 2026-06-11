from __future__ import annotations
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
    """Return Jinja2 globals for farrier install-time template helpers.

    Farrier (the agents-library build tool) processes source prompts and
    replaces calls like ``{{ workhorse_var('story_path') }}`` with plain
    ``{{ story_path }}`` before the workflow is installed.  When workhorse
    renders source prompts directly (e.g. during workflow development or
    testing), these helpers would otherwise be undefined.  The stubs here
    produce the same final output: ``workhorse_var('key')`` returns the
    context value for ``key`` directly, which is equivalent to the two-step
    install → runtime render.
    """
    def workhorse_var(name: str) -> Any:  # noqa: ANN202
        return context.get(name, "")

    def skill_dir() -> str:
        return str(workflow_dir)

    def _noop_ref(_name: str = "") -> str:
        return ""

    def is_using_instruction(*_args: Any, **_kwargs: Any) -> str:
        return ""

    # template.*/repo.*/vars.* attribute accesses resolve to "" with | default() support
    class _AttrNS:
        def __getattr__(self, name: str) -> str:
            return ""

    _ns = _AttrNS()

    return {
        "workhorse_var": workhorse_var,
        "skill_dir": skill_dir,
        "instruction_ref": _noop_ref,
        "instruction_file": _noop_ref,
        "skill_file": _noop_ref,
        "prompt_file": _noop_ref,
        "prompt_ref": _noop_ref,
        "isUsingInstruction": is_using_instruction,
        "template": _ns,
        "repo": _ns,
        "vars": _ns,
    }


def render(template_path: str | Path, context: dict[str, Any], workflow_dir: str | Path) -> str:
    """Render a Jinja2 template file relative to workflow_dir with the given context."""
    workflow_dir = Path(workflow_dir)
    template_path = Path(template_path)

    # Support both absolute paths and paths relative to the workflow directory
    if template_path.is_absolute():
        search_path = template_path.parent
        template_name = template_path.name
    else:
        search_path = workflow_dir
        template_name = str(template_path)

    env = Environment(
        loader=FileSystemLoader(str(search_path)),
        undefined=ResilientUndefined,
        keep_trailing_newline=True,
    )
    env.globals.update(_farrier_globals(context, workflow_dir))
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


def render_string(template_str: str, context: dict[str, Any]) -> str:
    """Render an inline Jinja2 template string (used for node args)."""
    env = Environment(undefined=ResilientUndefined)
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
