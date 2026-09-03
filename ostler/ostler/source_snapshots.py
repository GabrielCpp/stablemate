"""Compact source catalogs that ground code citations, and watermark what they cite.

Two jobs, one file. Grounding asks whether a cited file still declares the symbol the book
names; the backfill watermark asks whether that symbol is still the *same* symbol it was when
the book last described it. Both are answers about the same snapshot of the same bytes, so
both ride one catalog.

The catalog covers the graph's own repository as well as every external one. It did not
always: a snapshot was taken only where a citation named a repository, so the majority of any
book — its unqualified, same-repo `code:` refs — carried no watermark at all, and a run could
only ask "has anything at all changed?" (`source_fingerprint`) rather than "which nodes went
stale?". The graph's own repository is `SELF_REPOSITORY`, the empty id, which is exactly what
`refs.parse_code_ref` puts in `CodeRef.repository` for an unqualified ref.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ostler import inventory, path as path_mod, refs
from ostler.model import Graph
from ostler.qa.source_context import SourceRepository, SourceScope


#: The graph's own repository, as `refs.parse_code_ref` spells it for an unqualified ref.
SELF_REPOSITORY = ""


class SourceSymbol(BaseModel):
    """One declaration in a cited file, and the digest that says whether it has moved."""

    model_config = ConfigDict(frozen=True)

    name: str
    content_sha256: str


class SourceFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    content_sha256: str
    #: Every name the file declares. Kept alongside `declarations` because `doctor`'s
    #: existence check reads it, and a catalog written before `declarations` existed still
    #: has to ground the book it was written for.
    symbols: tuple[str, ...] = ()
    #: The same declarations, each carrying its content digest. Empty on a catalog written
    #: before this field existed — which a reader must treat as "no watermark", never as
    #: "nothing declared".
    declarations: tuple[SourceSymbol, ...] = ()

    def digest_of(self, symbol: str) -> str:
        """*symbol*'s content digest, or `""` when this snapshot carries no watermark for it."""
        return next(
            (item.content_sha256 for item in self.declarations if item.name == symbol), ""
        )


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


def _snapshot_file(path: str, text: str) -> SourceFile:
    """One cited file's snapshot: its bytes, what it declares, and each declaration's digest."""
    digests = inventory.symbol_digests(path, text)
    return SourceFile(
        path=path,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        symbols=tuple(sorted(inventory.declared_names(path, text))),
        declarations=tuple(
            SourceSymbol(name=name, content_sha256=digests[name]) for name in sorted(digests)
        ),
    )


def _cited_paths(graph: Graph) -> dict[str, set[str]]:
    """Every path the book cites, grouped by the repository the citation names.

    An unqualified ref lands under `SELF_REPOSITORY`, which is what `parse_code_ref` already
    returns for one — the grouping is the ref grammar's own answer, not a second reading of it.
    """
    cited: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        for value in refs.code_refs(node.meta.get("code")):
            try:
                parsed = refs.parse_code_ref(value)
            except ValueError:
                continue
            cited.setdefault(parsed.repository, set()).add(parsed.path)
    return cited


def _self_snapshot(graph: Graph, paths: set[str]) -> RepositorySnapshot:
    """The graph's own repository, read off the working tree it is checked out into.

    It carries no `base`, no revisions and no `source_fingerprint`: those describe a *diff*
    against another checkout, and the graph's own repo is the one the book already sits in.
    What it carries is the watermark, which is the whole reason it exists.
    """
    files: list[SourceFile] = []
    for path in sorted(paths):
        target = graph.root / path
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if text:
            files.append(_snapshot_file(path, text))
    return RepositorySnapshot(id=SELF_REPOSITORY, base="", head="WORKTREE", files=tuple(files))


def build_catalog(graph: Graph, repositories: tuple[SourceRepository, ...]) -> SourceCatalog:
    """Snapshot every file the current feature graph cites under `code:`, own repo included."""
    by_id = {repository.id: repository for repository in repositories}
    cited = _cited_paths(graph)

    snapshots: list[RepositorySnapshot] = []
    if cited.get(SELF_REPOSITORY):
        snapshots.append(_self_snapshot(graph, cited[SELF_REPOSITORY]))
    for identifier in sorted(cited):
        if identifier == SELF_REPOSITORY:
            continue
        repository = by_id.get(identifier)
        if repository is None:
            continue
        files: list[SourceFile] = []
        for path in sorted(cited[identifier]):
            text = _text_at(repository, path)
            if not text:
                continue
            files.append(_snapshot_file(path, text))
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
    "SELF_REPOSITORY",
    "RepositorySnapshot",
    "SourceCatalog",
    "SourceFile",
    "SourceSymbol",
    "build_catalog",
    "catalog_path",
    "load_catalog",
    "resolved_sha",
    "source_fingerprint",
    "write_catalog",
]
