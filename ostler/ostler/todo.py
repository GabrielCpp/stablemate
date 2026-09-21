"""`ostler todo` — the epics queue as markdown (``docs/epics/index.md``, the OKF bundle index)."""

from __future__ import annotations

import re
from pathlib import Path

from ostler import markdown, path as path_mod, registry
from ostler.result import Result
from ostler.model import Graph

_NAME = re.compile(r"\A[A-Za-z0-9][\w-]*")


def _queued_as(names: list[str], name: str) -> str | None:
    """The queue entry naming the same epic as *name*, or None."""
    if name in names:
        return name
    slug = registry.epic_slug(name)
    return next((n for n in names if registry.epic_slug(n) == slug), None)


def _index_path(graph: Graph) -> Path:
    return path_mod.epics_index(graph)


def list_epics(graph: Graph) -> list[str]:
    """Ordered epic names from index.md, falling back to milestone order."""
    p = _index_path(graph)
    if not p.exists():
        return _milestone_ordered_epics(graph)
    doc = markdown.split(p.read_text(encoding="utf-8"))
    names: list[str] = []
    for bullet in doc.walk_bullets():
        ident, _rest = bullet.bracketed
        if match := _NAME.match(ident or bullet.text):
            names.append(match.group(0))
    return names


def _milestone_ordered_epics(graph: Graph) -> list[str]:
    """Epics in milestone order, deduped — the fallback source when index.md is absent."""
    ordered: list[str] = []
    seen: set[str] = set()
    for milestone in graph.milestones:
        for epic in milestone.epics:
            slug = str(epic).strip()
            if slug and slug not in seen:
                ordered.append(slug)
                seen.add(slug)
    return ordered


def _title_of(graph: Graph, name: str) -> str:
    epic_md = path_mod.epic_dir(graph, name) / "epic.md"
    if epic_md.exists():
        fm = markdown.split(epic_md.read_text(encoding="utf-8")).frontmatter or {}
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
    queued = _queued_as(names, name)
    if queued is not None:
        return Result(False, f"epic '{queued}' already in the queue")
    name = path_mod.epic_dir(graph, name).name
    names.insert(0, name) if front else names.append(name)
    msg = f"queued epic '{name}'"
    if not (graph.doc_roots["epics"] / name / "epic.md").exists():
        msg += (f" — WARNING: no '{name}/epic.md' yet, so epic selection will skip it "
                f"and report no work remaining")
    return Result(True, msg, [_write(graph, names)])


def prune(graph: Graph, name: str) -> Result:
    names = list_epics(graph)
    queued = _queued_as(names, name)
    if queued is None:
        return Result(False, f"epic '{name}' not in the queue")
    names = [n for n in names if n != queued]
    return Result(True, f"pruned epic '{queued}' from the queue", [_write(graph, names)])


def reorder(graph: Graph, order: list[str]) -> Result:
    current = list_epics(graph)
    resolved = [(n, _queued_as(current, n)) for n in order]
    unknown = [n for n, q in resolved if q is None]
    if unknown:
        return Result(False, f"not in queue: {', '.join(unknown)}")
    front = [q for _, q in resolved if q is not None]
    tail = [n for n in current if n not in front]
    return Result(True, "reordered epics queue", [_write(graph, front + tail)])
