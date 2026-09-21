"""Every `{{ … }}` a prompt reads is something its own `self.agent(args=…)` passes."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from jinja2 import Environment, nodes
from jinja2.meta import find_undeclared_variables

from workhorse.templates import _farrier_globals
import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

WORKFLOWS = ("author", "coder", "okf_builder", "research")

AMBIENT = set(_farrier_globals({}, PACKAGE, quiet=True)) | {
    "template",
    "repo",
    "vars",
    "node_timeout_s",
    "node_timeout_min",
}


def _package_defs() -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every module-level function in the package, by name."""
    index: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for source in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                index.setdefault(node.name, []).append(node)
    return index


_PACKAGE_DEFS = _package_defs()


def _dict_keys(
    node: ast.Dict, spread: str | None, scope: ast.AST, module: ast.Module
) -> set[str] | None:
    """The string keys of a dict literal, or `None` if any of them cannot be named."""
    keys: set[str] = set()
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            if spread and isinstance(value, ast.Name) and value.id == spread:
                continue
            expanded = _keys_of(value, scope, module)
            if expanded is None:
                return None
            keys |= expanded
            continue
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.add(key.value)
    return keys


def _keys_of(node: ast.expr, scope: ast.AST, module: ast.Module) -> set[str] | None:
    """The keys the expression an `args=` was given resolves to, or `None` if unreadable."""
    if isinstance(node, ast.Dict):
        return _dict_keys(node, None, scope, module)
    if isinstance(node, ast.Name):
        return _keys_of_local(node.id, scope, module)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ):
        return _keys_of_helper(node.func.attr, node, module)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _keys_of_helper(node.func.id, node, module)
    return None


def _keys_of_local(name: str, scope: ast.AST, module: ast.Module) -> set[str] | None:
    """The keys a local dict is built from, across `name = …` and `name[<literal>] = …`."""
    keys: set[str] = set()
    for stmt in ast.walk(scope):
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == name:
                assigned = _keys_of(stmt.value, scope, module)
                if assigned is None:
                    return None
                keys |= assigned
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == name
            ):
                key = target.slice
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    return None
                keys.add(key.value)
    return keys


def _defs(name: str, module: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every definition of `name`, in `module` if it has one, else across the package."""
    local = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    return local or _PACKAGE_DEFS.get(name, [])


def _keys_of_helper(name: str, call: ast.Call, module: ast.Module) -> set[str] | None:
    """The keys `helper(**kwargs)` yields: what the helper returns, plus this call's own."""
    defs = _defs(name, module)
    if len(defs) != 1:
        return None
    helper = defs[0]
    spread = helper.args.kwarg.arg if helper.args.kwarg else None
    keys: set[str] = set()
    returns = [n for n in ast.walk(helper) if isinstance(n, ast.Return) and n.value is not None]
    if not returns:
        return None
    for node in returns:
        if not isinstance(node.value, ast.Dict):
            return None
        returned = _dict_keys(node.value, spread, helper, module)
        if returned is None:
            return None
        keys |= returned
    for keyword in call.keywords:
        if keyword.arg is None:
            return None
        keys.add(keyword.arg)
    return keys


def _scopes(tree: ast.Module) -> dict[int, ast.AST]:
    """Each `Call` in `tree` mapped to the innermost function that encloses it."""
    enclosing: dict[int, ast.AST] = {}

    def descend(node: ast.AST, scope: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                enclosing[id(child)] = scope
            inner = child if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else scope
            descend(child, inner)

    descend(tree, tree)
    return enclosing


def _turns(source: Path) -> tuple[list[tuple[int, str, set[str]]], list[int]]:
    """Every `self.agent(prompt, args=…)` in `source` as `(line, prompt, arg names)`, plus the lines of the sites whose arguments no static reading can name."""
    found: list[tuple[int, str, set[str]]] = []
    opaque: list[int] = []
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    enclosing = _scopes(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "agent"):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "self"):
            continue
        prompt: ast.expr | None = node.args[0] if node.args else None
        args: ast.expr | None = None
        for kw in node.keywords:
            if kw.arg == "prompt":
                prompt = kw.value
            elif kw.arg == "args":
                args = kw.value
        if not (isinstance(prompt, ast.Constant) and isinstance(prompt.value, str)):
            continue
        keys: set[str] | None = (
            set() if args is None else _keys_of(args, enclosing[id(node)], tree)
        )
        if keys is None:
            opaque.append(node.lineno)
            continue
        found.append((node.lineno, prompt.value, keys))
    return found, opaque


def _prompts() -> dict[tuple[str, str], tuple[set[str], list[str]]]:
    """`(workflow, prompt)` → (every name any of its turns passes, where those turns are)."""
    found: dict[tuple[str, str], tuple[set[str], list[str]]] = {}
    for name in WORKFLOWS:
        for source in sorted((PACKAGE / name).rglob("*.py")):
            turns, opaque = _turns(source)
            for lineno, prompt, args in turns:
                vocabulary, sites = found.setdefault((name, prompt), (set(), []))
                vocabulary |= args
                sites.append(f"{source.relative_to(PACKAGE)}:{lineno}")
            OPAQUE.extend(f"{source.relative_to(PACKAGE)}:{line}" for line in opaque)
    return found


OPAQUE: list[str] = []

PROMPTS = _prompts()


def _referenced(body: str) -> set[str]:
    """The names `body` reads, by Jinja's own parse."""
    env = Environment()
    tree = env.parse(body)
    names = set(find_undeclared_variables(tree))
    for call in tree.find_all(nodes.Call):
        if getattr(call.node, "name", None) != "workhorse_var":
            continue
        for arg in call.args:
            if isinstance(arg, nodes.Const) and isinstance(arg.value, str):
                names.add(arg.value)
    return names


def test_the_sweep_checks_every_workflow() -> None:
    """The guard against a walker that matches nothing — the same one `test_prompt_output_shape.py` carries, and for the same reason."""
    by_workflow = {name: 0 for name in WORKFLOWS}
    for name, _prompt in PROMPTS:
        by_workflow[name] += 1
    assert all(by_workflow.values()), by_workflow


def test_no_turn_is_unreadable() -> None:
    """No turn builds its arguments in a way `_turns` cannot name."""
    assert not OPAQUE, OPAQUE


@pytest.mark.parametrize(
    ("workflow", "prompt"),
    sorted(PROMPTS),
    ids=[f"{name}:{Path(prompt).stem}" for name, prompt in sorted(PROMPTS)],
)
def test_the_prompt_reads_only_names_the_workflow_can_supply(workflow: str, prompt: str) -> None:
    vocabulary, sites = PROMPTS[(workflow, prompt)]
    body = (PACKAGE / workflow / prompt).read_text(encoding="utf-8")
    missing = sorted(_referenced(body) - AMBIENT - vocabulary)
    assert not missing, (
        f"{workflow}/{prompt} reads {missing}, which no turn that renders it passes and no "
        f"prompt context supplies.\n"
        f"  rendered by: {', '.join(sites)}\n"
        f"  passed between them: {sorted(vocabulary)}\n"
        "Each renders empty — the reference is deleted from the prompt the agent reads, with "
        "one warning on the console. If the text is documenting another tool's {{ }} syntax "
        "rather than reading a value, wrap it in {% raw %} … {% endraw %}."
    )
