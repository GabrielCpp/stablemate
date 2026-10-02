"""The shape code gives a book after each turn, so no page grows past what one writer can hold.

A server page that holds an endpoint inline, as a `### <id>` under its `## Endpoints`, grows with
each endpoint. Code moves every such endpoint onto a page of its own beside the server and rewrites
each link the move touches, wherever it sits. A carve that would touch a page someone left
uncommitted is not made, and doctor goes on reporting the endpoint to the writer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ostler.carve import carve_endpoints
from ostler.model import load
from workhorse_workflows.okf_book.shared.entries import book_dir


@dataclass(frozen=True, slots=True)
class Carve:
    """One server page's carve: the repo-relative pages it wrote, or why it was not made."""

    server: str
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


def carve_inline_endpoints(root: Path, service: str, uncommitted: frozenset[str] = frozenset()) -> tuple[Carve, ...]:
    """Move each endpoint a server page of the service's book holds inline onto a page of its own, leaving the pages in *uncommitted* as they are."""
    resolved = root.resolve()
    carves: list[Carve] = []
    for server in _inline_servers(root, service):
        rel = server.relative_to(resolved).as_posix()
        plan = carve_endpoints(load(root), rel)
        pages = tuple(sorted(change.path.resolve().relative_to(resolved).as_posix() for change in plan.changes))
        held = sorted(set(pages) & uncommitted)
        if plan.error:
            carves.append(Carve(rel, refusal=plan.error))
        elif held:
            carves.append(Carve(rel, refusal=f"it would change pages someone left uncommitted: {', '.join(held)}"))
        else:
            plan.apply()
            carves.append(Carve(rel, pages))
    return tuple(carves)


def carved_pages(carves: tuple[Carve, ...]) -> tuple[str, ...]:
    """Every page the carves wrote, once each."""
    return tuple(sorted({page for carve in carves for page in carve.pages}))
