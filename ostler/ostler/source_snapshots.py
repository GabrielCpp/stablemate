"""Compact source catalogs that ground external-repository code citations."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ostler import inventory, path as path_mod, refs
from ostler.model import Graph
from ostler.qa.source_context import SourceRepository, SourceScope


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
    base_sha: str = ""
    head_sha: str = ""
    head_anchor_sha: str = ""
    scopes: tuple[SourceScope, ...] = ()
    source_fingerprint: str = ""
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


def _git(repository: SourceRepository, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path(repository.checkout).resolve(),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def resolved_sha(repository: SourceRepository, revision: str) -> str:
    value = _git(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")
    return value.decode().strip() if value else ""


def source_fingerprint(repository: SourceRepository) -> str:
    """Hash every path and byte under the repository's declared source scopes."""
    roots = sorted({scope.root.strip("/") or "." for scope in repository.scopes})
    if repository.head == "WORKTREE":
        listed = _git(
            repository,
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *roots,
        )
    else:
        listed = _git(
            repository,
            "ls-tree",
            "-r",
            "--name-only",
            repository.head,
            "--",
            *roots,
        )
    if listed is None:
        return ""
    digest = hashlib.sha256()
    for scope in repository.scopes:
        digest.update(f"scope\0{scope.surface}\0{scope.root}\0".encode())
    checkout = Path(repository.checkout).resolve()
    for raw_path in sorted(set(listed.decode().splitlines())):
        digest.update(raw_path.encode() + b"\0")
        if repository.head == "WORKTREE":
            target = checkout / raw_path
            content = target.read_bytes() if target.is_file() else b"<deleted>"
        else:
            content = _git(repository, "show", f"{repository.head}:{raw_path}")
            if content is None:
                content = b"<missing>"
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


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
            base_sha=resolved_sha(repository, repository.base),
            head_sha=(
                "" if repository.head == "WORKTREE" else resolved_sha(repository, repository.head)
            ),
            head_anchor_sha=(
                resolved_sha(repository, "HEAD") if repository.head == "WORKTREE" else ""
            ),
            scopes=repository.scopes,
            source_fingerprint=source_fingerprint(repository),
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
    "resolved_sha",
    "source_fingerprint",
    "write_catalog",
]
