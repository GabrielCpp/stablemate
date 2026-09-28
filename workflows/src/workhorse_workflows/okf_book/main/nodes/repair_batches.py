"""The batches a book too large for one writer is repaired in: its problem pages, in path order, each batch under the ceiling one writer reads.

A page alone over the ceiling is repaired a few `###` sections at a time instead, each section costed
as a page is and sent with only the problems in it. A section alone over the ceiling, or a page with
no sections, goes to no batch: it is reported, with its cost, for the operator to split.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.page_sections import page_sections
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import OversizedPart, PackedRepairs, PageRepair, RepairBatch
from workhorse_workflows.okf_book.main.nodes.repair_cost import PageCost, batch_tokens, journey_costs, text_cost
from workhorse_workflows.okf_book.main.nodes.turn_budget import SOURCE_AND_BOOK_CEILING_TOKENS
from workhorse_workflows.okf_book.shared.page_check import PageProblem

def problems_by_page(
    problems: Iterable[PageProblem], skipped: frozenset[str] = frozenset()
) -> dict[str, tuple[PageProblem, ...]]:
    """Each page's problems, pages in path order, without the pages in `skipped`."""
    grouped: dict[str, list[PageProblem]] = {}
    for problem in problems:
        if problem.page not in skipped:
            grouped.setdefault(problem.page, []).append(problem)
    return {page: tuple(grouped[page]) for page in sorted(grouped)}


def _repairs_joined_by_page(units: list[PageCost]) -> tuple[PageRepair, ...]:
    by_page: dict[str, PageRepair] = {}
    for unit in units:
        prior = by_page.get(unit.repair.page)
        by_page[unit.repair.page] = unit.repair if prior is None else prior.joined(unit.repair)
    return tuple(by_page.values())


def _claim_new_flow_page(root: Path, journey: JourneyPages, page: str, claimed_flow_pages: set[str]) -> str:
    """A path in the flow folder named for the page, that no page on disk and no other batch holds."""
    stem = Path(page).stem
    candidates = (f"{journey.flow_folder}/{stem}{'' if n == 1 else f'-{n}'}.md" for n in range(1, len(claimed_flow_pages) + 2))
    path = next(path for path in candidates if path not in claimed_flow_pages and not (root / path).exists())
    claimed_flow_pages.add(path)
    return path


def _batch(
    root: Path, journey_costs: list[PageCost], filling_batch_units: list[PageCost], journey: JourneyPages | None, claimed_flow_pages: set[str]
) -> RepairBatch:
    pages = _repairs_joined_by_page(filling_batch_units)
    return RepairBatch(
        pages=pages,
        tokens=batch_tokens([*journey_costs, *filling_batch_units]),
        journey=journey,
        new_flow_page=_claim_new_flow_page(root, journey, pages[0].page, claimed_flow_pages) if journey else "",
    )


@dataclass(frozen=True, slots=True)
class _PageSplit:
    units: list[PageCost]
    oversized_parts: list[OversizedPart]


@dataclass(frozen=True, slots=True)
class _PageSplitter:
    files: CitedFiles
    journey_costs: list[PageCost]
    ceiling: int
    with_journey: bool

    def _tokens_alone(self, unit: PageCost) -> int:
        return batch_tokens([*self.journey_costs, unit])

    def _oversized(self, page: str, tokens: int, section: str | None = None) -> OversizedPart:
        return OversizedPart(page=page, tokens=tokens, ceiling=self.ceiling, with_journey=self.with_journey, section=section)

    def _split_by_section(self, page: str, text: str, problems: tuple[PageProblem, ...]) -> _PageSplit:
        parts = page_sections(text)
        by_section: dict[str, list[PageProblem]] = {}
        for problem in problems:
            by_section.setdefault(parts.section_id_of_problem(problem), []).append(problem)
        units: list[PageCost] = []
        oversized_parts: list[OversizedPart] = []
        for section in (section for section in parts.sections if section.id in by_section):
            unit = text_cost(self.files, page, parts.section_text(section), tuple(by_section[section.id]), (section.id,))
            tokens_alone = self._tokens_alone(unit)
            if tokens_alone > self.ceiling:
                oversized_parts.append(self._oversized(page, tokens_alone, section.id))
            else:
                units.append(unit)
        return _PageSplit(units, oversized_parts)

    def split_page(self, page: str, problems: tuple[PageProblem, ...]) -> _PageSplit:
        """The page whole when it fits, else each of its sections with a problem that fits, and what does not."""
        path = self.files.root / page
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        whole = text_cost(self.files, page, text, problems)
        tokens_alone = self._tokens_alone(whole)
        if tokens_alone <= self.ceiling:
            return _PageSplit([whole], [])
        if len(page_sections(text).sections) > 1:
            return self._split_by_section(page, text, problems)
        return _PageSplit([], [self._oversized(page, tokens_alone)])


def _pack(
    files: CitedFiles, by_page: dict[str, tuple[PageProblem, ...]], ceiling: int, journey: JourneyPages | None
) -> PackedRepairs:
    read_journey = journey_costs(files.root, journey) if journey else []
    splitter = _PageSplitter(files, read_journey, ceiling, journey is not None)
    batches: list[RepairBatch] = []
    oversized_parts: list[OversizedPart] = []
    filling_batch_units: list[PageCost] = []
    claimed_flow_pages: set[str] = set(journey.pages) if journey else set()
    for page, problems in by_page.items():
        split = splitter.split_page(page, problems)
        oversized_parts.extend(split.oversized_parts)
        for unit in split.units:
            if filling_batch_units and batch_tokens([*read_journey, *filling_batch_units, unit]) > ceiling:
                batches.append(_batch(files.root, read_journey, filling_batch_units, journey, claimed_flow_pages))
                filling_batch_units = []
            filling_batch_units.append(unit)
    if filling_batch_units:
        batches.append(_batch(files.root, read_journey, filling_batch_units, journey, claimed_flow_pages))
    return PackedRepairs(batches=tuple(batches), oversized_parts=tuple(oversized_parts))


def pack_repairs(
    root: Path,
    by_page: dict[str, tuple[PageProblem, ...]],
    journey: JourneyPages | None = None,
    ceiling: int = SOURCE_AND_BOOK_CEILING_TOKENS,
) -> PackedRepairs:
    """Pack the pages, in the order given, into batches each under `ceiling`, and set aside each page alone over it.

    The problems whose fix goes on a flow or an entry page go first, into batches that also hold the
    journey pages and count what the writer reads of them. A page's other problems go to batches
    without them, so a large page with one such problem is not costed the journey pages in every
    section.
    """
    on_journey = {page: kept for page, problems in by_page.items() if journey and (kept := tuple(p for p in problems if p.needs_journey))}
    rest = {page: kept for page, problems in by_page.items() if (kept := tuple(p for p in problems if not (journey and p.needs_journey)))}
    files = CitedFiles(root)
    journey_packed = _pack(files, on_journey, ceiling, journey)
    rest_packed = _pack(files, rest, ceiling, None)
    return PackedRepairs(
        batches=(*journey_packed.batches, *rest_packed.batches),
        oversized_parts=(*journey_packed.oversized_parts, *rest_packed.oversized_parts),
    )
