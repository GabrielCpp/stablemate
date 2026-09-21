"""Every `self.agent(prompt, returns=Model)` asks for the shape the prompt documents."""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

WORKFLOWS = ("author", "coder", "okf_builder", "research")

BLOCK = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def _top_level_keys(body: str) -> set[str] | None:
    """The keys at depth 1 of the first object in `body`, or `None` if there is no object."""
    depth = 0
    keys: set[str] = set()
    started = False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '"':
            j = i + 1
            while j < len(body) and body[j] != '"':
                j += 2 if body[j] == "\\" else 1
            if depth == 1 and re.match(r"\s*:", body[j + 1 :]):
                keys.add(body[i + 1 : j])
            i = j + 1
            continue
        if ch in "{[":
            depth += 1
            started = True
        elif ch in "}]":
            depth -= 1
            if started and depth == 0:
                break
        i += 1
    return keys or None


def _turns(source: Path) -> list[tuple[int, str, ast.expr]]:
    """Every `self.agent(...)` in `source` as `(line, prompt, returns)`."""
    found: list[tuple[int, str, ast.expr]] = []
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "agent"):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "self"):
            continue
        prompt: ast.expr | None = node.args[0] if node.args else None
        returns: ast.expr | None = None
        for kw in node.keywords:
            if kw.arg == "prompt":
                prompt = kw.value
            elif kw.arg == "returns":
                returns = kw.value
        if returns is not None and isinstance(prompt, ast.Constant):
            if isinstance(prompt.value, str):
                found.append((node.lineno, prompt.value, returns))
    return found


def _sites() -> list[tuple[str, Path, int, str, ast.expr]]:
    sites: list[tuple[str, Path, int, str, ast.expr]] = []
    for name in WORKFLOWS:
        for source in sorted((PACKAGE / name).rglob("*.py")):
            for lineno, prompt, returns in _turns(source):
                sites.append((name, source, lineno, prompt, returns))
    return sites


SITES = _sites()


def _model_fields(source: Path, returns: ast.expr) -> set[str]:
    """The declared output keys, resolved through the module the turn is written in."""
    module = importlib.import_module(
        ".".join(source.relative_to(PACKAGE.parent).with_suffix("").parts)
    )
    name = ast.unparse(returns)
    obj = module
    for part in name.split("."):
        obj = getattr(obj, part)
    return set(getattr(obj, "model_fields", {}))


def test_the_sweep_found_turns_in_every_workflow() -> None:
    """The guard against a walker that silently matches nothing."""
    by_workflow = {name: 0 for name in WORKFLOWS}
    for name, _source, _lineno, _prompt, _returns in SITES:
        by_workflow[name] += 1
    assert all(by_workflow.values()), by_workflow


@pytest.mark.parametrize(
    ("workflow", "source", "lineno", "prompt", "returns"),
    SITES,
    ids=[f"{name}:{source.stem}:{lineno}" for name, source, lineno, _p, _r in SITES],
)
def test_the_prompt_documents_the_keys_the_turn_is_asked_for(
    workflow: str, source: Path, lineno: int, prompt: str, returns: ast.expr
) -> None:
    fields = _model_fields(source, returns)
    if not fields:
        return
    body = (PACKAGE / workflow / prompt).read_text(encoding="utf-8")
    if "{{ result_schema }}" in body:
        return
    examples = [keys for block in BLOCK.findall(body) if (keys := _top_level_keys(block))]
    assert any(keys == fields for keys in examples), (
        f"{source}:{lineno}: no ```json block in {prompt} has exactly the top-level keys "
        f"{ast.unparse(returns)} declares.\n"
        f"  declared: {sorted(fields)}\n"
        + "".join(f"  example:  {sorted(keys)}\n" for keys in examples or [set()])
        + "The turn can never parse: extract_outputs raises on the first missing key, and the "
        "node burns its whole retry ladder before defaulting every key to null."
    )
