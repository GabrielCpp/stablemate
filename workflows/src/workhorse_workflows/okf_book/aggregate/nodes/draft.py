"""A page writer's reply, each page's whole text, written into the book where the job may write it."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ostler.api import Ostler
from workhorse_workflows.okf_book.shared.confine import draftable
from workhorse_workflows.okf_book.shared.jobs import Job


class DraftedPage(BaseModel):
    """One page's repo-relative path and its whole text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    text: str


class Drafted(BaseModel):
    """A writer's account of what it changed, and each page it wrote, whole."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    pages: tuple[DraftedPage, ...]


PAGE_OPENS = re.compile(r"^=== page: (?P<path>\S+) ===$")
PAGE_ENDS = "=== end ==="
_JSON_STRING = TypeAdapter(str)


def _decoded(text: str) -> str:
    """The page a writer encoded as one JSON string body, every quote and backslash escaped, decoded; any other text unchanged.

    A page as written holds a bare quote wherever it holds an escaped one, since an escape only occurs inside a quoted check argument.
    """
    if '\\"' not in text:
        return text
    escaped_lines = text.replace("\n", "\\n")
    try:
        return _JSON_STRING.validate_json(f'"{escaped_lines}"')
    except ValidationError:
        return text


def read_draft(reply: str) -> Drafted:
    """The pages a writer's reply holds between its page and end lines, each text as written, and the prose outside them as its summary.

    A page the writer JSON-escaped whole is read as the text it encodes.
    """
    pages: list[DraftedPage] = []
    prose: list[str] = []
    path: str | None = None
    body: list[str] = []
    for line in reply.splitlines():
        opens = PAGE_OPENS.match(line.strip())
        if path is None and opens:
            path, body = opens["path"], []
        elif path is None:
            prose.append(line)
        elif line.strip() == PAGE_ENDS:
            pages.append(DraftedPage(path=path, text=_decoded("".join(f"{line}\n" for line in body))))
            path = None
        else:
            body.append(line)
    if path is not None:
        pages.append(DraftedPage(path=path, text=_decoded("".join(f"{line}\n" for line in body))))
    return Drafted(summary="\n".join(prose).strip(), pages=tuple(pages))


@dataclass(frozen=True, slots=True)
class Applied:
    """The drafted pages written into the book, and the paths the job may not write."""

    written: tuple[str, ...]
    dropped: tuple[str, ...]


def existing_pages(root: Path, pages: Iterable[str]) -> list[str]:
    """The pages that are files in the tree, sorted."""
    return sorted(page for page in pages if (root / page).is_file())


def apply_draft(root: Path, job: Job, pages: tuple[DraftedPage, ...]) -> Applied:
    """Write each drafted page the job may write, then canonicalize their shape. Writing the same draft twice changes nothing."""
    written: list[str] = []
    dropped: list[str] = []
    for page in pages:
        if not draftable(root, job, page.path):
            dropped.append(page.path)
            continue
        target = root / page.path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(page.text if page.text.endswith("\n") else f"{page.text}\n", encoding="utf-8")
        written.append(page.path)
    if written:
        _ = Ostler(root, use_index=False).fmt(*written)
    return Applied(written=tuple(written), dropped=tuple(dropped))
