"""`ostler backlog` — the intake list as managed markdown (``docs/backlog.md`` by default).

Bullets are ``- [<id>] <text>`` optionally grouped under ``## <section>`` headings. Replaces the
former bespoke append/prune scripts.
"""

from __future__ import annotations

from pathlib import Path

from ostler import ids, markdown, path as path_mod
from ostler.model import Graph
from ostler.result import Result


def _path(graph: Graph) -> Path:
    """Where this graph keeps its intake list — ``docRoots: backlog:``, and nothing else.

    There is no override. One used to exist, and it let a caller adopt ids into a list
    ``ostler backlog`` and ``doctor`` do not read — a second record of a location the
    config already gives, disagreeing with it.
    """
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


def create(
    graph: Graph,
    text: str,
    section: str = "",
    prefix: str | None = None,
) -> Result:
    """File a backlog item with a generated full id."""
    item_id = ids.allocate(graph, prefix)
    result = add(graph, item_id, text, section)
    return Result(
        result.ok,
        result.message,
        result.paths,
        entity_id=item_id if result.ok else "",
    )


def adopt(graph: Graph, prefix: str | None = None) -> Result:
    """Assign generated ids to every unnamed bullet in an existing backlog."""
    path = _path(graph)
    doc = _read(graph)
    if doc is None:
        return Result(False, f"no backlog at {path}")

    candidates = [bullet for bullet in doc.walk_bullets() if not bullet.bracketed[0]]
    if not candidates:
        return Result(True, "adopted 0 unnamed backlog items", [path])

    lines = doc.body.split("\n")
    for bullet in candidates:
        item_id = ids.allocate(graph, prefix)
        line = lines[bullet.line_start]
        indent = len(line) - len(line.lstrip())
        marker_end = next(
            (offset for offset, char in enumerate(line[indent:]) if char.isspace()),
            len(line) - indent,
        )
        content_start = indent + marker_end
        while content_start < len(line) and line[content_start].isspace():
            content_start += 1
        lines[bullet.line_start] = f"{line[:content_start]}[{item_id}] {line[content_start:]}"
    doc.replace_body(lines)
    _write(path, doc)
    return Result(True, f"adopted {len(candidates)} unnamed backlog items", [path])


def removal_lines(targets: list[markdown.Bullet]) -> set[int]:
    """Body-relative lines removable without discarding an unselected nested item."""
    selected = {bullet.line_start for bullet in targets}
    removable = [
        bullet
        for bullet in targets
        if all(child.line_start in selected for child in list(bullet.walk())[1:])
    ]
    return {
        line
        for bullet in removable
        for line in range(bullet.line_start, bullet.line_end)
    }


def prune(graph: Graph, item_id: str) -> Result:
    doc = _read(graph)
    if doc is None:
        return Result(False, "no backlog.md")
    target = next((b for b in doc.walk_bullets() if b.bracketed[0] == item_id), None)
    if target is None:
        return Result(False, f"no backlog item '{item_id}'")
    drop = removal_lines([target])
    if not drop:
        return Result(
            False,
            f"backlog item '{item_id}' has nested items; prune them first",
        )
    lines = [line for index, line in enumerate(doc.body.split("\n")) if index not in drop]
    doc.replace_body(lines)
    _write(_path(graph), doc)
    return Result(True, f"pruned backlog item '{item_id}'", [_path(graph)])
