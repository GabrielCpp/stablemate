from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from workhorse.graph.nodes import Graph


def _shape_graph(raw: dict[str, Any], default_name: str) -> dict[str, Any]:
    """Shape one graph's raw YAML into the dict Graph.model_validate expects.

    Recurses into ``flows:`` so each named sub-graph is shaped the same way (its
    ``nodes`` list keyed by id, its own ``flows`` recursed). The flow's key is its
    default name."""
    nodes_list: list[dict[str, Any]] = raw.get("nodes", [])
    # Build the nodes dict keyed by id before passing to Graph so the
    # discriminated union can resolve each entry by its 'type' field.
    nodes: dict[str, Any] = {n["id"]: n for n in nodes_list}
    flows_raw: dict[str, Any] = raw.get("flows") or {}
    flows = {fname: _shape_graph(fraw, fname) for fname, fraw in flows_raw.items()}
    # Every key Graph accepts must be shaped here explicitly -- this dict is the whole
    # input to model_validate, so a key omitted below is silently dropped rather than
    # rejected. (`env` was, until requires: landed and needed the same wiring.)
    return {
        "name": raw.get("name") or default_name,
        "start": raw["start"],
        "vars": raw.get("vars") or {},
        "env": raw.get("env") or {},
        "requires": raw.get("requires") or [],
        "nodes": nodes,
        "flows": flows,
    }


def load_workflow(path: str | Path) -> Graph:
    p = Path(path)
    raw: dict[str, Any] = yaml.safe_load(p.read_text())

    try:
        return Graph.model_validate(_shape_graph(raw, p.stem))
    except ValidationError as exc:
        raise ValueError(f"Invalid workflow '{p}': {exc}") from exc
