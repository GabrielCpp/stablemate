"""`ostler todo` — the epics queue as markdown (``docs/epics/index.md``, the OKF bundle index).

Replaces the former ``epics-todo.json``. The list order *is* the work order. Each line is
``- [<name>](<name>/epic.md) — <title>``; ostler reads the epic name from the link/bracket.
"""

from __future__ import annotations

import re
from pathlib import Path

from ostler import markdown, path as path_mod, registry
from ostler.result import Result
from ostler.model import Graph

#: An epic name is an identifier, not markdown — the leading run of one is what a
#: hand-edited entry that dropped the link still yields a usable name from.
_NAME = re.compile(r"\A[A-Za-z0-9][\w-]*")


def _queued_as(names: list[str], name: str) -> str | None:
    """The queue entry naming the same epic as *name*, or None.

    Epic directories are numbered (`0001-checkout-flow`) but the queue is edited by hand
    and by prompts that know only the slug, so the two spellings have to meet somewhere.
    They meet here: the exact line wins, then the one with the same slug.
    """
    if name in names:
        return name
    slug = registry.epic_slug(name)
    return next((n for n in names if registry.epic_slug(n) == slug), None)


def _index_path(graph: Graph) -> Path:
    return path_mod.epics_index(graph)


def list_epics(graph: Graph) -> list[str]:
    """Ordered epic names from index.md, falling back to milestone order.

    Each entry is ``- [<name>](<name>/epic.md) — <title>``, so the name is the bullet's
    bracket. Reading it off the parsed list rather than a line regex is what keeps a
    fenced example of the format out of the work queue.

    index.md is a compatibility view, not a required authoring artifact — a fresh
    milestone-based repo may never write one, since milestones are the durable
    sequencing model there. Without this fallback such a repo's queue reads as
    permanently empty (indistinguishable from "everything is merged") rather than
    "nothing has been queued yet". The fallback is read-only: it does not write
    index.md itself, so `add`/`prune`/`reorder` still materialize it lazily, from
    this same order, the first time one of them writes.
    """
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
    # Queue the directory that exists, not the name that was typed: the index's job is to
    # point at epic docs, and `[checkout-flow](checkout-flow/epic.md)` points at nothing
    # once the directory is `0001-checkout-flow`. An epic queued ahead of its doc keeps the
    # name as given — there is no directory to name yet.
    name = path_mod.epic_dir(graph, name).name
    names.insert(0, name) if front else names.append(name)
    # Warn — never fail — on an epic with no epic.md: selection silently skips such a name
    # and then reports "every epic is fully authored", which is a no-work run indistinguishable
    # from success. Queueing ahead of the epic doc is legitimate, so this stays advisory.
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
