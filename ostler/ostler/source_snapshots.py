"""Compact source catalogs that ground code citations, and watermark what they cite."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ostler import path as path_mod
from ostler.qa.source_context import SourceRepository, SourceScope


SELF_REPOSITORY = ""

REPOSITORY_DECL_FILENAME = "repository.txt"


def book_repository(features_root: Path) -> str:
    """The repository a book declares its unqualified ``code:`` refs resolve to."""
    path = Path(features_root) / REPOSITORY_DECL_FILENAME
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def set_book_repository(features_root: Path, repository_id: str) -> Path:
    """Write the book's repository declaration."""
    path = Path(features_root) / REPOSITORY_DECL_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(repository_id.strip() + "\n", encoding="utf-8")
    return path


class SourceSymbol(BaseModel):
    """One declaration in a cited file, and the digest that says whether it has moved."""

    model_config = ConfigDict(frozen=True)

    name: str
    content_sha256: str


class SourceFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    content_sha256: str
    symbols: tuple[str, ...] = ()
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


__all__ = [
    "REPOSITORY_DECL_FILENAME",
    "SELF_REPOSITORY",
    "RepositorySnapshot",
    "SourceCatalog",
    "SourceFile",
    "SourceSymbol",
    "book_repository",
    "catalog_path",
    "load_catalog",
    "set_book_repository",
    "resolved_sha",
    "source_fingerprint",
]
