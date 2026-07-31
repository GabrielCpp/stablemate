from __future__ import annotations
import json
import logging
import os
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from jinja2 import (
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    make_logging_undefined,
)

from workhorse.manifest import ManifestContext
from workhorse.references import resolve_instruction

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


def _flatten(names: Iterable[Any]) -> Iterator[str]:
    """Yield reference names from either calling convention, skipping empties.

    `instruction_refs("go", "pulumi")` reads best inline; `instruction_refs(stack_skills)`
    is what a `{% set %}`-built list or a node's own output needs. Supporting both costs
    one isinstance and spares every prompt a `*`-unpacking dance. Strings are deliberately
    NOT treated as iterables of characters.
    """
    for name in names:
        if isinstance(name, str):
            if name:
                yield name
        elif isinstance(name, Iterable):
            yield from _flatten(name)


def _farrier_globals(
    context: dict[str, Any], workflow_dir: Path, *, quiet: bool = False
) -> dict[str, Any]:
    """Return Jinja2 globals for the farrier template helpers, resolved at run time.

    Workflows (and their prompts) now run **directly from the agent library** —
    farrier no longer renders/copies them into a repo. Instead it emits a per-repo
    **context manifest** (``.agents/agents-context.json``) that the runner loads and
    merges into the workflow context; :class:`workhorse.manifest.ManifestContext`
    reads it back out — the instruction/prompt path maps, the selected skills and the
    skills directory.

    These helpers reproduce what farrier used to resolve at install time, but from
    the manifest in ``context``. Paths are repo-root-relative because the agent runs
    with its working directory at the repo root (``AGENT_REPO_DIR``); the library
    prompt's physical location is irrelevant.
    """
    manifest = ManifestContext.from_context(context)
    instructions = manifest.instructions
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

    # A run with no context manifest at all (hello-world, most tests) resolves nothing
    # by design, so "unresolved" is its normal state and not worth a word. A manifest
    # that IS present and still misses a name is the failure this warns about.
    manifest_present = manifest.present

    def unresolved(kind: str, name: str) -> None:
        """Report a reference that rendered as prose instead of a path.

        The placeholder is kept — a half-rendered prompt is worse than one carrying a
        sentence the agent can at least read — but it is no longer silent. The same
        names are reported *before* the run by workhorse.references; this catches the
        ones a static scan cannot see (a helper called with a computed argument).
        """
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

    # `*_ref` asks for ONE reference the prompt cannot do without, so not resolving it
    # is a defect and says so. `*_refs` asks a different question — "of these, which
    # does this repo actually have?" — and the honest answer for a name the repo never
    # installed is to say nothing about it. A prompt that enumerates the skills for
    # every stack the workflow has ever met (go, react-router, flutter, pulumi) is
    # naming a menu, not a dependency; rendering the absent half as
    # "generated flutter instruction file when installed" tells a Go repo's agent to go
    # find a Flutter skill. So the unresolved names are DROPPED, not placeheld, and the
    # result is empty — hence falsy — when none of them resolve, which is what lets the
    # surrounding sentence disappear with `{% if %}` instead of dangling after "e.g.".
    def _rendered(names: Iterable[Any], lookup: Any) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for name in _flatten(names):
            path = lookup(name)
            # Deduped on the resolved PATH: farrier indexes one skill under several
            # aliases, and a prompt listing two of them means one file, said twice.
            if path is not None and path not in seen:
                seen.add(path)
                out.append(f"`{path}`")
        return ", ".join(out)

    def instruction_refs(*names: Any) -> str:
        return _rendered(names, lambda n: resolve_instruction(instructions, n))

    def prompt_refs(*names: Any) -> str:
        return _rendered(names, prompts.get)

    def is_using_instruction(name: str = "", *_args: Any, **_kwargs: Any) -> bool:
        return name in used_skills

    def agent_cli() -> str:
        return os.environ.get("AGENT_CLI", "claude").strip().lower()

    def skill_load_ref(skill_name: str, skill_path: str = "") -> str:
        """Return the harness-native syntax for loading a skill.

        For Claude Code, emits a slash-command invocation (``/skill-name``).
        For every other harness, emits a Read-the-file instruction using the
        resolved path — first checking the manifest ``instructions`` dict
        (which holds the correct prefixed path from farrier), then falling back
        to ``skill_path`` or ``{skill_dir}/{skill_name}/SKILL.md``.
        """
        cli = agent_cli()
        if cli == "claude":
            return f"/{skill_name}"
        path = instructions.get(skill_name) or skill_path or f"{skill_dir()}/{skill_name}/SKILL.md"
        return f"Read `{path}` and follow its instructions"

    return {
        "workhorse_var": workhorse_var,
        "agent_cli": agent_cli,
        "skill_load_ref": skill_load_ref,
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
    flavor is looked up relative to that per-node CWD rather than the manifest's
    repo root — so each repo in a multi-repo workflow can provide its own flavor
    independently of the orchestrating repo.
    """
    node_cwd = context.get("_node_cwd")
    repo_root = node_cwd if node_cwd else ManifestContext.from_context(context).repo_root
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


def render_string(
    template_str: str, context: dict[str, Any], *, quiet: bool = False
) -> str:
    """Render an inline Jinja2 template string (used for node args/cwd/commands).

    Exposes the same farrier helpers as :func:`render` so node args in a
    library-resident ``workflow.yaml`` can use ``instruction_ref``/``template.*``
    the same way prompts do.

    ``quiet`` suppresses the missing-variable warning (the render still yields
    empty). It is for the callers where an unresolved reference is an *expected*
    state rather than a symptom — telemetry labels, which are deliberately dropped
    until the value they track exists, and which re-render before every node, so
    warning would mean thousands of lines about a designed behavior. Everywhere a
    missing variable really does indicate a broken prompt or arg, leave it off.
    """
    env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)
    workflow_dir = Path(ManifestContext.from_context(context).skill_dir or ".")
    env.globals.update(_farrier_globals(context, workflow_dir, quiet=quiet))
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
