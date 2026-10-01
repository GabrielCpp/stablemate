"""Preflight for the skill references a workflow's prompts make."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, nodes

from workhorse._vendor.stablemate_core.skill_refs import RETIRED_HELPERS, SkillCatalog

NAMED_HELPERS = frozenset({"skill_link", "skill_path", "skill_command"})

TAG_HELPERS = frozenset({"find_by_tags"})

GUARD_HELPERS = frozenset({"has_skill"})

REFERENCE_HELPERS = NAMED_HELPERS | TAG_HELPERS | frozenset(RETIRED_HELPERS)

PROMPT_GLOB = "**/prompts/**/*.md"


@dataclass(frozen=True)
class MissingReference:
    """One reference in one template that will fail to render against the catalog."""

    kind: str
    name: str
    template: str

    def __str__(self) -> str:
        if self.kind == "retired":
            return f"retired helper `{self.name}` (called in {self.template})"
        return f"skill '{self.name}' (referenced in {self.template})"


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
        if name in RETIRED_HELPERS:
            found.add(("retired", name))
        elif name in NAMED_HELPERS:
            first = node.args[0] if node.args else None
            if (
                not guarded
                and isinstance(first, nodes.Const)
                and isinstance(first.value, str)
            ):
                found.add(("skill", first.value))

    for child in node.iter_child_nodes():
        _collect(child, guarded, found)


def helpers_called(source: str) -> set[str]:
    """Every skill reference helper `source` calls, whatever its arguments, which a template this file's glob never reaches must not use."""
    ast = Environment().parse(source)
    return {
        node.node.name
        for node in ast.find_all(nodes.Call)
        if isinstance(node.node, nodes.Name) and node.node.name in REFERENCE_HELPERS
    }


def referenced_names(source: str) -> set[tuple[str, str]]:
    """Return ``{(kind, name)}`` for every unguarded constant skill reference and every retired helper call."""
    try:
        ast = Environment().parse(source)
    except TemplateSyntaxError:
        return set()

    found: set[tuple[str, str]] = set()
    _collect(ast, False, found)
    return found


def missing_references(
    workflow_dir: str | Path, catalog: SkillCatalog
) -> list[MissingReference]:
    """Every reference in the workflow's prompts that will not render against `catalog`."""
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
            if kind == "retired" or catalog.get(name) is None:
                missing.add(MissingReference(kind, name, rel))
    return sorted(missing, key=lambda m: (m.template, m.kind, m.name))


def format_missing(missing: Iterable[MissingReference]) -> str:
    """The operator-facing report: what will not render, and how to fix it."""
    items = list(missing)
    if not items:
        return ""
    lines = "\n".join(f"  - {item}" for item in items)
    return (
        f"{len(items)} skill reference(s) will fail to render:\n{lines}\n"
        "  A turn whose prompt makes one stops with an error.\n"
        "  Install the skill in this repo or at home with `farrier install`, "
        "and move a retired helper to the one its error names."
    )
