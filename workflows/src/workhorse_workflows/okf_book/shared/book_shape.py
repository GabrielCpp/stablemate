"""The shape code gives a book after each turn, so no page grows past what one writer can hold.

A server page that holds an endpoint inline, as a `### <id>` under its `## Endpoints`, grows with
each endpoint. Code moves every such endpoint onto a page of its own beside the server and rewrites
each link the move touches, wherever it sits. A page past the size limit has its largest sections'
subsections moved onto fragment pages beside it the same way. A carve that would touch a page
someone left uncommitted is not made, and doctor goes on reporting the page to the writer.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ostler import registry
from ostler.carve import CarvePlan, carve_endpoints
from ostler.fragment_carve import carve_fragments
from ostler.model import Graph, load
from ostler.page_size import PAGE_SIZE_LIMIT
from ostler.pages import files_in_book
from workhorse_workflows.okf_book.shared.entries import book_dir


@dataclass(frozen=True, slots=True)
class Carve:
    """One page's carve: the repo-relative pages it wrote, or why it was not made."""

    page: str
    pages: tuple[str, ...] = ()
    refusal: str = ""


def _inline_servers(root: Path, service: str) -> list[Path]:
    folder = book_dir(root, service).resolve()
    servers = {
        node.path.resolve()
        for node in load(root).ui_nodes_of_type("endpoint")
        if node.kind != "file" and node.path.resolve().is_relative_to(folder)
    }
    return sorted(servers)


def _oversized(root: Path, service: str) -> list[Path]:
    folder = book_dir(root, service).resolve()
    if not folder.is_dir():
        return []
    return [p.resolve() for p in files_in_book(folder)
            if p.name not in registry.RESERVED_FILES and p.stat().st_size > PAGE_SIZE_LIMIT]


def _carve(root: Path, pages: list[Path], carve: Callable[[Graph, str], CarvePlan],
           uncommitted: frozenset[str]) -> list[Carve]:
    resolved = root.resolve()
    carves: list[Carve] = []
    for page in pages:
        rel = page.relative_to(resolved).as_posix()
        plan = carve(load(root), rel)
        written = tuple(sorted(change.path.resolve().relative_to(resolved).as_posix() for change in plan.changes))
        held = sorted(set(written) & uncommitted)
        if plan.error:
            carves.append(Carve(rel, refusal=plan.error))
        elif held:
            carves.append(Carve(rel, refusal=f"it would change pages someone left uncommitted: {', '.join(held)}"))
        elif written:
            plan.apply()
            carves.append(Carve(rel, written))
    return carves


def carve_inline_endpoints(root: Path, service: str, uncommitted: frozenset[str] = frozenset()) -> tuple[Carve, ...]:
    """Move each endpoint a server page of the service's book holds inline onto a page of its own, leaving the pages in *uncommitted* as they are."""
    return tuple(_carve(root, _inline_servers(root, service), carve_endpoints, uncommitted))


def carve_oversized_pages(root: Path, service: str, uncommitted: frozenset[str] = frozenset()) -> tuple[Carve, ...]:
    """Move the largest sections' subsections of each page past the size limit in the service's book onto fragment pages, leaving the pages in *uncommitted* as they are."""
    return tuple(_carve(root, _oversized(root, service), carve_fragments, uncommitted))


def shape_book(root: Path, service: str, uncommitted: frozenset[str] = frozenset()) -> tuple[Carve, ...]:
    """Carve the endpoints the service's book holds inline, then the pages still past the size limit."""
    return carve_inline_endpoints(root, service, uncommitted) + carve_oversized_pages(root, service, uncommitted)


def carved_pages(carves: tuple[Carve, ...]) -> tuple[str, ...]:
    """Every page the carves wrote, once each."""
    return tuple(sorted({page for carve in carves for page in carve.pages}))
