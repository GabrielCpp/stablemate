"""The entries page code writes for a book that has none: a link to each cli page, each server page, and each screen no other screen links to."""
from __future__ import annotations

from pathlib import Path

from ostler import links as links_mod
from ostler.model import Graph, UINode, load, read_links
from workhorse_workflows.okf_book.shared.entries import ENTRIES_NAME, EntryLink, book_dir, entries_path

ENTRY_TYPES = ("cli", "server")
SCREEN_TYPE = "screen"
FILE_KIND = "file"
NO_ENTRY_PAGE = (
    "the book has pages but no cli, server or screen page for its entries page to link, so nothing reaches them "
    + "and no repair turn can change that; and"
)


def _book_nodes(graph: Graph, book: Path, type_name: str) -> list[UINode]:
    return sorted(
        (node for node in graph.ui_nodes_of_type(type_name) if node.kind == FILE_KIND and node.path.resolve().is_relative_to(book)),
        key=lambda node: node.path.resolve(),
    )


def _linked_pages(page: Path) -> set[Path]:
    return {
        (page.parent / href.split("#", 1)[0]).resolve()
        for _text, href, _line in read_links(page)
        if links_mod.is_doc_link(href) and href.split("#", 1)[0]
    }


def entry_links(root: Path, service: str) -> tuple[EntryLink, ...]:
    """One link per entry page of the service's book: each cli and server page, then each screen no other screen links to."""
    book = book_dir(root, service).resolve()
    graph = load(root)
    screens = _book_nodes(graph, book, SCREEN_TYPE)
    linked = {target for screen in screens for target in _linked_pages(screen.path) - {screen.path.resolve()}}
    pages = [
        *(node for type_name in ENTRY_TYPES for node in _book_nodes(graph, book, type_name)),
        *(screen for screen in screens if screen.path.resolve() not in linked),
    ]
    return tuple(
        EntryLink(node.title or node.path.stem, node.path.resolve().relative_to(book).as_posix()) for node in pages
    )


def render_entries(service: str, links: tuple[EntryLink, ...]) -> str:
    """The entries page's text."""
    header = ["---", "type: entries", f"slug: {Path(ENTRIES_NAME).stem}", f"title: {service}", "---", "", f"# {service}", ""]
    return "\n".join([*header, *(link.render() for link in links)]) + "\n"


def write_root_entries(root: Path, service: str) -> str:
    """Write the service's entries page, and return its repo-relative path."""
    path = entries_path(root, service)
    _ = path.write_text(render_entries(service, entry_links(root, service)), encoding="utf-8")
    return path.relative_to(root).as_posix()
