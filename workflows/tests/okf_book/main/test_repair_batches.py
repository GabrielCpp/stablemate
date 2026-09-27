"""A book too large for one writer is repaired in batches of its problem pages, each under the ceiling."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.repair_batches import problems_by_page, repair_batches
from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_READS
from workhorse_workflows.okf_book.shared.page_check import PageProblem

BOOK = "docs/features/ledger"
SOURCE = "ledger/cli.py"
PAGE_TOKENS = 100
SOURCE_TOKENS = 400


def _page(root: Path, name: str, *, cites: bool) -> str:
    page = f"{BOOK}/{name}"
    path = root / page
    path.parent.mkdir(parents=True, exist_ok=True)
    citation = f"- code: `{SOURCE}::main`\n" if cites else ""
    body = f"# {name}\n\n{citation}"
    _ = path.write_text(body + "x" * (PAGE_TOKENS * CHARS_PER_TOKEN - len(body)), encoding="utf-8")
    return page


def _source(root: Path) -> None:
    path = root / SOURCE
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("x" * SOURCE_TOKENS * CHARS_PER_TOKEN, encoding="utf-8")


def test_problems_are_grouped_by_page_in_path_order_without_the_skipped_pages() -> None:
    problems = (PageProblem("b.md", "b one"), PageProblem("a.md", "a one"), PageProblem("b.md", "b two"), PageProblem("c.md", "c"))

    grouped = problems_by_page(problems, frozenset({"c.md"}))

    assert grouped == {"a.md": ("a one",), "b.md": ("b one", "b two")}


def test_pages_that_cite_one_file_share_its_cost_in_one_batch(tmp_path: Path) -> None:
    _source(tmp_path)
    pages = [_page(tmp_path, f"{name}.md", cites=True) for name in ("a", "b")]
    alone = BOOK_HOLDS * PAGE_TOKENS + 1 + SOURCE_READS * SOURCE_TOKENS

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, ceiling=alone + BOOK_HOLDS * PAGE_TOKENS + 1)

    assert [batch.page_paths for batch in batches] == [tuple(pages)]
    assert batches[0].sources == (SOURCE,)


def test_a_page_that_would_cross_the_ceiling_starts_the_next_batch(tmp_path: Path) -> None:
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b", "c")]
    one = BOOK_HOLDS * PAGE_TOKENS + 1

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, ceiling=2 * one)

    assert [batch.page_paths for batch in batches] == [tuple(pages[:2]), (pages[2],)]
    assert [batch.tokens for batch in batches] == [2 * one, one]


def test_a_page_alone_over_the_ceiling_is_a_batch_of_its_own(tmp_path: Path) -> None:
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b")]

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, ceiling=1)

    assert [batch.page_paths for batch in batches] == [(pages[0],), (pages[1],)]
