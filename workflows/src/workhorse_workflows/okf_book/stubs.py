"""Stub pages for a surface's entry points, scaffolded by ostler before any repair turn runs."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ostler import markdown, registry
from ostler.api import Ostler
from ostler.model import Graph
from ostler.scaffold import scaffold
from workhorse_workflows.okf_book.entries import EntryLink, book_dir
from workhorse_workflows.okf_book.surface import EntryPoint, Surface, SurfaceKind

_SURFACE_TYPE = {SurfaceKind.CLI: "cli", SurfaceKind.HTTP: "server"}
_SECTION_TYPE = {SurfaceKind.CLI: "command", SurfaceKind.HTTP: "endpoint"}
_SCREEN = "screen"
_EMPTY_CODE = "- code:\n"


class StubError(RuntimeError):
    """ostler refused to scaffold a page the book needs and does not have."""


def file_page(root: Path, type_name: str, service: str, name: str) -> Path:
    """Where ostler places a file-level page of `type_name`."""
    uitype = registry.ui_type(type_name)
    context = uitype.context if uitype is not None else ""
    folder = book_dir(root, service) / context if context else book_dir(root, service)
    return folder / f"{name}.md"


def _ensure_file(graph: Graph, type_name: str, surface: Surface, name: str, title: str) -> Path:
    path = file_page(graph.root, type_name, surface.service, name)
    if not path.is_file():
        result = scaffold(graph, type_name, name, service=surface.service, title=title)
        if not result.ok:
            raise StubError(result.message)
    _cite_entry(path, surface.entry)
    return path


def _cite_entry(page: Path, entry: str) -> None:
    """Fill the page's own empty `code:` bullet with the entry, leaving its sections' bullets alone."""
    text = page.read_text(encoding="utf-8")
    cut = text.find("\n## ") + 1 or len(text)
    intro = text[:cut]
    if _EMPTY_CODE in intro:
        _ = page.write_text(intro.replace(_EMPTY_CODE, f"- code: {entry}\n", 1) + text[cut:], encoding="utf-8")


def _has_section(page: Path, type_name: str, slug: str) -> bool:
    uitype = registry.ui_type(type_name)
    if uitype is None or not uitype.heading:
        return False
    section = markdown.split(page.read_text(encoding="utf-8")).find_section(uitype.heading)
    return section is not None and any(child.title.strip() == slug for child in section.children)


def _ensure_section(graph: Graph, type_name: str, page: Path, slug: str) -> None:
    if _has_section(page, type_name, slug):
        return
    result = scaffold(graph, type_name, slug, in_file=str(page))
    if not result.ok:
        raise StubError(result.message)


def _link(root: Path, service: str, page: Path, title: str, anchor: str = "") -> EntryLink:
    target = page.relative_to(book_dir(root, service)).as_posix()
    return EntryLink(title, f"{target}#{anchor}" if anchor else target)


def write_stubs(root: Path, surface: Surface, entry_points: Iterable[EntryPoint]) -> tuple[EntryLink, ...]:
    """Scaffold whatever page each entry point lacks, and return the entries links to them."""
    graph = Ostler(root, use_index=False).graph
    if surface.kind in _SURFACE_TYPE:
        page = _ensure_file(graph, _SURFACE_TYPE[surface.kind], surface, surface.service, surface.service)
        links: list[EntryLink] = []
        for point in entry_points:
            _ensure_section(graph, _SECTION_TYPE[surface.kind], page, point.slug)
            links.append(_link(root, surface.service, page, point.title, point.slug))
        return tuple(links)
    return tuple(
        _link(root, surface.service, _ensure_file(graph, _SCREEN, surface, point.slug, point.title), point.title)
        for point in entry_points
    )
