"""`ostler explain` — what a resource page says, what borrows it, and which claims depend on it."""

from __future__ import annotations

import re
from pathlib import Path

from ostler.model import Graph, UINode
from ostler.qa import book_fixtures


def _resource(graph: Graph, name: str) -> UINode | None:
    for node in graph.ui_nodes_of_type("resource"):
        if Path(node.id).stem == name or node.id == name or node.path.as_posix().endswith(name):
            return node
    return None


def _values(node: UINode, key: str) -> list[str]:
    value = node.meta.get(key)
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _needing(graph: Graph, borrowers: dict[str, list[str]]) -> dict[str, str]:
    """Every fixture that builds on a borrower through `needs:`, mapped to the borrower it reaches."""
    reached = {stem: stem for stem in borrowers}
    needs = {stem: [n["fixture"] for n in row["needs"] if n.get("fixture")]
             for stem, row in book_fixtures.resolved(graph).items()}
    grew = True
    while grew:
        grew = False
        for stem, wanted in needs.items():
            if stem in reached:
                continue
            hit = next((reached[w] for w in wanted if w in reached), None)
            if hit is not None:
                reached[stem] = hit
                grew = True
    return reached


def run(graph: Graph, name: str) -> str | None:
    """The explanation of resource *name*, or `None` when the book holds no such resource."""
    page = _resource(graph, name)
    if page is None:
        return None
    stem = Path(page.id).stem
    spec = book_fixtures.resolved_resources(graph)[stem]
    out = [page.path.read_text(encoding="utf-8").rstrip(), ""]
    probe = spec["probe"]
    if probe and probe.get("request"):
        request = probe["request"]
        out.append(f"probe: {request['method']} {request['path']} on {spec['base']}")
    elif probe:
        out.append(f"probe: {probe.get('command', '')} (binary {spec['binary']})")
    out.extend(["", "## Observations", ""])
    for observation, step in spec["observations"].items():
        request = step.get("request")
        what = f"{request['method']} {request['path']}" if request else str(step.get("command", ""))
        out.append(f"{observation}: {what}")

    borrowers: dict[str, list[str]] = {}
    for fixture, row in book_fixtures.resolved(graph).items():
        steps = [f"{s['kind']} {s['id']}" for s in row["steps"] if s.get("on") == stem]
        if steps:
            borrowers[fixture] = steps
    out.extend(["", "## Borrowed by", ""])
    out.extend(f"{fixture}: {', '.join(steps)}" for fixture, steps in borrowers.items())
    if not borrowers:
        out.append("no fixture borrows from it")

    reached = _needing(graph, borrowers)
    groups: dict[str, list[str]] = {}
    for node in graph.ui_nodes:
        for value in _values(node, "fixture"):
            for fixture, borrower in reached.items():
                if re.search(rf"(?<![\w-]){re.escape(fixture)}(?![\w-])", value):
                    groups.setdefault(f"fixture {borrower}", []).append(node.id)
        for value in _values(node, "observe"):
            if value.strip().startswith(f"@{stem}."):
                groups.setdefault(f"observe {value.strip()}", []).append(node.id)
    out.extend(["", "## Claims", ""])
    for label, ids in groups.items():
        out.append(f"{label}:")
        out.extend(f"  {claim}" for claim in dict.fromkeys(ids))
    if not groups:
        out.append("no claim reads it")
    return "\n".join(out)
