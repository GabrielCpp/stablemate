"""The batches a book too large for one writer is repaired in: its problem pages, in path order, each batch under the ceiling one writer reads.

A page costs twice its own tokens, since the writer holds it as it edits it and again as it reads it
back, and twice each source file it cites, since the writer reads the file once and again as it
checks the page's claims against it. A file two pages of one batch cite is counted once. A page
alone over the ceiling is a batch of its own.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_AND_BOOK_CEILING_TOKENS, SOURCE_READS
from workhorse_workflows.okf_book.shared.citations import page_citations
from workhorse_workflows.okf_book.shared.page_check import PageProblem


class PageRepair(BaseModel):
    """One page to repair, repo-relative, and each problem the check reports on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    problems: tuple[str, ...]
    sources: tuple[str, ...] = ()


class RepairBatch(BaseModel):
    """The pages one repair turn is sent, and the tokens of those pages and the files they cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[PageRepair, ...]
    tokens: int

    @property
    def page_paths(self) -> tuple[str, ...]:
        return tuple(repair.page for repair in self.pages)

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(source for repair in self.pages for source in repair.sources))


@dataclass(frozen=True, slots=True)
class _Unit:
    repair: PageRepair
    own_tokens: int
    source_tokens: dict[str, int]


def _file_tokens(path: Path) -> int:
    return -(-path.stat().st_size // CHARS_PER_TOKEN) if path.is_file() else 0


def _unit(root: Path, page: str, problems: tuple[str, ...]) -> _Unit:
    path = root / page
    cited = tuple(dict.fromkeys(citation.path for citation in page_citations(path))) if path.is_file() else ()
    sources = {source: _file_tokens(root / source) for source in cited if (root / source).is_file()}
    problem_tokens = -(-sum(len(problem) for problem in problems) // CHARS_PER_TOKEN)
    return _Unit(
        PageRepair(page=page, problems=problems, sources=tuple(sources)),
        BOOK_HOLDS * _file_tokens(path) + problem_tokens,
        sources,
    )


def _cost(units: list[_Unit]) -> int:
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


def repair_batches(
    root: Path, by_page: dict[str, tuple[str, ...]], ceiling: int = SOURCE_AND_BOOK_CEILING_TOKENS
) -> tuple[RepairBatch, ...]:
    """Pack the pages, in the order given, into batches each under `ceiling`."""
    batches: list[RepairBatch] = []
    current: list[_Unit] = []
    for page, problems in by_page.items():
        unit = _unit(root, page, problems)
        if current and _cost([*current, unit]) > ceiling:
            batches.append(RepairBatch(pages=tuple(u.repair for u in current), tokens=_cost(current)))
            current = []
        current.append(unit)
    if current:
        batches.append(RepairBatch(pages=tuple(u.repair for u in current), tokens=_cost(current)))
    return tuple(batches)
