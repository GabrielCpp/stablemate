"""The output-contract block a prompt shows, rendered from the model that parses the reply."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

PREAMBLE = "Produce a JSON document that complies with this schema:"


def schema_block(model: type[BaseModel]) -> str:
    """The rendered output contract for a turn whose reply parses into `model`."""
    schema = _pruned(model.model_json_schema())
    body = json.dumps(schema, indent=2, ensure_ascii=False)
    return f"{PREAMBLE}\n\n```json\n{body}\n```"


def described_fields(schema: dict[str, Any]) -> list[str]:
    """Every `properties` key in `schema`, as `Model.field`, paired with nothing else."""
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
    """`value` without the keys a reader of the block has no use for."""
    if isinstance(value, dict):
        drop = {"title", "description"} if "properties" in value else {"title"}
        return {k: _pruned(v) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [_pruned(v) for v in value]
    return value


__all__ = ["PREAMBLE", "described_fields", "schema_block"]
