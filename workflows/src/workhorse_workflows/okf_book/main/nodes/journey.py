"""The journey pages of a book: the pages its entries page links and its flow pages, which a fix that puts a page on a journey may change."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.entries import book_dir, read_entries
from workhorse_workflows.okf_book.shared.page_check import PageProblem

FLOWS_FOLDER = "flows"


class JourneyPages(BaseModel):
    """The pages a fix that puts a page on a journey may change: the entry pages, the flow pages, and a new page in the flow folder.

    Only the flow pages count against a batch. The writer reads a flow whole to extend it, but adds
    no more than a link to an entry page, which it finds without reading the rest of it. A flow page
    written after the pages were listed is not one of them, since no batch counted it. A later round
    reports it and leaves it for the book check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[str, ...]
    flow_folder: str

    def owns(self, path: str, created: frozenset[str] = frozenset()) -> bool:
        """Whether a turn may change the path: one of the pages, or a flow page in `created`, the paths the turn wrote new."""
        return path in self.pages or (self.is_flow(path) and path in created)

    def is_flow(self, path: str) -> bool:
        return path.startswith(f"{self.flow_folder}/")

    @property
    def flow_pages(self) -> tuple[str, ...]:
        return tuple(page for page in self.pages if self.is_flow(page))


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


def pages_needing_journey(problems: Iterable[PageProblem]) -> frozenset[str]:
    """The pages with a problem whose fix goes on a flow or an entry page."""
    return frozenset(problem.page for problem in problems if problem.needs_journey)
