"""What one writer reads to repair a page, or one `###` section of it, in tokens.

A page costs twice its own tokens, since the writer holds it as it edits it and again as it reads it
back, and twice the part of each source file it cites, since the writer reads that part once and
again as it checks the page's claims against it. The part is the declaration or yaml key the
citation names, or the whole file when it names none. A part two pages of one batch cite is counted
once.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import PageRepair
from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_READS
from workhorse_workflows.okf_book.shared.citations import citations_in
from workhorse_workflows.okf_book.shared.page_check import PageProblem


@dataclass(frozen=True, slots=True)
class PageCost:
    """One page or section to repair, what the writer reads of it and its problems, and the tokens of each part of a file it cites."""

    repair: PageRepair
    own_tokens: int
    source_tokens: dict[str, int]


def tokens_of_chars(chars: int) -> int:
    """The tokens a text of *chars* characters costs, rounded up."""
    return -(-chars // CHARS_PER_TOKEN)


def text_cost(
    files: CitedFiles, page: str, text: str, problems: tuple[PageProblem, ...], sections: tuple[str, ...] = ()
) -> PageCost:
    """What repairing *text*, a page or one section of it, costs the writer."""
    cited = (files.cited(citation) for citation in citations_in(text))
    sources = {part.label: part.tokens for part in cited if part is not None}
    texts = tuple(problem.text for problem in problems)
    return PageCost(
        PageRepair(page=page, problems=texts, sources=tuple(sources), sections=sections),
        BOOK_HOLDS * tokens_of_chars(len(text)) + tokens_of_chars(sum(len(problem) for problem in texts)),
        sources,
    )


def batch_tokens(units: list[PageCost]) -> int:
    """What one turn sent every unit costs, each cited part counted once."""
    sources: dict[str, int] = {}
    for unit in units:
        sources.update(unit.source_tokens)
    return sum(unit.own_tokens for unit in units) + SOURCE_READS * sum(sources.values())


def journey_cost(root: Path, journey: JourneyPages, page: str) -> PageCost:
    """What the writer reads of a journey page a batch may also change."""
    path = root / page
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return PageCost(PageRepair(page=page, problems=()), BOOK_HOLDS * tokens_of_chars(len(journey.read_by_writer(page, text))), {})
