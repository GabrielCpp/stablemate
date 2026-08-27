"""Every model a coder turn's output contract is rendered from describes all of its fields.

The contract block a prompt shows is generated from the pydantic model that parses the
reply (`shared/schemas/render.py`), which removes the drift a hand-written `Return Format`
section carried but moves the burden: the field prose the prompt used to spell out is now
`Field(description=...)`, and a field without one renders as a bare type the agent has to
guess the meaning of. Nothing in pydantic requires a description, so this is the check that
does.

The models are discovered rather than listed, by reading the `returns=` of every
`roles.turn(...)` call and every `schema_block(...)` argument in the coder package. A list
would be a third copy of the same fact and would go stale the first time a lane added a
turn — which is exactly the failure the rendering removed one instance of.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel

import workhorse_workflows
from workhorse_workflows.coder.shared.schemas import render

CODER = Path(workhorse_workflows.__file__).parent / "coder"


def _rendered_model_names() -> set[str]:
    """The class names named at a `returns=` of `roles.turn` or an argument of `schema_block`."""
    names: set[str] = set()
    for path in sorted(CODER.rglob("*.py")):
        # `roles.turn` is the threading point: it calls `schema_block(returns)` on the
        # parameter every callsite binds, so reading it back names the parameter.
        if path == CODER / "shared" / "roles.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "turn":
                names |= {
                    kw.value.id
                    for kw in node.keywords
                    if kw.arg == "returns" and isinstance(kw.value, ast.Name)
                }
            elif isinstance(func, ast.Name) and func.id == "schema_block":
                names |= {arg.id for arg in node.args if isinstance(arg, ast.Name)}
    return names


def _model(name: str) -> type[BaseModel]:
    """The schema class that name refers to, from the one package the lanes import it from."""
    import importlib

    for module in sorted(p.stem for p in (CODER / "shared" / "schemas").glob("*.py")):
        loaded = importlib.import_module(
            f"workhorse_workflows.coder.shared.schemas.{module}"
        )
        found = getattr(loaded, name, None)
        if isinstance(found, type) and issubclass(found, BaseModel):
            return found
    raise AssertionError(f"{name} is rendered into a prompt but is not a schema class")


MODEL_NAMES = sorted(_rendered_model_names())


def test_every_lane_renders_at_least_one_contract() -> None:
    """The discovery is the test's own input, so an empty sweep would pass vacuously."""
    assert len(MODEL_NAMES) >= 10


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_rendered_models_describe_every_field(name: str) -> None:
    model = _model(name)
    assert render.described_fields(model.model_json_schema()) == []


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_rendered_contracts_ask_for_a_document(name: str) -> None:
    """The block frames the schema as something to comply with, not something to echo."""
    block = render.schema_block(_model(name))
    assert block.startswith(render.PREAMBLE)
    assert '"title"' not in block


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_class_docstrings_stay_out_of_the_contract(name: str) -> None:
    """The rationale a class docstring carries is for the maintainer, not for the turn.

    Pydantic lifts it into the schema's object-level `description`, where it would reach the
    agent as part of the contract — several paragraphs on which gate reads a field and what a
    key used to be called, in a document whose whole job is to say what to return.
    """
    model = _model(name)
    for owner in [model, *(f.annotation for f in model.model_fields.values())]:
        doc = getattr(owner, "__doc__", None)
        first = (doc or "").strip().splitlines()[:1]
        if first and isinstance(owner, type) and issubclass(owner, BaseModel):
            assert first[0] not in render.schema_block(model), f"{owner.__name__}: {first[0]}"
