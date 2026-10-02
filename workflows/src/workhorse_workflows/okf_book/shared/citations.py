"""The source files a book's pages cite on their `code:` bullets, with the symbol and the digest each cites."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ostler.pages import files_in_book
from ostler.refs import code_refs, parse_code_ref
from workhorse_workflows.okf_book.shared.entries import book_dir

_CODE_BULLET = re.compile(r"^\s*[-*]\s+code:\s*(?P<value>.*)$")
_FENCE = "```"


@dataclass(frozen=True, slots=True)
class Citation:
    """One cited file, repo-relative, the digest stamped beside it, if any, and the symbol it names, if any."""

    path: str
    digest: str | None
    symbol: str = ""


def _bullet_citations(value: str) -> list[Citation]:
    found: list[Citation] = []
    for rendered in code_refs(value):
        try:
            ref = parse_code_ref(rendered)
        except ValueError:
            continue
        if not ref.repository:
            found.append(Citation(ref.path, ref.digest, ref.symbol))
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
