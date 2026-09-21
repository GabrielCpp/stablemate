"""Every `self.agent("prompts/…")` in the distribution names a file that is packaged."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

WORKFLOWS = ("author", "coder", "loop_runner", "okf_builder", "research")


def _agent_prompts(source: Path) -> list[tuple[int, ast.expr]]:
    """Every `self.agent(...)`'s prompt argument in `source`, with its line number."""
    found: list[tuple[int, ast.expr]] = []
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    resolved = _roles_by_line(tree)
    flow = source.parent.name
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "agent"):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "self"):
            continue
        if node.args:
            found.extend(
                (node.lineno, lit)
                for arg in _branches(node.args[0])
                for lit in _literalize(arg, resolved, flow)
            )
            continue
        for kw in node.keywords:
            if kw.arg == "prompt":
                found.extend(
                    (node.lineno, lit)
                    for arg in _branches(kw.value)
                    for lit in _literalize(arg, resolved, flow)
                )
    return found


def _roles_by_line(tree: ast.Module) -> dict[int, list[str]]:
    """Every `<name> = roles.turn(self, "<role>")` in the module, by the line it is on."""
    seen: dict[int, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        fn = node.value.func
        named_roles_turn = (
            isinstance(fn, ast.Attribute)
            and fn.attr == "turn"
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "roles"
        )
        if not named_roles_turn or len(node.value.args) < 2:
            continue
        roles: list[str] = []
        for arm in _branches(node.value.args[1]):
            if not (isinstance(arm, ast.Constant) and isinstance(arm.value, str)):
                break
            roles.append(arm.value)
        else:
            seen[node.lineno] = roles
    return seen


def _literalize(arg: ast.expr, resolved: dict[int, list[str]], flow: str) -> list[ast.expr]:
    """`turn.prompt` → the envelope paths of the nearest preceding `roles.turn(…)`."""
    is_turn_prompt = (
        isinstance(arg, ast.Attribute)
        and arg.attr == "prompt"
        and isinstance(arg.value, ast.Name)
        and arg.value.id == "turn"
    )
    if not is_turn_prompt:
        return [arg]
    before = [line for line in resolved if line <= arg.lineno]
    if not before:
        return [arg]
    return [
        ast.Constant(value=f"{flow}/prompts/{role}.md") for role in resolved[max(before)]
    ]


def _branches(arg: ast.expr) -> list[ast.expr]:
    """The prompt expressions one call site can render — both arms of a ternary, else one."""
    if isinstance(arg, ast.IfExp):
        return [*_branches(arg.body), *_branches(arg.orelse)]
    return [arg]


def _sites() -> list[tuple[str, Path, int, ast.expr]]:
    sites: list[tuple[str, Path, int, ast.expr]] = []
    for name in WORKFLOWS:
        for source in sorted((PACKAGE / name).rglob("*.py")):
            for lineno, arg in _agent_prompts(source):
                sites.append((name, source, lineno, arg))
    return sites


SITES = _sites()


def test_the_sweep_found_turns_in_every_workflow() -> None:
    """The guard against a walker that silently matches nothing."""
    by_workflow = {name: 0 for name in WORKFLOWS}
    for name, _source, _lineno, _arg in SITES:
        by_workflow[name] += 1
    assert all(by_workflow.values()), by_workflow


@pytest.mark.parametrize(
    ("workflow", "source", "lineno", "arg"),
    SITES,
    ids=[f"{name}:{source.stem}:{lineno}" for name, source, lineno, _arg in SITES],
)
def test_the_prompt_file_is_there(
    workflow: str, source: Path, lineno: int, arg: ast.expr
) -> None:
    assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
        f"{source}:{lineno}: prompt is not a literal, so this check cannot see it"
    )
    prompt = PACKAGE / workflow / arg.value
    assert prompt.is_file(), f"{source}:{lineno}: no such prompt {prompt}"
