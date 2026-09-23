"""The files one run documents, fixed once by phase 1 and read back unchanged on every resume."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ostler.stamp import digest_file
from workhorse_workflows.okf_book.citations import Citation

WORK_SET_NAME = "work-set.json"


class WorkSet(BaseModel):
    """The frozen output of enumeration: which services the run covers, and which files it documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[str, ...]
    files: tuple[str, ...]
    pruned: tuple[str, ...] = ()


def cited_digests(citations: Iterable[Citation]) -> dict[str, frozenset[str]]:
    """Each cited file with every digest the book stamps it with."""
    found: dict[str, set[str]] = {}
    for citation in citations:
        digests = found.setdefault(citation.path, set())
        if citation.digest:
            digests.add(citation.digest)
    return {path: frozenset(digests) for path, digests in found.items()}


def unstamped_files(root: Path, files: Iterable[str], cited: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The files whose content the book has not stamped: new, unstamped, or edited since."""
    return frozenset(
        rel for rel in files
        if digest_file((root / rel).read_bytes()) not in cited.get(rel, frozenset())
    )


def freeze(run_dir: Path, work_set: WorkSet) -> WorkSet:
    """Write the work set once. A later call returns the one already written instead."""
    path = run_dir / WORK_SET_NAME
    if path.is_file():
        return WorkSet.model_validate_json(path.read_text(encoding="utf-8"))
    run_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(work_set.model_dump_json(indent=2), encoding="utf-8")
    return work_set


def read_work_set(run_dir: Path) -> WorkSet | None:
    """The work set this run already fixed, if enumeration got that far."""
    path = run_dir / WORK_SET_NAME
    return WorkSet.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
