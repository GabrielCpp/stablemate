"""Every `{{ … }}` a prompt reads is something its own `self.agent(args=…)` passes.

The renderer is deliberately forgiving: `templates.ResilientUndefined` logs a warning and
renders **empty** rather than raising, because a week-long unattended run must not die on one
bad reference (`workhorse_var` is even more forgiving — it is `context.get(name, "")`). That is
the right call for the run and the wrong one for the author: an unpassed variable is a hole in
the prompt that only a live render shows, and only to whoever is reading the console at that
second.

The costly shape is not a typo'd argument, though. It is a prompt that documents *another*
tool's `{{ }}` syntax — Jinja renders the prompt first and eats it. `plan-qa.md` teaches the
`ostler qa plan` DSL, whose capture references are spelled `{{key}}`; unescaped, the live run
handed the planner "Use `` to reference values captured by prior steps" and a worked example
reading `curl -H "Device: " ...`. Not a missing hint — an *instruction to write a broken
command*, in the one file whose whole job is teaching that DSL. The fix is `{% raw %}`, and
what makes this test the lock for it is that Jinja's own parser is what reports the variables:
text inside `{% raw %}` is not a reference, so escaping a block is exactly what turns the
finding off.

The check is per *prompt*, against the union of what all its call sites pass — deliberately
weaker than per-site, because per-site is wrong here. A prompt's optional sections are real:
`rework-story.md` reads `prior_attempts` under an `{% if %}` and is reached both from the
gate-failure rework (which has a ledger) and the operator-feedback rework (which does not),
and `coder/workflow.py`'s nested `implement-plan` turn documents omitting three arguments the
`dev` flow passes as preserved YAML behavior. Flagging those would report decisions as
defects, and a test that cries wolf on its first eight findings gets deleted. A name that
*no* site supplies has no such reading: nothing in the workflow can ever fill it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from jinja2 import Environment, nodes
from jinja2.meta import find_undeclared_variables

import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

#: Mirrors `test_prompt_output_shape.WORKFLOWS` — the packages whose turns render prompts.
WORKFLOWS = ("author", "coder", "okf_builder", "research")

#: Names present in every prompt context, so a reference to one is never a missing argument:
#: the helpers `workhorse.templates._globals` installs, the manifest namespaces
#: `workhorse.manifest.context_from` builds (`{{ repo.name }}`), and the two timeout values
#: `runner.ladder` stamps on before rendering.
AMBIENT = {
    "workhorse_var",
    "agent_cli",
    "skill_load_ref",
    "get_node_output",
    "skill_dir",
    "instruction_ref",
    "instruction_file",
    "skill_file",
    "prompt_file",
    "prompt_ref",
    "instruction_refs",
    "find_by_tags",
    "instruction_files",
    "skill_files",
    "prompt_refs",
    "prompt_files",
    "isUsingInstruction",
    "template",
    "repo",
    "vars",
    "node_timeout_s",
    "node_timeout_min",
}


def _dict_keys(node: ast.Dict, spread: str | None) -> set[str] | None:
    """The string keys of a dict literal, or `None` if any of them cannot be named.

    `spread` is the name of a `**kwargs` parameter whose expansion is expected and ignored:
    a helper that returns `{…, **extra}` names the fixed part here and its caller names the
    rest. Any other `**` expansion is unreadable.
    """
    keys: set[str] = set()
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            if spread and isinstance(value, ast.Name) and value.id == spread:
                continue
            return None
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        keys.add(key.value)
    return keys


def _keys_of(node: ast.expr, scope: ast.AST, module: ast.Module) -> set[str] | None:
    """The keys the expression an `args=` was given resolves to, or `None` if unreadable.

    Three shapes reach it, and all three are load-bearing. A literal `{…}` is the common one.
    A local `args` variable is how `coder/qa/flow.py::_apply_fixes` adds `operator_feedback`
    conditionally — the plain fix path's YAML args did not carry the key at all — and reading
    only the literal would report that omission as a hole in the prompt. `self._helper(…)` is
    how `research/workflow.py` shares the program triple across a dozen turns.
    """
    if isinstance(node, ast.Dict):
        return _dict_keys(node, None)
    if isinstance(node, ast.Name):
        return _keys_of_local(node.id, scope, module)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ):
        return _keys_of_helper(node, module)
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


def _keys_of_helper(call: ast.Call, module: ast.Module) -> set[str] | None:
    """The keys `self._helper(**kwargs)` yields: what the helper returns, plus this call's own.

    Only a helper whose returns are dict literals is readable, which is the whole population
    today. A `**` expansion at the call site is not: its keys live wherever that mapping came
    from.
    """
    name = call.func.attr  # type: ignore[union-attr]  # the caller checked the shape
    defs = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
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
        returned = _dict_keys(node.value, spread)
        if returned is None:
            return None
        keys |= returned
    for keyword in call.keywords:
        if keyword.arg is None:
            return None
        keys.add(keyword.arg)
    return keys


def _scopes(tree: ast.Module) -> dict[int, ast.AST]:
    """Each `Call` in `tree` mapped to the innermost function that encloses it.

    Innermost matters: `_keys_of_local` reads assignments out of the returned scope, and the
    module reads as one flat scope in which two functions' identically named locals merge.
    """
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
    """Every `self.agent(prompt, args=…)` in `source` as `(line, prompt, arg names)`, plus the
    lines of the sites whose arguments no static reading can name.

    Unreadable means computed — a comprehension, a `**spread`, a dict handed in from
    elsewhere. There are none today and `test_no_turn_is_unreadable` keeps it that way,
    because a prompt checked against a *partial* vocabulary invents findings, and this is the
    one test whose findings must never be wrong.
    """
    found: list[tuple[int, str, set[str]]] = []
    opaque: list[int] = []
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    enclosing = _scopes(tree)
    for node in ast.walk(tree):
        fn = node.func if isinstance(node, ast.Call) else None
        if not (isinstance(fn, ast.Attribute) and fn.attr == "agent"):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "self"):
            continue
        prompt = node.args[0] if node.args else None
        args = None
        for kw in node.keywords:
            if kw.arg == "prompt":
                prompt = kw.value
            elif kw.arg == "args":
                args = kw.value
        if not isinstance(prompt, ast.Constant):
            continue
        keys = set() if args is None else _keys_of(args, enclosing[id(node)], tree)
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


#: Call sites `_turns` could not read arguments from — see `test_no_turn_is_unreadable`.
OPAQUE: list[str] = []

PROMPTS = _prompts()


def _referenced(body: str) -> set[str]:
    """The names `body` reads, by Jinja's own parse.

    Two spellings reach the same context dict and both count: a bare `{{ name }}`, which the
    parser reports, and `workhorse_var('name')`, whose argument is a string the parser has no
    reason to look inside. The second is the sanctioned spelling in these prompts, so reading
    only the first would check mostly the wrong half.
    """
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
    """The guard against a walker that matches nothing — the same one
    `test_prompt_output_shape.py` carries, and for the same reason. Every one of these
    packages passes literal args to at least one turn, so a zero means the call shape moved,
    not that the turns did."""
    by_workflow = {name: 0 for name in WORKFLOWS}
    for name, _prompt in PROMPTS:
        by_workflow[name] += 1
    assert all(by_workflow.values()), by_workflow


def test_no_turn_is_unreadable() -> None:
    """No turn builds its arguments in a way `_turns` cannot name.

    A site it cannot read contributes nothing to its prompt's vocabulary, so every name that
    site alone supplies reads as missing — the sweep would start reporting live wiring as
    holes. Better to fail here, where the message says the walker needs teaching."""
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
