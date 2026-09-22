"""Which book pages a service's `entries` page reaches by links, and which it leaves dead."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from ostler import links as links_mod
from ostler.model import Graph, read_links

ENTRIES_TYPE = "entries"


@dataclass(frozen=True)
class DeadPage:
    path: Path
    rel: str
    service: str
    entries_pages: tuple[str, ...]


@dataclass(frozen=True)
class BookPages:
    all_pages: frozenset[Path]
    entries_pages: tuple[Path, ...]


def _service_of(graph: Graph, page: Path) -> str:
    parts = page.relative_to(graph.doc_roots["features"].resolve()).parts
    return parts[0] if len(parts) > 1 else ""


def _book_pages(graph: Graph) -> BookPages:
    all_pages = frozenset(record.path.resolve() for record in graph.features)
    entries_pages = tuple(sorted(
        node.path.resolve() for node in graph.ui_nodes_of_type(ENTRIES_TYPE) if node.kind == "file"))
    return BookPages(all_pages=all_pages, entries_pages=entries_pages)


def _linked_pages(page: Path, all_pages: frozenset[Path]) -> set[Path]:
    targets: set[Path] = set()
    for _text, href, _line in read_links(page):
        if not links_mod.is_doc_link(href):
            continue
        path_part = href.strip().split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        target = (page.parent / path_part).resolve()
        if target in all_pages:
            targets.add(target)
    return targets


def reachable_pages(start: tuple[Path, ...], all_pages: frozenset[Path]) -> set[Path]:
    seen = set(start)
    queue = deque(start)
    while queue:
        for target in _linked_pages(queue.popleft(), all_pages) - seen:
            seen.add(target)
            queue.append(target)
    return seen


def dead_pages(graph: Graph) -> list[DeadPage]:
    """Every page in a service that has an `entries` page, which no link path from one reaches.

    A service with no `entries` page has no root yet, so none of its pages is judged.
    """
    book = _book_pages(graph)
    root = graph.root.resolve()
    entries_by_service: dict[str, list[str]] = {}
    for entries in book.entries_pages:
        entries_by_service.setdefault(_service_of(graph, entries), []).append(
            entries.relative_to(root).as_posix())
    reached = reachable_pages(book.entries_pages, book.all_pages)
    dead: list[DeadPage] = []
    for page in sorted(book.all_pages - reached):
        service = _service_of(graph, page)
        if service in entries_by_service:
            dead.append(DeadPage(path=page, rel=page.relative_to(root).as_posix(), service=service,
                                 entries_pages=tuple(entries_by_service[service])))
    return dead


def delete_pages(pages: list[DeadPage]) -> None:
    for page in pages:
        page.path.unlink()
