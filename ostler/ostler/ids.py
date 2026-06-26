"""Id allocation — ostler owns ``.agents/ids.json`` (subsumes the workflow's allocate-ids script).

The registry is ``{prefix, counter, frozen}``. ``allocate`` mints the next ``<prefix>-<n>`` id and
persists the bumped counter. ``ensure`` creates the registry on first use (prefix from config's
``id_prefix`` / ``template.id_prefix`` or an explicit override).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .model import Graph


def path_for(graph: Graph) -> Path:
    return graph.root / ".agents" / "ids.json"


def load(graph: Graph) -> dict | None:
    if graph.ids is not None:
        return dict(graph.ids)
    p = path_for(graph)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def save(graph: Graph, ids: dict) -> None:
    p = path_for(graph)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    graph.ids = ids


def _config_prefix(graph: Graph) -> str | None:
    """Best-effort id prefix from agents.yml (``template.id_prefix`` or ``repo.prefix``)."""
    for name in ("agents.yml", ".agents.yml", "ostler.yml", "ostler.yaml"):
        p = graph.root / name
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        tmpl = data.get("template") or {}
        repo = data.get("repo") or {}
        for cand in (tmpl.get("id_prefix"), repo.get("prefix"), (data.get("organization") or {}).get("prefix")):
            if cand:
                return str(cand)
    return None


def ensure(graph: Graph, prefix: str | None = None) -> dict:
    """Return the registry, creating it if absent. A prefix is required to mint one."""
    ids = load(graph)
    if ids is not None:
        return ids
    pfx = prefix or _config_prefix(graph) or graph.org_name
    ids = {"prefix": pfx, "counter": 1}
    save(graph, ids)
    return ids


def allocate(graph: Graph, prefix: str | None = None) -> str:
    """Mint and persist the next ``<prefix>-<n>`` id."""
    ids = ensure(graph, prefix)
    n = int(ids.get("counter", 1))
    ids["counter"] = n + 1
    new_id = f"{ids['prefix']}-{n}"
    save(graph, ids)
    return new_id
