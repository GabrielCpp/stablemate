"""A service's production file set: what its entry points reach, and what brings its stack up."""
from __future__ import annotations

from pathlib import Path

from ostler.refs import is_test_source
from workhorse_workflows.okf_book.shared.citations import page_citations
from workhorse_workflows.okf_book.shared.entries import book_dir, read_entries
from workhorse_workflows.okf_book.shared.imports import reached_files
from workhorse_workflows.okf_book.shared.stack import stack_files


def entry_pages(root: Path, service: str) -> tuple[Path, ...]:
    """The pages the service's entries links land on, once each, in link order."""
    folder = book_dir(root, service)
    pages = dict.fromkeys(folder / link.page for link in read_entries(root, service))
    return tuple(page for page in pages if page.is_file())


def walk_roots(root: Path, service: str) -> frozenset[str]:
    """The existing production files the entry pages cite: where the import walk starts."""
    return frozenset(
        citation.path
        for page in entry_pages(root, service)
        for citation in page_citations(page)
        if (root / citation.path).is_file() and not is_test_source(citation.path)
    )


def production_files(root: Path, service: str) -> frozenset[str]:
    """Every file reached from the service's entry points, with the files that build and start its stack."""
    reached = frozenset(reached_files(root, sorted(walk_roots(root, service))))
    return reached | stack_files(root, service, reached)
