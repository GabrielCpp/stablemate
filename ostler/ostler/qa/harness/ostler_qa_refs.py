from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

CHECK_METHODS = frozenset({"check", "require", "eventually", "require_eventually", "verify", "settle", "holds"})


@dataclass(frozen=True)
class _ParsedPlan:
    """A plan's source parsed once: its module constants and every call each top-level function reaches."""

    constants: dict[str, Any]
    reachable: dict[str, list[ast.Call]]


@lru_cache(maxsize=1)
def _tree(source: str) -> ast.Module:
    """The plan source's syntax tree, parsed once for both the import and the extractors."""
    return ast.parse(source)


@lru_cache(maxsize=1)
def _parsed(source: str) -> _ParsedPlan:
    """The plan source parsed once, so every extractor reading the same plan shares one parse and one walk."""
    tree = _tree(source)
    return _ParsedPlan(_module_constants(tree), _reachable_calls(tree))


def count_checks(source: str) -> dict[str, int]:
    """How many assertion calls each function reaches, including a state settle's recorded verdict."""
    reachable = _parsed(source).reachable
    return {
        name: sum(
            1
            for call in calls
            if isinstance(call.func, ast.Attribute) and call.func.attr in CHECK_METHODS
        )
        for name, calls in reachable.items()
    }


def _reachable_calls(tree: ast.Module) -> dict[str, list[ast.Call]]:
    """Every call each top-level function makes, following the module helpers it calls."""
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    walked: dict[str, list[ast.Call]] = {}

    def own(name: str) -> list[ast.Call]:
        if name not in walked:
            calls = [child for child in ast.walk(functions[name]) if isinstance(child, ast.Call)]
            walked[name] = sorted(calls, key=lambda call: (call.lineno, call.col_offset))
        return walked[name]

    found: dict[str, list[ast.Call]] = {}
    for name in functions:
        seen = {name}
        pending = [name]
        calls: list[ast.Call] = []
        while pending:
            body = own(pending.pop(0))
            calls.extend(body)
            for call in body:
                if not isinstance(call.func, ast.Name) or call.func.id in seen:
                    continue
                if call.func.id in functions:
                    seen.add(call.func.id)
                    pending.append(call.func.id)
        found[name] = calls
    return found


def extract_check_covers(source: str) -> dict[str, list[str]]:
    """Which obligation ids each scenario's assertion calls claim, as written."""
    parsed = _parsed(source)
    constants = parsed.constants
    found: dict[str, list[str]] = {}
    for name, calls in parsed.reachable.items():
        claimed: list[str] = []
        for call in calls:
            if (
                not isinstance(call.func, ast.Attribute)
                or call.func.attr not in CHECK_METHODS
            ):
                continue
            for keyword in call.keywords:
                if keyword.arg == "covers":
                    claimed.extend(_covers_ids(keyword.value, constants))
        found[name] = claimed
    return found


def _resolve(node: ast.expr, constants: dict[str, Any]) -> Any:
    """The value the parse can attribute to this expression, or `None` when it cannot."""
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return _literal(node)


def _check_argument(node: ast.expr, constants: dict[str, Any]) -> Any:
    """A check argument's value, reading `qa.resolve("<text>")` as the text the book declared."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve"
            and len(node.args) == 1 and not node.keywords):
        text = _resolve(node.args[0], constants)
        if isinstance(text, str):
            return text
    return _resolve(node, constants)


def _covers_ids(node: ast.expr, constants: dict[str, Any]) -> list[str]:
    """The obligation ids a `covers=` argument binds, with `COMPUTED` for each unreadable one."""
    written = _resolve(node, constants)
    if isinstance(written, (list, tuple)):
        return [item if isinstance(item, str) else COMPUTED for item in written]
    if isinstance(node, (ast.List, ast.Tuple)):
        elements = [_resolve(element, constants) for element in node.elts]
        return [item if isinstance(item, str) else COMPUTED for item in elements]
    return [COMPUTED]


def _module_constants(tree: ast.Module) -> dict[str, Any]:
    """Module-level `NAME = <literal>` bindings, minus every name bound more than once."""
    constants: dict[str, Any] = {}
    rebound: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            targets = [node.target] if node.value is not None else []
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in constants:
                rebound.add(target.id)
            constants[target.id] = _literal(value) if value is not None else None
    for name in rebound:
        constants.pop(name, None)
    return constants


COMPUTED = "*"


FIXTURE_METHOD = "fixture"


def extract_fixtures(source: str) -> dict[str, list[str]]:
    """Which book fixtures each scenario arranges, as written, leaving out a name computed at run time."""
    found: dict[str, list[str]] = {}
    for name, calls in _parsed(source).reachable.items():
        fixtures: list[str] = []
        for call in calls:
            if not isinstance(call.func, ast.Attribute) or call.func.attr != FIXTURE_METHOD:
                continue
            fixture = _literal(call.args[0]) if call.args else None
            if isinstance(fixture, str) and fixture not in fixtures:
                fixtures.append(fixture)
        found[name] = fixtures
    return found


def _literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None
