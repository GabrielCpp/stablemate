"""Declared QA fixtures: the named arrangements a plan may ask for, and where they live."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler._vendor.stablemate_core.config import ConfigError
from ostler.manifest import read_manifest
from ostler.qa.tools import opted_in_tools

DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True)
class FixtureSpec:
    """One declared app-language fixture, as `qa.fixture(name)` will run it."""

    name: str
    tool: str
    args: tuple[str, ...]
    provides: str
    timeout: float = DEFAULT_TIMEOUT

    def as_context(self) -> dict[str, Any]:
        """The form that crosses into the harness process, JSON-shaped."""
        return {
            "tool": self.tool,
            "args": list(self.args),
            "provides": self.provides,
            "timeout": self.timeout,
        }


def declared(root: Path) -> tuple[dict[str, FixtureSpec], list[str]]:
    """Every fixture this repo declares, plus a message for each entry that is malformed."""
    try:
        manifest = read_manifest(root)
    except ConfigError as exc:
        return {}, [str(exc)]
    if manifest is None:
        return {}, []

    specs: dict[str, FixtureSpec] = {}
    errors: list[str] = []
    for name, entry in manifest.qa.fixtures.items():
        if not entry.tool:
            errors.append(f"qa fixture {name!r} has no `tool:` naming the command that runs it")
            continue
        if not (entry.provides or "").strip():
            errors.append(
                f"qa fixture {name!r} has no `provides:` — say what state it guarantees, "
                "in the same terms a scenario's `preconditions:` are written in"
            )
            continue
        specs[name] = FixtureSpec(
            name=name,
            tool=entry.tool,
            args=tuple(entry.args),
            provides=(entry.provides or "").strip(),
            timeout=float(entry.timeout),
        )
    return specs, errors


def preflight_errors(root: Path) -> list[str]:
    """Every reason this repo's declared fixtures could not be used right now."""
    specs, errors = declared(root)
    opted_in = opted_in_tools(root)
    errors.extend(
        f"qa fixture {spec.name!r} runs tool {spec.tool!r}, which this repo has not opted "
        f"into — add it to `qa: {{tools: [{spec.tool!r}]}}` or point the fixture at a tool "
        "that is already there"
        for spec in specs.values()
        if spec.tool not in opted_in
    )
    return errors


def referenced(plan: Path) -> set[str]:
    """The fixture names one plan asks for, read off its AST."""
    try:
        tree = ast.parse(plan.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "fixture"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def resolved(root: Path) -> dict[str, dict[str, Any]]:
    """`{name: spec}` for every well-formed fixture, in the form the harness receives."""
    specs, _errors = declared(root)
    return {name: spec.as_context() for name, spec in specs.items()}
