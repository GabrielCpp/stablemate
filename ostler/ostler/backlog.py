"""`ostler backlog` — the intake list as managed markdown (``docs/backlog.md``).

Bullets are ``- [<id>] <text>`` optionally grouped under ``## <section>`` headings. Replaces the
former bespoke append/prune scripts.
"""

from __future__ import annotations

from pathlib import Path

from ostler import markdown, path as path_mod
from ostler.model import Graph
from ostler.result import Result


def _path(graph: Graph) -> Path:
    return path_mod.backlog_path(graph)


def _read(graph: Graph) -> markdown.MarkdownDoc | None:
    p = _path(graph)
    return markdown.split(p.read_text(encoding="utf-8")) if p.exists() else None


def _write(p: Path, doc: markdown.MarkdownDoc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.render().rstrip("\n") + "\n", encoding="utf-8")


def items(graph: Graph) -> list[tuple[str, str]]:
    """(id, text) pairs across all sections, in file order."""
    doc = _read(graph)
    if doc is None:
        return []
    return [(ident, text) for ident, text in
            (b.bracketed for b in doc.walk_bullets()) if ident]


def add(graph: Graph, item_id: str, text: str, section: str = "") -> Result:
    p = _path(graph)
    if item_id in {i for i, _ in items(graph)}:
        return Result(False, f"backlog item '{item_id}' already exists")
    doc = _read(graph) or markdown.split("# Backlog\n")
    lines = doc.body.split("\n")
    bullet = f"- [{item_id}] {text}".rstrip()
    if section:
        # The section's parsed span already ends where the next heading begins, which is
        # exactly where a new item belongs — no scan for the next `## ` line.
        found = doc.find_section(section)
        if found is not None:
            lines.insert(min(found.line_end, len(lines)), bullet)
        else:
            lines += ["", f"## {section}", bullet]
    else:
        lines.append(bullet)
    doc.replace_body(lines)
    _write(p, doc)
    return Result(True, f"filed backlog item '{item_id}'", [p])


def prune(graph: Graph, item_id: str) -> Result:
    doc = _read(graph)
    if doc is None:
        return Result(False, "no backlog.md")
    target = next((b for b in doc.walk_bullets() if b.bracketed[0] == item_id), None)
    if target is None:
        return Result(False, f"no backlog item '{item_id}'")
    lines = doc.body.split("\n")
    # The bullet's span covers its nested continuation lines too, so an item with
    # sub-bullets leaves none of them orphaned behind.
    del lines[target.line_start:target.line_end]
    doc.replace_body(lines)
    _write(_path(graph), doc)
    return Result(True, f"pruned backlog item '{item_id}'", [_path(graph)])
