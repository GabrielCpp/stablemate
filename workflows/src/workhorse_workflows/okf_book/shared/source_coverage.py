"""The product source a book leaves uncited: each file of the surface's source folder that no page's `code:` cites.

A book covers its app when every product file is cited by the page that documents what it does
for a user or a caller. Tests, test doubles, fixtures and a test runner's setup are no product. A
type declaration file and a build tool's config state nothing a user or a caller meets, so neither
needs a page.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from ostler.coverage import citations
from ostler.inventory import SOURCE_SUFFIXES
from ostler.model import Graph
from ostler.refs import is_test_source, parse_code_ref
from workhorse_workflows.kit import list_tracked_files

UNCITED_CODE = "uncited-source"
SAMPLE_FILES = 5
DECLARATION_SUFFIX = ".d.ts"
CONFIG_MARK = ".config."


def product_files(root: Path, source_folder: str) -> tuple[str, ...]:
    """Every tracked product source file under `source_folder`, repo-relative."""
    return tuple(
        path
        for path in list_tracked_files(root, source_folder)
        if PurePosixPath(path).suffix in SOURCE_SUFFIXES
        and not is_test_source(path)
        and not path.endswith(DECLARATION_SUFFIX)
        and CONFIG_MARK not in PurePosixPath(path).name
    )


def cited_paths(book: Graph, service: str) -> frozenset[str]:
    """The repo-relative files the service's pages cite, without their symbols."""
    paths: set[str] = set()
    for ref in citations(book, surface=service):
        try:
            code = parse_code_ref(ref)
        except ValueError:
            continue
        if not code.repository:
            paths.add(code.path)
    return frozenset(paths)


def uncited_by_folder(root: Path, source_folder: str, book: Graph, service: str) -> dict[str, tuple[str, ...]]:
    """Each folder holding product files no page of the service cites, and those files."""
    if not source_folder:
        return {}
    cited = cited_paths(book, service)
    by_folder: dict[str, list[str]] = {}
    for path in product_files(root, source_folder):
        if path not in cited:
            by_folder.setdefault(PurePosixPath(path).parent.as_posix(), []).append(path)
    return {folder: tuple(paths) for folder, paths in sorted(by_folder.items())}
