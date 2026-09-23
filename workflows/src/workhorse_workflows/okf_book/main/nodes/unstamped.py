"""Which production files a merge pass documents again: those whose content the book has not stamped."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ostler.stamp import digest_file
from workhorse_workflows.okf_book.shared.citations import Citation


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
