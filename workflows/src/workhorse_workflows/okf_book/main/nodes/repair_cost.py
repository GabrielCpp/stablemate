"""What one writer reads to repair a page, or one `###` section of it, in tokens.

A page costs twice its own tokens, since the writer holds it as it edits it and again as it reads it
back, and twice the part of each source file it cites, since the writer reads that part once and
again as it checks the page's claims against it. The part is the declaration or yaml key the
citation names, or the whole file when it names none. A part two pages of one batch cite is counted
once. A page or section that is over the ceiling at two readings and under it at one is sent alone,
since a file no citation can name a part of, such as a stylesheet, is otherwise never repaired.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.cited_lines import CitedFiles
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages, outline
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
    requests = tuple(dict.fromkeys(request for problem in problems for request in problem.requests))
    return PageCost(
        PageRepair(page=page, problems=texts, sources=tuple(sources), sections=sections, requests=requests),
        BOOK_HOLDS * tokens_of_chars(len(text)) + tokens_of_chars(sum(len(problem) for problem in texts)),
        sources,
    )


def batch_tokens(units: list[PageCost], source_reads: int = SOURCE_READS) -> int:
    """What one turn sent every unit costs, each cited part counted once and read *source_reads* times."""
    sources: dict[str, int] = {}
    for unit in units:
        sources.update(unit.source_tokens)
    return sum(unit.own_tokens for unit in units) + source_reads * sum(sources.values())


def _read_cost(page: str, text: str) -> PageCost:
    return PageCost(PageRepair(page=page, problems=()), BOOK_HOLDS * tokens_of_chars(len(text)), {})


def journey_costs(root: Path, journey: JourneyPages) -> list[PageCost]:
    """What the writer reads of the journey pages a batch may also change: the headings of each, and the largest flow page whole."""
    texts = {page: (root / page).read_text(encoding="utf-8") if (root / page).is_file() else "" for page in journey.pages}
    flows = [page for page in journey.flow_pages if page in texts]
    extended = max(flows, key=lambda page: len(texts[page]), default=None)
    return [_read_cost(page, text if page == extended else outline(text)) for page, text in texts.items()]
