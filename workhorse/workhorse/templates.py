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
    def _as_list(paths: Iterable[str]) -> str:
        """The one rendering of a resolved set: backticked paths, comma-joined."""
        return ", ".join(f"`{path}`" for path in paths)

    def _rendered(names: Iterable[Any], lookup: Any) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for name in _flatten(names):
            path = lookup(name)
            # Deduped on the resolved PATH: farrier indexes one skill under several
            # aliases, and a prompt listing two of them means one file, said twice.
            if path is not None and path not in seen:
                seen.add(path)
                out.append(path)
        return _as_list(out)

    def instruction_refs(*names: Any) -> str:
        return _rendered(names, lambda n: resolve_instruction(instructions, n))

    def prompt_refs(*names: Any) -> str:
        return _rendered(names, prompts.get)

    def find_by_tags(*tags: Any) -> str:
        """The installed skills tagged with **all** of *tags*, as a reference list.

        What `instruction_refs` asks by name, this asks by capability: a prompt says
        `find_by_tags('web', 'tests')` — "however this repo writes web tests" — instead
        of listing `react-router-qa`, `flutter-testing`, `go-testing` and hoping the
        repo's stack is one the workflow has met before. The tags come from each
        skill's own front matter, so a repo teaches the workflow about its stack by
        tagging a skill rather than by getting the workflow's menu extended.

        AND, not OR: a second tag narrows. An empty query renders nothing rather than
        the whole library — `find_by_tags()` asks for no capability in particular, and
        answering it with every installed skill would be the opposite of a query.
        Unmatched is likewise empty (hence falsy), so the sentence around it can
        disappear with `{% if %}` exactly as it does for the plural `*_refs` helpers.
        """
        wanted = {tag.lower() for tag in _flatten(tags)}
        if not wanted:
            return ""
        matched: set[str] = set()
        for name, owned in instruction_tags.items():
            if not wanted <= set(owned):
                continue
            # Through the same resolver as `instruction_ref`, so a matched name that
            # is a pack alias lands on the same installed path either route reaches.
            path = resolve_instruction(instructions, name)
            if path is not None:
                matched.add(path)
        # Sorted rather than in manifest order: a JSON dict's order is farrier's
        # bookkeeping, and a prompt that renders differently run-to-run for no
        # semantic reason costs a diff every time the manifest is regenerated.
        return _as_list(sorted(matched))

    def is_using_instruction(name: str = "", *_args: Any, **_kwargs: Any) -> bool:
        return name in used_skills

    def agent_cli() -> str:
        return (os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()

    def skill_load_ref(skill_name: str, skill_path: str = "") -> str:
        """Return the harness-native instruction for loading a skill.

        This is the imperative sibling of ``instruction_ref``: the call sites say
        "load this and follow it" rather than citing a path, so an unresolved name is
        a defect and is reported as one — same ``unresolved`` channel, same reason.

        **Both harness spellings come from the one resolved path.** Farrier installs a
        skill under the consuming repo's prefix, so ``ostler-okf`` lands as
        ``<repo>-ostler-okf`` — directory and registered command alike. The
        Claude branch used to emit the caller's bare argument, which therefore named a
        slash command no repo has: the single failure this helper exists to prevent,
        produced on every Claude run. Deriving the command from the installed
        directory's name keeps the two branches saying the same thing about the same
        file.

        Resolution is ``resolve_instruction``, not an exact ``instructions`` lookup,
        so a pack that namespaces the skill resolves here exactly as it does for every
        other helper. The fallbacks — the caller's ``skill_path``, then
        ``{skill_dir}/{skill_name}/SKILL.md`` — are unchanged and still describe an
        uninstalled skill, which is the honest thing to say when nothing resolved.
        """
        resolved = resolve_instruction(instructions, skill_name)
        if resolved is None:
            unresolved("skill", skill_name)
        path = resolved or skill_path or f"{skill_dir()}/{skill_name}/SKILL.md"
        if agent_cli() == "claude":
            # `.claude/skills/<installed-name>/SKILL.md` → `/<installed-name>`. A path
            # that is not skill-shaped (no parent directory) leaves nothing to derive
            # from, so the caller's name stands.
            return f"/{PurePosixPath(path).parent.name or skill_name}"
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
        "find_by_tags": find_by_tags,
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

    Two locations, the **path-keyed** one first::

        .agents/flavors/<workflow>/<dir>/<node>.md   # mirrors the prompt's own path
        .agents/flavors/<workflow>/<node>.md         # by basename alone

    A workflow whose flows each own their prompts has several files called
    ``implement-plan.md``, one per flow, and the basename cannot tell them apart: a
    single flavor would activate on all of them while its ``{% extends %}`` names one
    base, so a repo flavouring dev's turn would silently render dev's envelope inside
    fix's node. Mirroring the prompt's directory (``dev/implement-plan.md``) says which
    one is meant. The basename location stays, and stays working, because it is what
    every repo that already ships a flavor wrote — it is simply the broader match.

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
    root = Path(repo_root) / ".agents" / "flavors" / workflow_dir.name
    # `dev/prompts/implement-plan.md` -> `dev/`, the flow that owns the prompt. A prompt
    # at the workflow root keeps `parent.parent` empty, so both candidates coincide.
    owner = template_path.parent.parent
    for flavor_dir in (root / owner, root):
        if (flavor_dir / node_name).is_file():
            return str(flavor_dir), node_name
    return None


#: The namespace a resolved prompt body is mounted under, so `body/<name>` is the only
#: way to address it and a body named for its role cannot resolve to the envelope.
BODY_PREFIX = "body"


def render(template_path: str | Path, context: dict[str, Any], workflow_dir: str | Path) -> str:
    """Render a Jinja2 template file relative to workflow_dir with the given context.

    A repo may override a node prompt via a flavor file (see :func:`_flavor_override`);
    when present it is rendered instead, with the base prompt on the loader path so its
    ``{% extends %}`` resolves. Otherwise the base prompt renders exactly as authored.

    ``_body_dir`` in the context mounts one further directory under the ``body/``
    namespace. That is how a workflow-owned **envelope** — provided inputs, the
    exit-condition stage, the result schema — pulls in a **body** the workflow does not
    own and did not ship: the state resolves which body applies (the repo's override,
    the library layer it came from), passes the directory here and ``body/<name>`` as an
    ordinary variable, and the envelope says ``{% include body_template %}``. A body can
    never shadow a template the workflow ships, because no shipped template is addressed
    through that prefix.
    """
    workflow_dir = Path(workflow_dir)
    template_path = Path(template_path)
    body_dir = str(context.get("_body_dir") or "")

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

    # The body is reachable only as `body/<name>`, never as a bare filename. A body is
    # normally named for the role, which is what the envelope is named — so a plain
    # `{% include "dev-fix.md" %}` resolves back to the envelope that asked for it and
    # Jinja recurses until the interpreter stops it. Its own namespace also keeps the
    # guarantee the ordering was there for: nothing a repo supplies can shadow a template
    # the workflow ships, because the two are not addressed the same way.
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
    """Render an inline Jinja2 template string (an agent turn's cwd/args/add_dirs).

    Exposes the same farrier helpers as :func:`render` so those values can use
    ``instruction_ref``/``template.*`` the same way a prompt file does.

    ``quiet`` suppresses the missing-variable warning (the render still yields
    empty). It is for a caller where an unresolved reference is an *expected*
    state rather than a symptom, re-rendered often enough that warning would mean
    thousands of lines about a designed behavior. Nothing passes it today: the one
    such caller was the retired YAML front-end's ``labels:`` block, whose Jinja
    strings were re-rendered before every transition; a Python workflow overrides
    ``labels()`` and returns a dict, with no template involved. Everywhere a
    missing variable really does indicate a broken prompt or arg, leave it off.
    """
    env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)
    workflow_dir = Path(ManifestContext.from_context(context).skill_dir or ".")
    env.globals.update(_farrier_globals(context, workflow_dir, quiet=quiet))
    tmpl = env.from_string(template_str)
    return tmpl.render(**context)
