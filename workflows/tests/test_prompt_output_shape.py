"""Every `self.agent(prompt, returns=Model)` asks for the shape the prompt documents.

`engine._outputs_for` takes the keys a turn is asked for straight off the model's **top-level
field names** — there is no envelope, and every field is required. `extract_outputs` then
raises on the first declared key the reply does not carry, which puts the node on the retry →
compact → reframe ladder and, when that is exhausted, defaults every key to null. So a prompt
whose example wraps its answer (`{"qa_result": {…}}`), or names a field the model does not
have, or omits one it does, is not a cosmetic mismatch: it is a turn that can *never* parse.

Nothing surfaces it. `CoderResult` strips nulls so the defaulted reply validates back to the
model's own defaults, and the flow routes on a blank status down whatever `default:` arm it
has — a wrong answer, not a crash. The live run that motivated this file spent 134 seconds on
`code-review`, threw the result away, and carried on. It cost only wall-clock and a wrong
branch, which is exactly why it survived a port and two readings.

The two halves are checked against each other because neither is checkable alone: the model is
the contract the engine enforces, and the prompt is the only thing the agent ever sees.

The walk is over the source, like `test_prompts_exist.py`'s, and for the same reason — the
turns worth checking are the ones buried three sub-flows deep that no runtime sweep reaches.
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

import workhorse_workflows

PACKAGE = Path(workhorse_workflows.__file__).parent

#: The workflow packages whose turns declare a model. `hello_world` is the quick start and is
#: covered end-to-end by `test_hello_world.py`; `kit` is the shared library and has no prompts.
WORKFLOWS = ("author", "coder", "okf_builder", "research")

#: A fenced ```json block. A prompt may carry several — an artifact it must write, an example
#: reply — and only one of them has to be the reply.
BLOCK = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def _top_level_keys(body: str) -> set[str] | None:
    """The keys at depth 1 of the first object in `body`, or `None` if there is no object.

    Hand-scanned rather than `json.loads`ed because prompt examples are pseudo-JSON as often
    as not — `"status": "written" | "blocked"` documents a vocabulary and parses as nothing.
    Rejecting those would make this check quietly stop covering the prompts most worth
    covering, so the scanner tracks brace depth and reads the keys it can see.
    """
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
    """Every `self.agent(...)` in `source` as `(line, prompt, returns)`.

    A call missing either argument is skipped rather than failed: `returns=` is optional in
    the engine (a turn without one is asked for a single scalar key) and a non-literal prompt
    is `test_prompts_exist.py`'s finding to report, not this file's to report twice.
    """
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
        # A literal prompt is a path string; a constant of any other type is as much
        # `test_prompts_exist.py`'s finding as a non-literal one, and drops out with it.
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
    """The declared output keys, resolved through the module the turn is written in.

    Resolving in the caller's own namespace rather than searching the schema packages is what
    makes this exact: `returns=QaResult` means whatever that name is bound to *there*, which
    is the same lookup the engine does at runtime.
    """
    module = importlib.import_module(
        ".".join(source.relative_to(PACKAGE.parent).with_suffix("").parts)
    )
    name = ast.unparse(returns)
    obj = module
    for part in name.split("."):
        obj = getattr(obj, part)
    return set(getattr(obj, "model_fields", {}))


def test_the_sweep_found_turns_in_every_workflow() -> None:
    """The guard against a walker that silently matches nothing.

    Every one of these workflows runs model-returning turns, so a package contributing zero
    means the walk broke — a renamed method, a changed call shape — not that the turns went
    away. Without this the whole file passes vacuously.
    """
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
        return  # not a model: the engine asks for one scalar key, and a prompt cannot drift
    body = (PACKAGE / workflow / prompt).read_text(encoding="utf-8")
    examples = [keys for block in BLOCK.findall(body) if (keys := _top_level_keys(block))]
    assert any(keys == fields for keys in examples), (
        f"{source}:{lineno}: no ```json block in {prompt} has exactly the top-level keys "
        f"{ast.unparse(returns)} declares.\n"
        f"  declared: {sorted(fields)}\n"
        + "".join(f"  example:  {sorted(keys)}\n" for keys in examples or [set()])
        + "The turn can never parse: extract_outputs raises on the first missing key, and the "
        "node burns its whole retry ladder before defaulting every key to null."
    )
