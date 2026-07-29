"""Preflight for the skill/prompt references a workflow's prompts make.

``instruction_ref("story-docs")`` resolves against the per-repo context manifest
(see :mod:`workhorse.templates`). When it does *not* resolve, the helper returns a
human-readable placeholder — ``generated story-docs instruction file when
installed`` — and that string is rendered straight into the agent's prompt where a
path belonged. Nothing fails; the agent is simply handed prose and left to find the
skill itself. It has cost real runs (author's epic-split gate escalating to its
auto-resolver) and it is invisible in the logs.

So the references are checked **before the first node runs**, against the manifest
this run actually loaded, and every name that will not resolve is named up front.
The check is a Jinja parse, not a regex: the templates are Jinja already, so the
call sites are in the AST — which also means every alias of the helper
(``instruction_file``/``skill_file``, ``prompt_file``) is covered for free, and a
mention inside a comment or a string is not mistaken for a call.

Two deliberate limits. Only *constant* arguments are checkable — ``instruction_ref(
skill)`` names something known at render time only, and is skipped rather than
guessed at. And a run with **no** manifest (hello-world, most tests) is skipped
whole: there, unresolved is the normal state, not a symptom.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, nodes

# The helper names exposed by workhorse.templates, grouped by what they look up.
SKILL_HELPERS = frozenset({"instruction_ref", "instruction_file", "skill_file"})
PROMPT_HELPERS = frozenset({"prompt_ref", "prompt_file"})

# Where a workflow keeps the templates rendered as node prompts. Scoped on purpose:
# a workflow's own docs may show `{{ instruction_ref(...) }}` in a fenced example,
# and a documented example is not a broken reference.
PROMPT_GLOB = "prompts/**/*.md"


@dataclass(frozen=True)
class MissingReference:
    """One reference in one template that the loaded manifest cannot resolve."""

    kind: str  # "skill" or "prompt"
    name: str
    template: str  # path relative to the workflow dir

    def __str__(self) -> str:
        return f"{self.kind} '{self.name}' (referenced in {self.template})"


def resolve_instruction(instructions: Mapping[str, str], name: str) -> str | None:
    """The installed path for a skill, tolerating pack namespacing. None when unresolved.

    A prompt asks for a *capability* (``story-docs``) while a pack is free to namespace
    the skill that provides it (``process/process-story-docs``, installed as
    ``process-story-docs``). An exact-only lookup makes those two names miss each other.

    So: exact match first, then a **unique** suffix match on the last path segment.
    Unique is the safety rule — two packs both ending in ``-story-docs`` is a genuine
    ambiguity, and silently picking one would be a worse failure than not resolving.

    Uniqueness is judged on the resolved *path*, not the key. Farrier indexes one skill
    under several aliases (bare ``process-story-docs`` and repo-prefixed
    ``todo-app-process-story-docs``), so counting keys makes every namespaced skill look
    ambiguous with itself and resolve to nothing.
    """
    if name in instructions:
        return instructions[name]
    suffix = f"-{name}"
    hits = {
        instructions[key]
        for key in instructions
        if "/" not in key and (key == name or key.endswith(suffix))
    }
    return next(iter(hits)) if len(hits) == 1 else None


def referenced_names(source: str) -> set[tuple[str, str]]:
    """Return ``{(kind, name)}`` for every helper call with a constant argument.

    A template that will not parse yields nothing: the syntax error is the render's
    to report, and swallowing it here would only turn one clear failure into two.
    """
    env = Environment()
    try:
        ast = env.parse(source)
    except TemplateSyntaxError:
        return set()

    found: set[tuple[str, str]] = set()
    for call in ast.find_all(nodes.Call):
        target = call.node
        if not isinstance(target, nodes.Name):
            continue
        if target.name in SKILL_HELPERS:
            kind = "skill"
        elif target.name in PROMPT_HELPERS:
            kind = "prompt"
        else:
            continue
        if not call.args:
            continue
        first = call.args[0]
        if isinstance(first, nodes.Const) and isinstance(first.value, str):
            found.add((kind, first.value))
    return found


def missing_references(
    workflow_dir: str | Path, context: Mapping[str, Any]
) -> list[MissingReference]:
    """Every constant skill/prompt reference in the workflow's prompts that will not resolve.

    Sorted, so the report reads the same on every run. An empty ``context`` (no
    manifest was loaded) returns nothing — see the module docstring.
    """
    if not context:
        return []
    instructions: Mapping[str, str] = context.get("_instructions") or {}
    prompts: Mapping[str, str] = context.get("_prompts") or {}

    root = Path(workflow_dir)
    missing: set[MissingReference] = set()
    for template in sorted(root.glob(PROMPT_GLOB)):
        if not template.is_file():
            continue
        try:
            source = template.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = template.relative_to(root).as_posix()
        for kind, name in referenced_names(source):
            resolved = (
                resolve_instruction(instructions, name) is not None
                if kind == "skill"
                else name in prompts
            )
            if not resolved:
                missing.add(MissingReference(kind, name, rel))
    return sorted(missing, key=lambda m: (m.template, m.kind, m.name))


def format_missing(missing: Iterable[MissingReference]) -> str:
    """The operator-facing report: what is unresolved, and what it costs."""
    items = list(missing)
    if not items:
        return ""
    lines = "\n".join(f"  - {item}" for item in items)
    return (
        f"{len(items)} reference(s) will not resolve against this repo's context "
        f"manifest:\n{lines}\n"
        "  Each renders as prose ('generated <name> instruction file when installed') "
        "into a live agent prompt.\n"
        "  Add the skill/prompt to this repo's agents.yml selection and re-run "
        "`make agent-install`."
    )
