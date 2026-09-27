"""The batches a book too large for one writer is repaired in: its problem pages, in path order, each batch under the ceiling one writer reads.

A page costs twice its own tokens, since the writer holds it as it edits it and again as it reads it
back, and twice the part of each source file it cites, since the writer reads that part once and
again as it checks the page's claims against it. The part is the declaration or yaml key the
citation names, or the whole file when it names none. A part two pages of one batch cite is counted
once. A page alone over the ceiling goes to no batch: it is reported, with its cost, for the
operator to split.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles
from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_AND_BOOK_CEILING_TOKENS, SOURCE_READS
from workhorse_workflows.okf_book.shared.citations import page_citations
from workhorse_workflows.okf_book.shared.entries import book_dir, read_entries
from workhorse_workflows.okf_book.shared.page_check import PageProblem

FLOWS_FOLDER = "flows"


class PageRepair(BaseModel):
    """One page to repair, repo-relative, and each problem the check reports on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    problems: tuple[str, ...]
    sources: tuple[str, ...] = ()


class JourneyPages(BaseModel):
    """The pages a fix that puts a page on a journey may change: the entry pages, the flow pages, and a new page in the flow folder.

    Only the flow pages count against a batch. The writer reads a flow whole to extend it, but adds
    no more than a link to an entry page, which it finds without reading the rest of it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[str, ...]
    flow_folder: str

    def owns(self, path: str) -> bool:
        return path in self.pages or self.is_flow(path)

    def is_flow(self, path: str) -> bool:
        return path.startswith(f"{self.flow_folder}/")

    @property
    def flow_pages(self) -> tuple[str, ...]:
        return tuple(page for page in self.pages if self.is_flow(page))


class RepairBatch(BaseModel):
    """The pages one repair turn is sent, the journey pages it may also change, and the tokens of those pages and the files they cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[PageRepair, ...]
    tokens: int
    journey: JourneyPages | None = None

    @property
    def page_paths(self) -> tuple[str, ...]:
        return tuple(repair.page for repair in self.pages)

    def owns(self, path: str) -> bool:
        """Whether the turn may change the path: one of its pages, or a journey page when it has one."""
        return path in self.page_paths or (self.journey is not None and self.journey.owns(path))

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(source for repair in self.pages for source in repair.sources))


class TooLarge(BaseModel):
    """A problem page no turn is sent, since it, the files it cites and the flow pages its fix goes on cost more than one writer reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    tokens: int
    ceiling: int
    with_journey: bool = False

    @property
    def reason(self) -> str:
        cost = ", the files it cites and the flow pages its fix goes on" if self.with_journey else " and the files it cites"
        split = "split the page or the flow pages" if self.with_journey else "split the page"
        return (
            f"{self.page}{cost} cost {self.tokens} tokens, over the {self.ceiling} one writer reads, "
            + f"so no repair turn was sent it: {split}"
        )


class PackedRepairs(BaseModel):
    """The batches the repair turns are sent, and the pages too large for any of them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    batches: tuple[RepairBatch, ...]
    too_large: tuple[TooLarge, ...] = ()


@dataclass(frozen=True, slots=True)
class _PageCost:
    repair: PageRepair
    own_tokens: int
    source_tokens: dict[str, int]


def _file_tokens(path: Path) -> int:
    return -(-path.stat().st_size // CHARS_PER_TOKEN) if path.is_file() else 0


def _page_cost(files: CitedFiles, page: str, problems: tuple[str, ...]) -> _PageCost:
    path = files.root / page
    cited = (files.cited(citation) for citation in page_citations(path)) if path.is_file() else ()
    sources = {part.label: part.tokens for part in cited if part is not None}
    problem_tokens = -(-sum(len(problem) for problem in problems) // CHARS_PER_TOKEN)
    return _PageCost(
        PageRepair(page=page, problems=problems, sources=tuple(sources)),
        BOOK_HOLDS * _file_tokens(path) + problem_tokens,
        sources,
    )


def _cost(units: list[_PageCost]) -> int:
    sources: dict[str, int] = {}
    for unit in units:
        sources.update(unit.source_tokens)
    return sum(unit.own_tokens for unit in units) + SOURCE_READS * sum(sources.values())


def problems_by_page(problems: Iterable[PageProblem], skipped: frozenset[str] = frozenset()) -> dict[str, tuple[str, ...]]:
    """Each page's problems, pages in path order, without the pages in `skipped`."""
    grouped: dict[str, list[str]] = {}
    for problem in problems:
        if problem.page not in skipped:
            grouped.setdefault(problem.page, []).append(problem.text)
    return {page: tuple(grouped[page]) for page in sorted(grouped)}


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


def journey_needed(problems: Iterable[PageProblem]) -> frozenset[str]:
    """The pages with a problem whose fix goes on a flow or an entry page."""
    return frozenset(problem.page for problem in problems if problem.needs_journey)


def _journey_cost(root: Path, page: str) -> _PageCost:
    return _PageCost(PageRepair(page=page, problems=()), BOOK_HOLDS * _file_tokens(root / page), {})


def _batch(journey_costs: list[_PageCost], current: list[_PageCost], journey: JourneyPages | None) -> RepairBatch:
    return RepairBatch(pages=tuple(u.repair for u in current), tokens=_cost([*journey_costs, *current]), journey=journey)


def _pack(
    files: CitedFiles, by_page: dict[str, tuple[str, ...]], ceiling: int, journey: JourneyPages | None
) -> PackedRepairs:
    journey_costs = [_journey_cost(files.root, page) for page in journey.flow_pages] if journey else []
    batches: list[RepairBatch] = []
    too_large: list[TooLarge] = []
    current: list[_PageCost] = []
    for page, problems in by_page.items():
        unit = _page_cost(files, page, problems)
        alone = _cost([*journey_costs, unit])
        if alone > ceiling:
            too_large.append(TooLarge(page=page, tokens=alone, ceiling=ceiling, with_journey=journey is not None))
            continue
        if current and _cost([*journey_costs, *current, unit]) > ceiling:
            batches.append(_batch(journey_costs, current, journey))
            current = []
        current.append(unit)
    if current:
        batches.append(_batch(journey_costs, current, journey))
    return PackedRepairs(batches=tuple(batches), too_large=tuple(too_large))


def repair_batches(
    root: Path,
    by_page: dict[str, tuple[str, ...]],
    journey: JourneyPages | None = None,
    needs_journey: frozenset[str] = frozenset(),
    ceiling: int = SOURCE_AND_BOOK_CEILING_TOKENS,
) -> PackedRepairs:
    """Pack the pages, in the order given, into batches each under `ceiling`, and set aside each page alone over it.

    The pages in `needs_journey` go first, into batches that also hold the journey pages and count
    the flow pages' cost, since their fix goes on a flow or an entry page.
    """
    on_journey = {page: problems for page, problems in by_page.items() if journey and page in needs_journey}
    rest = {page: problems for page, problems in by_page.items() if page not in on_journey}
    files = CitedFiles(root)
    first = _pack(files, on_journey, ceiling, journey)
    then = _pack(files, rest, ceiling, None)
    return PackedRepairs(batches=(*first.batches, *then.batches), too_large=(*first.too_large, *then.too_large))
