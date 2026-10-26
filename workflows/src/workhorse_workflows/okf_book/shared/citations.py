"""The source files a book's pages cite on their `code:` bullets, with the symbol and the digest each cites."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ostler.pages import files_in_book
from ostler.refs import code_refs, parse_code_ref
from ostler.stamp import digest_file
from workhorse_workflows.okf_book.shared.entries import book_dir
from workhorse_workflows.okf_book.shared.source_repo import repository_root

_CODE_BULLET = re.compile(r"^\s*[-*]\s+code:\s*(?P<value>.*)$")
_FENCE = "```"


@dataclass(frozen=True, slots=True)
class Citation:
    """One cited file, repo-relative, the digest stamped beside it, if any, the symbol it names, if any, and the workspace member it lives in, empty for the book's own repository."""

    path: str
    digest: str | None
    symbol: str = ""
    repository: str = ""


def _bullet_citations(value: str) -> list[Citation]:
    found: list[Citation] = []
    for rendered in code_refs(value):
        try:
            ref = parse_code_ref(rendered)
        except ValueError:
            continue
        found.append(Citation(ref.path, ref.digest, ref.symbol, ref.repository))
    return found


def citations_in(text: str) -> tuple[Citation, ...]:
    """Every citation on a `code:` bullet of `text`, outside fenced blocks."""
    found: list[Citation] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(_FENCE):
            fenced = not fenced
            continue
        match = None if fenced else _CODE_BULLET.match(line)
        if match:
            found.extend(_bullet_citations(match.group("value")))
    return tuple(found)


def page_citations(page: Path) -> tuple[Citation, ...]:
    return citations_in(page.read_text(encoding="utf-8"))


def book_pages(root: Path, service: str) -> tuple[Path, ...]:
    """Every markdown page of the service's book."""
    folder = book_dir(root, service)
    if not folder.is_dir():
        return ()
    return tuple(files_in_book(folder))


def cites_changed_file(root: Path, service: str) -> bool:
    """Whether any page of the service's book cites a file that no longer has the digest stamped beside it."""
    digests: dict[tuple[str, str], str | None] = {}
    for page in book_pages(root, service):
        for citation in page_citations(page):
            if citation.digest is None:
                continue
            key = (citation.repository, citation.path)
            if key not in digests:
                tree = repository_root(root, citation.repository)
                cited = tree / citation.path if tree else None
                digests[key] = digest_file(cited.read_bytes()) if cited and cited.is_file() else None
            current = digests[key]
            if current is not None and current != citation.digest:
                return True
    return False
