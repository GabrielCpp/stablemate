"""Compact source catalogs that ground external-repository code citations."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ostler import inventory, path as path_mod, refs
from ostler.model import Graph
from ostler.qa.source_context import SourceRepository


class SourceFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    content_sha256: str
    symbols: tuple[str, ...] = ()


class RepositorySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    base: str
    head: str
    files: tuple[SourceFile, ...] = ()


class SourceCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[1] = 1
    repositories: tuple[RepositorySnapshot, ...] = ()

    def repository(self, identifier: str) -> RepositorySnapshot | None:
        return next((item for item in self.repositories if item.id == identifier), None)


def catalog_path(root: Path) -> Path:
    return path_mod.features_root_in(root) / "sources.json"


def load_catalog(root: Path) -> SourceCatalog | None:
    path = catalog_path(root)
    if not path.is_file():
        return None
    return SourceCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _text_at(repository: SourceRepository, path: str) -> str:
    checkout = Path(repository.checkout).resolve()
    if repository.head == "WORKTREE":
        target = checkout / path
        return target.read_text(encoding="utf-8") if target.is_file() else ""
    result = subprocess.run(
        ["git", "show", f"{repository.head}:{path}"],
        cwd=checkout,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout if result.returncode == 0 else ""


def build_catalog(graph: Graph, repositories: tuple[SourceRepository, ...]) -> SourceCatalog:
    """Snapshot every external file the current feature graph cites under `code:`."""
    by_id = {repository.id: repository for repository in repositories}
    cited: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        for value in refs.code_refs(node.meta.get("code")):
            try:
                parsed = refs.parse_code_ref(value)
            except ValueError:
                continue
            if parsed.repository:
                cited.setdefault(parsed.repository, set()).add(parsed.path)

    snapshots: list[RepositorySnapshot] = []
    for identifier in sorted(cited):
        repository = by_id.get(identifier)
        if repository is None:
            continue
        files: list[SourceFile] = []
        for path in sorted(cited[identifier]):
            text = _text_at(repository, path)
            if not text:
                continue
            files.append(SourceFile(
                path=path,
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                symbols=tuple(sorted(inventory.declared_names(path, text))),
            ))
        snapshots.append(RepositorySnapshot(
            id=identifier,
            base=repository.base,
            head=repository.head,
            files=tuple(files),
        ))
    return SourceCatalog(repositories=tuple(snapshots))


def write_catalog(graph: Graph, repositories: tuple[SourceRepository, ...]) -> Path:
    path = catalog_path(graph.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(graph, repositories)
    path.write_text(catalog.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


__all__ = [
    "RepositorySnapshot",
    "SourceCatalog",
    "SourceFile",
    "build_catalog",
    "catalog_path",
    "load_catalog",
    "write_catalog",
]
