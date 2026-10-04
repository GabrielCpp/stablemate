"""The journey pages of a book: the pages its entries page links and its flow pages, which a fix that puts a page on a journey may change."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.entries import book_dir, read_entries

FLOWS_FOLDER = "flows"
_LINK = re.compile(r"\]\([^)\s]+\)")


class JourneyPages(BaseModel):
    """The pages a fix that puts a page on a journey may change: the entry pages and the flow pages.

    A batch counts the outline of every one of them, since the writer reads the headings to find the
    flow a page belongs on and to place a link, and adds no more than link lines to an entry page.
    It counts the largest flow page whole once more, since the writer reads the one flow it extends
    whole. A flow page written after the pages were listed is not one of them, since no batch
    counted it. A later round reports it and leaves it for the book check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[str, ...]
    flow_folder: str

    def owns(self, path: str) -> bool:
        """Whether a turn may change the path: one of the pages listed when the round was planned."""
        return path in self.pages

    def is_flow(self, path: str) -> bool:
        return path.startswith(f"{self.flow_folder}/")

    @property
    def flow_pages(self) -> tuple[str, ...]:
        return tuple(page for page in self.pages if self.is_flow(page))

    @property
    def entry_pages(self) -> tuple[str, ...]:
        return tuple(page for page in self.pages if not self.is_flow(page))


def outline(text: str) -> str:
    """The heading lines of a page, which a writer reads to place a link on it."""
    return "\n".join(line for line in text.splitlines() if line.startswith("#"))


def _only_link_lines(lines: list[str]) -> bool:
    in_link_item = False
    for line in lines:
        if _LINK.search(line):
            in_link_item = True
        elif not line.strip():
            in_link_item = False
        elif not (in_link_item and line[0].isspace()):
            return False
    return True


def adds_only_links(before: str, after: str) -> bool:
    """Whether `after` is `before` with lines added and none changed, each added line blank, holding a markdown link, or the indented wrap of an added link line."""
    old, new = before.splitlines(), after.splitlines()
    for tag, _, _, start, end in SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert" or not _only_link_lines(new[start:end]):
            return False
    return True


def journey_pages(root: Path, service: str, uncommitted_at_start: frozenset[str] = frozenset()) -> JourneyPages:
    """The pages the entries page links and the flow pages of the service's book, repo-relative, without the pages in `uncommitted_at_start`."""
    folder = book_dir(root, service)
    linked = (folder / link.page for link in read_entries(root, service))
    flows = sorted((folder / FLOWS_FOLDER).glob("*.md")) if (folder / FLOWS_FOLDER).is_dir() else []
    pages = (path.relative_to(root).as_posix() for path in (*linked, *flows) if path.is_file())
    return JourneyPages(
        pages=tuple(page for page in dict.fromkeys(pages) if page not in uncommitted_at_start),
        flow_folder=(folder / FLOWS_FOLDER).relative_to(root).as_posix(),
    )

