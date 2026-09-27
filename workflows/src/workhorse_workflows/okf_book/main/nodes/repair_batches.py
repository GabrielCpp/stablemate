"""The batches a book too large for one writer is repaired in: its problem pages, in path order, each batch under the ceiling one writer reads.

A page costs twice its own tokens, since the writer holds it as it edits it and again as it reads it
back, and twice the part of each source file it cites, since the writer reads that part once and
again as it checks the page's claims against it. The part is the declaration or yaml key the
citation names, or the whole file when it names none. A part two pages of one batch cite is counted
once. A page alone over the ceiling is repaired a few `###` sections at a time instead, each
section costed as a page is and sent with only the problems in it. A section alone over the ceiling,
or a page with no sections, goes to no batch: it is reported, with its cost, for the operator to
split.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.page_sections import HEAD, page_sections
from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_AND_BOOK_CEILING_TOKENS, SOURCE_READS
from workhorse_workflows.okf_book.shared.citations import citations_in
from workhorse_workflows.okf_book.shared.page_check import PageProblem

class PageRepair(BaseModel):
    """One page to repair, repo-relative, each problem the check reports on it, and the parts of files it cites.

    A page too large for one writer names the `###` sections the turn repairs, `HEAD` for the lines
    under no `###` heading. With none named, the turn repairs the whole page.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    problems: tuple[str, ...]
    sources: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()

    def joined(self, other: PageRepair) -> PageRepair:
        """This repair and another of the same page's sections, as one."""
        return self.model_copy(
            update={
                "problems": (*self.problems, *other.problems),
                "sources": tuple(dict.fromkeys((*self.sources, *other.sources))),
                "sections": (*self.sections, *other.sections),
            }
        )


class RepairBatch(BaseModel):
    """The pages one repair turn is sent, the journey pages it may also change, and the tokens of those pages and the files they cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[PageRepair, ...]
    tokens: int
    journey: JourneyPages | None = None

    @property
    def page_paths(self) -> tuple[str, ...]:
        return tuple(repair.page for repair in self.pages)

    def owns(self, path: str, created: frozenset[str] = frozenset()) -> bool:
        """Whether the turn may change the path: one of its pages, or a journey page when it has one."""
        return path in self.page_paths or (self.journey is not None and self.journey.owns(path, created))

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
    section: str | None = None

    @property
    def subject(self) -> str:
        """The page, or the section of it, no turn was sent."""
        if self.section is None:
            return self.page
        return f"{self.page}, the lines under no ### heading" if self.section == HEAD else f"{self.page}, ### {self.section}"

    @property
    def reason(self) -> str:
        counted = ", the files it cites and the flow pages its fix goes on" if self.with_journey else " and the files it cites"
        part = "page" if self.section is None else "section"
        split = f"split the {part} or the flow pages" if self.with_journey else f"split the {part}"
        return (
            f"{self.subject}{counted} cost {self.tokens} tokens, over the {self.ceiling} one writer reads, "
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


def _tokens(chars: int) -> int:
    return -(-chars // CHARS_PER_TOKEN)


def _text_cost(files: CitedFiles, page: str, text: str, problems: tuple[str, ...], sections: tuple[str, ...] = ()) -> _PageCost:
    cited = (files.cited(citation) for citation in citations_in(text))
    sources = {part.label: part.tokens for part in cited if part is not None}
    return _PageCost(
        PageRepair(page=page, problems=problems, sources=tuple(sources), sections=sections),
        BOOK_HOLDS * _tokens(len(text)) + _tokens(sum(len(problem) for problem in problems)),
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


def _journey_cost(root: Path, page: str) -> _PageCost:
    return _PageCost(PageRepair(page=page, problems=()), BOOK_HOLDS * _file_tokens(root / page), {})


def _repairs_joined_by_page(units: list[_PageCost]) -> tuple[PageRepair, ...]:
    by_page: dict[str, PageRepair] = {}
    for unit in units:
        prior = by_page.get(unit.repair.page)
        by_page[unit.repair.page] = unit.repair if prior is None else prior.joined(unit.repair)
    return tuple(by_page.values())


def _batch(journey_costs: list[_PageCost], current: list[_PageCost], journey: JourneyPages | None) -> RepairBatch:
    return RepairBatch(pages=_repairs_joined_by_page(current), tokens=_cost([*journey_costs, *current]), journey=journey)


@dataclass(frozen=True, slots=True)
class _PageSplit:
    units: list[_PageCost]
    too_large: list[TooLarge]


@dataclass(frozen=True, slots=True)
class _PageSplitter:
    files: CitedFiles
    journey_costs: list[_PageCost]
    ceiling: int
    with_journey: bool

    def _tokens_alone(self, unit: _PageCost) -> int:
        return _cost([*self.journey_costs, unit])

    def _too_large(self, page: str, tokens: int, section: str | None = None) -> TooLarge:
        return TooLarge(page=page, tokens=tokens, ceiling=self.ceiling, with_journey=self.with_journey, section=section)

    def _section_units(self, page: str, text: str, problems: tuple[str, ...]) -> _PageSplit:
        parts = page_sections(text)
        by_section: dict[str, list[str]] = {}
        for problem in problems:
            by_section.setdefault(parts.section_id_of_problem(page, problem), []).append(problem)
        units: list[_PageCost] = []
        too_large: list[TooLarge] = []
        for section in (section for section in parts.sections if section.id in by_section):
            unit = _text_cost(self.files, page, parts.section_text(section), tuple(by_section[section.id]), (section.id,))
            tokens_alone = self._tokens_alone(unit)
            if tokens_alone > self.ceiling:
                too_large.append(self._too_large(page, tokens_alone, section.id))
            else:
                units.append(unit)
        return _PageSplit(units, too_large)

    def split_page(self, page: str, problems: tuple[str, ...]) -> _PageSplit:
        """The page whole when it fits, else each of its sections with a problem that fits, and what does not."""
        path = self.files.root / page
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        whole = _text_cost(self.files, page, text, problems)
        tokens_alone = self._tokens_alone(whole)
        if tokens_alone <= self.ceiling:
            return _PageSplit([whole], [])
        if len(page_sections(text).sections) > 1:
            return self._section_units(page, text, problems)
        return _PageSplit([], [self._too_large(page, tokens_alone)])


def _pack(
    files: CitedFiles, by_page: dict[str, tuple[str, ...]], ceiling: int, journey: JourneyPages | None
) -> PackedRepairs:
    journey_costs = [_journey_cost(files.root, page) for page in journey.flow_pages] if journey else []
    splitter = _PageSplitter(files, journey_costs, ceiling, journey is not None)
    batches: list[RepairBatch] = []
    too_large: list[TooLarge] = []
    current: list[_PageCost] = []
    for page, problems in by_page.items():
        split = splitter.split_page(page, problems)
        too_large.extend(split.too_large)
        for unit in split.units:
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
    journey_packed = _pack(files, on_journey, ceiling, journey)
    rest_packed = _pack(files, rest, ceiling, None)
    return PackedRepairs(
        batches=(*journey_packed.batches, *rest_packed.batches),
        too_large=(*journey_packed.too_large, *rest_packed.too_large),
    )
