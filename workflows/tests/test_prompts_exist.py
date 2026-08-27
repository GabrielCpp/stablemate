"""Every `self.agent("prompts/…")` in the distribution names a file that is packaged.

A prompt path is the one argument in the new shape that nothing checks until the turn
fires. A misspelled node name is an `UnknownNodeError` at import, a wrong `returns=` is a
validation error on the first reply, and a bad transition target is caught by the driver —
but a prompt that was renamed, or copied from a YAML workflow whose file did not come with
it, is a run that gets all the way to an agent turn before it fails. The YAML had the same
hole; it is cheap to close statically, so this closes it for every workflow at once.

The walk is over the source rather than over the loaded classes on purpose: a state that is
only reachable three sub-flows and an operator gate deep is exactly the one whose prompt
nobody notices is missing, and a runtime sweep would have to reach it to see it.

Non-literal prompts are a failure here rather than a skip, with two shapes excused. A
conditional between two literals (`"a.md" if cond else "b.md"`, which is how okf-builder's
one drain state picks the repair prompt over the discovery one) — both arms are checked, so
nothing stops being covered. And `turn.prompt`, the coder workflow's role indirection: the
`turn = roles.turn(self, "dev-fix")` that produced it is in the same function, so the role
name is still a literal in the source — or a conditional between two literals, which gets
the same both-arms treatment — and the envelope it resolves to is still checkable
here — under the calling flow's own `prompts/`, which is the directory the walked file
sits in. That is the whole reason the resolver names the envelope after its own stem. Anything
else — a computed name, an f-string — is a failure, because silently dropping it would turn
this check into one that quietly stops covering things.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

#: The workflow packages. `kit` is the shared library and has no prompts of its own.
WORKFLOWS = ("author", "coder", "hello_world", "okf_builder", "research")


def _agent_prompts(source: Path) -> list[tuple[int, ast.expr]]:
    """Every `self.agent(...)`'s prompt argument in `source`, with its line number.

    A `turn.prompt` argument is rewritten to the literal envelope path the role it came
    from resolves to, so the caller sees the same `ast.Constant` a hand-written path
    gives it and the check below stays one assertion.
    """
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
    """Every `<name> = roles.turn(self, "<role>")` in the module, by the line it is on.

    The role argument gets the same ternary allowance the prompt argument does below: a
    state that picks its role from the item it drew names two envelopes, and both are
    recorded so both are checked. An arm that is not a string literal spoils the whole
    site — recording the literal arm alone would half-cover it silently.
    """
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
    """`turn.prompt` → the envelope paths of the nearest preceding `roles.turn(…)`.

    Nearest *preceding* rather than "the one in this function": the walk is over an AST
    with no scope attached, and every call site in this repo assigns its `turn` on the
    lines immediately above the `self.agent(` it feeds. An assignment that is not the
    right one would have to sit between the two, which is the same mistake a reader would
    make. Nothing preceding it at all is left alone, and fails as non-literal below.
    """
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
    """The prompt expressions one call site can render — both arms of a ternary, else one.

    A state that picks its prompt from the item it drew (`repair.md` for a `fix:` item,
    `investigate.md` otherwise) still names two packaged files; checking only the whole
    expression would report it as non-literal and check neither.
    """
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
    """The guard against a walker that silently matches nothing.

    Every one of these workflows runs agent turns, so a package contributing zero sites
    means the walk broke — a renamed method, a changed call shape — not that the workflow
    stopped using agents.
    """
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
