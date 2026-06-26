"""`ostler backlog` — the intake list as managed markdown (``docs/backlog.md``).

Bullets are ``- [<id>] <text>`` optionally grouped under ``## <section>`` headings. Replaces the
former bespoke append/prune scripts.
"""

from __future__ import annotations

import re
from pathlib import Path

from .crud import Result
from .model import Graph

_ITEM = re.compile(r"^\s*[-*]\s+\[(?P<id>[^\]]+)\]\s*(?P<text>.*)$")


def _path(graph: Graph) -> Path:
    return graph.root / "docs" / "backlog.md"


def items(graph: Graph) -> list[tuple[str, str]]:
    """(id, text) pairs across all sections, in file order."""
    p = _path(graph)
    if not p.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _ITEM.match(line)
        if m:
            out.append((m.group("id").strip(), m.group("text").strip()))
    return out


def add(graph: Graph, item_id: str, text: str, section: str = "") -> Result:
    p = _path(graph)
    existing = {i for i, _ in items(graph)}
    if item_id in existing:
        return Result(False, f"backlog item '{item_id}' already exists")
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else ["# Backlog", ""]
    bullet = f"- [{item_id}] {text}".rstrip()
    if section:
        heading = f"## {section}"
        if heading in lines:
            idx = lines.index(heading)
            insert_at = idx + 1
            while insert_at < len(lines) and not lines[insert_at].startswith("## "):
                insert_at += 1
            lines.insert(insert_at, bullet)
        else:
            lines += ["", heading, bullet]
    else:
        lines.append(bullet)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Result(True, f"filed backlog item '{item_id}'", [p])


def prune(graph: Graph, item_id: str) -> Result:
    p = _path(graph)
    if not p.exists():
        return Result(False, "no backlog.md")
    kept, removed = [], False
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _ITEM.match(line)
        if m and m.group("id").strip() == item_id:
            removed = True
            continue
        kept.append(line)
    if not removed:
        return Result(False, f"no backlog item '{item_id}'")
    p.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return Result(True, f"pruned backlog item '{item_id}'", [p])
