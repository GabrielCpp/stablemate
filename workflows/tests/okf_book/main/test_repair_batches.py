"""A book too large for one writer is repaired in batches of its problem pages, each under the ceiling."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.repair_batches import JourneyPages, journey_pages, problems_by_page, repair_batches
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

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, ceiling=alone + BOOK_HOLDS * PAGE_TOKENS + 1).batches

    assert [batch.page_paths for batch in batches] == [tuple(pages)]
    assert batches[0].sources == (SOURCE,)


def test_a_page_that_would_cross_the_ceiling_starts_the_next_batch(tmp_path: Path) -> None:
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b", "c")]
    one = BOOK_HOLDS * PAGE_TOKENS + 1

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, ceiling=2 * one).batches

    assert [batch.page_paths for batch in batches] == [tuple(pages[:2]), (pages[2],)]
    assert [batch.tokens for batch in batches] == [2 * one, one]


def test_a_page_alone_over_the_ceiling_goes_to_no_batch_and_is_reported_with_its_cost(tmp_path: Path) -> None:
    _source(tmp_path)
    large = _page(tmp_path, "a.md", cites=True)
    small = _page(tmp_path, "b.md", cites=False)
    one = BOOK_HOLDS * PAGE_TOKENS + 1

    packed = repair_batches(tmp_path, {large: ("p",), small: ("p",)}, ceiling=one)

    assert [batch.page_paths for batch in packed.batches] == [(small,)]
    assert [(page.page, page.tokens) for page in packed.too_large] == [(large, one + SOURCE_READS * SOURCE_TOKENS)]
    assert packed.too_large[0].reason.startswith(f"{large} and the files it cites cost")


def test_the_journey_pages_are_the_pages_the_entries_page_links_and_the_flow_pages_without_the_ones_left_uncommitted(tmp_path: Path) -> None:
    root_page = _page(tmp_path, "ledger.md", cites=False)
    flows = [_page(tmp_path, f"flows/{name}.md", cites=False) for name in ("add", "split")]
    _ = _page(tmp_path, "concepts/entry.md", cites=False)
    _ = (tmp_path / BOOK / "entries.md").write_text("---\ntype: entries\n---\n\n- [Ledger](ledger.md)\n", encoding="utf-8")

    journey = journey_pages(tmp_path, "ledger", frozenset({flows[1]}))

    assert journey == JourneyPages(pages=(root_page, flows[0]), flow_folder=f"{BOOK}/flows")
    assert journey.owns(f"{BOOK}/flows/new.md")
    assert not journey.owns(f"{BOOK}/concepts/entry.md")


def test_pages_whose_fix_goes_on_a_journey_are_packed_first_with_the_journey_pages_cost(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b", "c")]
    journey = JourneyPages(pages=(flow,), flow_folder=f"{BOOK}/flows")
    one = BOOK_HOLDS * PAGE_TOKENS + 1

    batches = repair_batches(tmp_path, {page: ("p",) for page in pages}, journey, frozenset(pages[1:]), ceiling=2 * one).batches

    assert [(batch.page_paths, batch.journey) for batch in batches] == [
        ((pages[1],), journey),
        ((pages[2],), journey),
        ((pages[0],), None),
    ]
    assert batches[0].tokens == one + BOOK_HOLDS * PAGE_TOKENS
    assert batches[0].owns(f"{BOOK}/flows/new.md")
    assert not batches[2].owns(flow)


def test_a_page_over_the_ceiling_with_the_journey_pages_is_reported_with_them(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    page = _page(tmp_path, "a.md", cites=False)
    journey = JourneyPages(pages=(flow,), flow_folder=f"{BOOK}/flows")

    packed = repair_batches(tmp_path, {page: ("p",)}, journey, frozenset({page}), ceiling=BOOK_HOLDS * PAGE_TOKENS + 1)

    assert packed.batches == ()
    assert packed.too_large[0].reason.endswith("split the page or the flow pages")


def test_a_page_that_cites_one_declaration_costs_that_declaration_not_the_file(tmp_path: Path) -> None:
    declaration = "def main():\n    return 0\n"
    source = tmp_path / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    _ = source.write_text(declaration + "#" * SOURCE_TOKENS * CHARS_PER_TOKEN + "\n", encoding="utf-8")
    page = _page(tmp_path, "a.md", cites=True)

    batch = repair_batches(tmp_path, {page: ("p",)}).batches[0]

    assert batch.sources == (f"{SOURCE}:1-2",)
    assert batch.tokens == BOOK_HOLDS * PAGE_TOKENS + 1 + SOURCE_READS * -(-len(declaration) // CHARS_PER_TOKEN)


def test_a_journey_batch_counts_the_flow_pages_and_not_the_entry_pages_it_may_link_from(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    entry = _page(tmp_path, "ledger.md", cites=False)
    page = _page(tmp_path, "a.md", cites=False)
    journey = JourneyPages(pages=(entry, flow), flow_folder=f"{BOOK}/flows")

    batch = repair_batches(tmp_path, {page: ("p",)}, journey, frozenset({page})).batches[0]

    assert batch.tokens == BOOK_HOLDS * PAGE_TOKENS + 1 + BOOK_HOLDS * PAGE_TOKENS
    assert batch.owns(entry)
