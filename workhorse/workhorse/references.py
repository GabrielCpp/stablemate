"""Preflight for the skill/prompt references a workflow's prompts make."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, nodes

from workhorse.manifest import ManifestContext

SKILL_HELPERS = frozenset(
    {"instruction_ref", "instruction_file", "skill_file", "skill_load_ref"}
)
PROMPT_HELPERS = frozenset({"prompt_ref", "prompt_file"})

OPTIONAL_SKILL_HELPERS = frozenset({"instruction_refs", "instruction_files", "skill_files"})
OPTIONAL_PROMPT_HELPERS = frozenset({"prompt_refs", "prompt_files"})

TAG_HELPERS = frozenset({"find_by_tags"})

GUARD_HELPERS = frozenset({"isUsingInstruction", "is_using_instruction"})

PROMPT_GLOB = "**/prompts/**/*.md"


@dataclass(frozen=True)
class MissingReference:
    """One reference in one template that the loaded manifest cannot resolve."""

    kind: str
    name: str
    template: str

    def __str__(self) -> str:
        return f"{self.kind} '{self.name}' (referenced in {self.template})"


def resolve_instruction(instructions: Mapping[str, str], name: str) -> str | None:
    """The installed path for a skill, tolerating pack namespacing."""
    if name in instructions:
        return instructions[name]
    suffix = f"-{name}"
    hits = {
        instructions[key]
        for key in instructions
        if "/" not in key and (key == name or key.endswith(suffix))
    }
    return next(iter(hits)) if len(hits) == 1 else None


def _is_guard(test: nodes.Node) -> bool:
    """Whether an ``{% if %}`` test asks whether a skill is installed."""
    candidates = [test, *test.find_all(nodes.Call)]
    return any(
        isinstance(call, nodes.Call)
        and isinstance(call.node, nodes.Name)
        and call.node.name in GUARD_HELPERS
        for call in candidates
    )


def _collect(node: nodes.Node, guarded: bool, found: set[tuple[str, str]]) -> None:
    """Walk the AST, carrying whether this subtree sits behind an installed-skill guard."""
    if isinstance(node, nodes.If):
        _collect(node.test, guarded, found)
        body_guarded = guarded or _is_guard(node.test)
        for child in node.body:
            _collect(child, body_guarded, found)
        for child in [*node.elif_, *node.else_]:
            _collect(child, guarded, found)
        return

    if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name):
        name = node.node.name
        if name in SKILL_HELPERS or name in PROMPT_HELPERS:
            kind = "skill" if name in SKILL_HELPERS else "prompt"
            first = node.args[0] if node.args else None
            if (
                not guarded
                and isinstance(first, nodes.Const)
                and isinstance(first.value, str)
            ):
                found.add((kind, first.value))
        elif (
            name in OPTIONAL_SKILL_HELPERS
            or name in OPTIONAL_PROMPT_HELPERS
            or name in TAG_HELPERS
        ):
            return

    for child in node.iter_child_nodes():
        _collect(child, guarded, found)


def referenced_names(source: str) -> set[tuple[str, str]]:
    """Return ``{(kind, name)}`` for every REQUIRED reference with a constant argument."""
    env = Environment()
    try:
        ast = env.parse(source)
    except TemplateSyntaxError:
        return set()

    found: set[tuple[str, str]] = set()
    _collect(ast, False, found)
    return found


def missing_references(
    workflow_dir: str | Path, context: Mapping[str, Any]
) -> list[MissingReference]:
    """Every constant skill/prompt reference in the workflow's prompts that will not resolve."""
    if not context:
        return []
    manifest = ManifestContext.from_context(context)
    instructions: Mapping[str, str] = manifest.instructions
    prompts: Mapping[str, str] = manifest.prompts

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
