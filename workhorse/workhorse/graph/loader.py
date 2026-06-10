from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .nodes import Graph


def load_workflow(path: str | Path) -> Graph:
    p = Path(path)
    raw: dict[str, Any] = yaml.safe_load(p.read_text())

    name = raw.get("name") or p.stem
    nodes_list: list[dict[str, Any]] = raw.get("nodes", [])

    # Build the nodes dict keyed by id before passing to Graph so the
    # discriminated union can resolve each entry by its 'type' field.
    nodes: dict[str, Any] = {n["id"]: n for n in nodes_list}

    try:
        return Graph.model_validate(
            {
                "name": name,
                "start": raw["start"],
                "vars": raw.get("vars") or {},
                "nodes": nodes,
            }
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid workflow '{p}': {exc}") from exc
