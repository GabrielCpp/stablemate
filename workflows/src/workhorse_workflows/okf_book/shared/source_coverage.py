"""The product source a book leaves uncited: each file of the surface's source folder that no page's `code:` cites.

A book covers its app when every product file is cited by the page that documents what it does
for a user or a caller, from a node whose claims a run can prove. A concept page mints no claim,
so a file it alone cites is explained and never proven. Tests, test doubles, fixtures and a test
runner's setup are no product. A type declaration file and a build tool's config state nothing a
user or a caller meets, so neither needs a page. A file that declares no name, such as an empty
package marker or one that only re-exports, has no symbol a citation could name, so it needs none.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, TypeAdapter

from ostler import graph as graph_mod
from ostler.inventory import SOURCE_SUFFIXES, declared_names
from ostler.model import Graph
from ostler.refs import code_refs, is_test_source, parse_code_ref, strip_digest
from workhorse_workflows.kit import list_tracked_files

UNCITED_CODE = "uncited-source"
UNPROVING_TYPES = frozenset({"concept"})


class _Node(BaseModel):
    """A node of the book's graph, with only the fields the coverage check reads."""

    model_config = ConfigDict(frozen=True)

    type: str
    bullets: dict[str, object]


_NODES = TypeAdapter(tuple[_Node, ...])
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
        and _declares_a_name(root, path)
    )


def _declares_a_name(root: Path, path: str) -> bool:
    """Whether the file binds a name other than a dunder like `__all__`, so a `path::symbol` citation can reach it."""
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return any(not (name.startswith("__") and name.endswith("__")) for name in declared_names(path, text))


def proving_citations(book: Graph, service: str) -> tuple[str, ...]:
    """Every `code:` target a claim-bearing node of the service cites."""
    nodes = _NODES.validate_python(graph_mod.build(book, surface=service)["nodes"])
    return tuple(
        strip_digest(ref)
        for node in nodes
        if node.type not in UNPROVING_TYPES
        for ref in code_refs(node.bullets.get("code"))
    )


def cited_paths(book: Graph, service: str) -> frozenset[str]:
    """The repo-relative files the service's claim-bearing pages cite, without their symbols."""
    paths: set[str] = set()
    for ref in proving_citations(book, service):
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
