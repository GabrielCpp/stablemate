"""Id allocation — ostler owns ``.agents/ids.json`` (subsumes the workflow's allocate-ids script).

The registry is ``{prefix, counter, frozen}``. ``allocate`` mints the next ``<prefix>-<n>`` id and
persists the bumped counter. ``ensure`` creates the registry on first use. The prefix is managed
entirely by ostler: it is tied to the repo in the CWD — the first 4 letters of the repo name,
uppercased (an explicit override may still be passed programmatically). The registry pins the
prefix once minted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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


def _repo_prefix(graph: Graph) -> str:
    """Derived id prefix: the first 4 letters of the CWD repo's name, uppercased."""
    letters = re.sub(r"[^A-Za-z0-9]", "", graph.root.name)
    return (letters[:4] or "REPO").upper()


def ensure(graph: Graph, prefix: str | None = None) -> dict:
    """Return the registry, creating it if absent (prefix derived from the repo name)."""
    ids = load(graph)
    if ids is not None:
        return ids
    ids = {"prefix": prefix or _repo_prefix(graph), "counter": 1}
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
