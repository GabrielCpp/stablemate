"""`ostler todo` — the epics queue as markdown (``docs/epics/index.md``, the OKF bundle index).

Replaces the former ``epics-todo.json``. The list order *is* the work order. Each line is
``- [<name>](<name>/epic.md) — <title>``; ostler reads the epic name from the link/bracket.
"""

from __future__ import annotations

import re
from pathlib import Path

from ostler.crud import Result
from ostler.model import Graph

_LINE = re.compile(r"^\s*[-*]\s+(?:\[)?([A-Za-z0-9][\w-]*)")


def _index_path(graph: Graph) -> Path:
    return graph.doc_roots["epics"] / "index.md"


def list_epics(graph: Graph) -> list[str]:
    """Ordered epic names from index.md; empty list if the index does not exist."""
    p = _index_path(graph)
    if not p.exists():
        return []
    names: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(line)
        if m:
            names.append(m.group(1))
    return names


def _title_of(graph: Graph, name: str) -> str:
    edir = graph.doc_roots["epics"] / name / "epic.md"
    if edir.exists():
        from ostler import markdown
        fm = markdown.split(edir.read_text(encoding="utf-8")).frontmatter or {}
        return str(fm.get("title") or name)
    return name


def _render(graph: Graph, names: list[str]) -> str:
    lines = ["# Epics", "",
             "The ordered work queue for this repo (the OKF index of the epics bundle).", ""]
    for n in names:
        lines.append(f"- [{n}]({n}/epic.md) — {_title_of(graph, n)}")
    return "\n".join(lines) + "\n"


def _write(graph: Graph, names: list[str]) -> Path:
    p = _index_path(graph)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_render(graph, names), encoding="utf-8")
    return p


def add(graph: Graph, name: str, *, front: bool = False) -> Result:
    names = list_epics(graph)
    if name in names:
        return Result(False, f"epic '{name}' already in the queue")
    names.insert(0, name) if front else names.append(name)
    return Result(True, f"queued epic '{name}'", [_write(graph, names)])


def prune(graph: Graph, name: str) -> Result:
    names = list_epics(graph)
    if name not in names:
        return Result(False, f"epic '{name}' not in the queue")
    names = [n for n in names if n != name]
    return Result(True, f"pruned epic '{name}' from the queue", [_write(graph, names)])


def reorder(graph: Graph, order: list[str]) -> Result:
    current = set(list_epics(graph))
    unknown = [n for n in order if n not in current]
    if unknown:
        return Result(False, f"not in queue: {', '.join(unknown)}")
    tail = [n for n in list_epics(graph) if n not in order]
    return Result(True, "reordered epics queue", [_write(graph, order + tail)])
