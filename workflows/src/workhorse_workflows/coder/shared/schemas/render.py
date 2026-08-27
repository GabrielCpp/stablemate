"""The output-contract block a prompt shows, rendered from the model that parses the reply.

A hand-written `Return Format` section is a second copy of the schema, and the two drift in
the direction that costs the most: the prompt keeps describing the field that was renamed,
the agent returns what the prompt asked for, and the parser rejects it. So the block is
generated — `model_json_schema()` over the model named at the `returns=` of the very turn
being rendered, reached through `roles.turn`, which hands the flow back the same class it
put in the block. Prompt and parser cannot disagree because there is one declaration.

Which puts the field prose in `Field(description=...)`, beside the type it describes. That
is the trade this module asks for: what a prompt used to say about a field in a bullet list
now lives in the schema, is checked to exist by `test_output_contracts.py`, and reaches the
agent inside the contract it has to satisfy rather than several paragraphs above it.

`title` is stripped on the way out. Pydantic derives one for every model and every field
from the Python name, so it restates the key it sits under, for sixty-two fields. So is the
`description` pydantic lifts from a **class** docstring, which is the other half of the same
trade: those docstrings are this codebase's own rationale — which gate reads a field, which
live run the default was wrong for, what a key used to be called — written for the next
maintainer and read by no agent. `Field(description=...)` is where the agent-facing sentence
goes, and per-field descriptions are kept.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

#: What the block says before the schema. Framed as a document to *produce* — an agent
#: shown a bare schema and no verb has been known to echo the schema back.
PREAMBLE = "Produce a JSON document that complies with this schema:"


def schema_block(model: type[BaseModel]) -> str:
    """The rendered output contract for a turn whose reply parses into `model`."""
    schema = _pruned(model.model_json_schema())
    # `ensure_ascii=False`: the descriptions are prose with em dashes and curly quotes in
    # them, and \u2014 escapes are what the agent would be shown otherwise.
    body = json.dumps(schema, indent=2, ensure_ascii=False)
    return f"{PREAMBLE}\n\n```json\n{body}\n```"


def described_fields(schema: dict[str, Any]) -> list[str]:
    """Every `properties` key in `schema`, as `Model.field`, paired with nothing else.

    The guard's half of this module: a rendered contract is only worth having if every key
    in it says what it is for. Returns the *undescribed* ones, so an empty list is a pass.
    """
    missing: list[str] = []
    for owner, body in _models(schema):
        for name, field in body.get("properties", {}).items():
            if not str(field.get("description", "")).strip():
                missing.append(f"{owner}.{name}")
    return missing


def _models(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """The root model and every `$defs` entry, each with the name a reader would use."""
    root = str(schema.get("title") or "root")
    found = [(root, schema)]
    found += [(name, body) for name, body in schema.get("$defs", {}).items()]
    return found


def _pruned(value: Any) -> Any:
    """`value` without the keys a reader of the block has no use for.

    A `description` is dropped only where it sits on an object schema — one with
    `properties`, which is what pydantic builds from a class and fills from its docstring.
    A field's own description sits on the property, which has no `properties` of its own.
    """
    if isinstance(value, dict):
        drop = {"title", "description"} if "properties" in value else {"title"}
        return {k: _pruned(v) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [_pruned(v) for v in value]
    return value


__all__ = ["PREAMBLE", "described_fields", "schema_block"]
