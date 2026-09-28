"""A book too large for one writer is repaired in batches of its problem pages, each under the ceiling."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.repair_batches import problems_by_page, pack_repairs
from workhorse_workflows.okf_book.main.nodes.turn_budget import BOOK_HOLDS, CHARS_PER_TOKEN, SOURCE_READS
from workhorse_workflows.okf_book.shared.page_check import PageProblem

BOOK = "docs/features/ledger"
SOURCE = "ledger/cli.py"
PAGE_TOKENS = 100
SOURCE_TOKENS = 400
ONE_PAGE_TOKENS = BOOK_HOLDS * PAGE_TOKENS + 1


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

    assert grouped == {"a.md": (problems[1],), "b.md": (problems[0], problems[2])}


def test_pages_that_cite_one_file_share_its_cost_in_one_batch(tmp_path: Path) -> None:
    _source(tmp_path)
    pages = [_page(tmp_path, f"{name}.md", cites=True) for name in ("a", "b")]
    one_citing_page_tokens = ONE_PAGE_TOKENS + SOURCE_READS * SOURCE_TOKENS

    batches = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),) for page in pages}, ceiling=one_citing_page_tokens + ONE_PAGE_TOKENS).batches

    assert [batch.page_paths for batch in batches] == [tuple(pages)]
    assert batches[0].sources == (SOURCE,)


def test_a_page_that_would_cross_the_ceiling_starts_the_next_batch(tmp_path: Path) -> None:
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b", "c")]

    batches = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),) for page in pages}, ceiling=2 * ONE_PAGE_TOKENS).batches

    assert [batch.page_paths for batch in batches] == [tuple(pages[:2]), (pages[2],)]
    assert [batch.tokens for batch in batches] == [2 * ONE_PAGE_TOKENS, ONE_PAGE_TOKENS]


def test_a_page_alone_over_the_ceiling_goes_to_no_batch_and_is_reported_with_its_cost(tmp_path: Path) -> None:
    _source(tmp_path)
    large = _page(tmp_path, "a.md", cites=True)
    small = _page(tmp_path, "b.md", cites=False)

    packed = pack_repairs(tmp_path, {large: (PageProblem(large, "p"),), small: (PageProblem(small, "p"),)}, ceiling=ONE_PAGE_TOKENS)

    assert [batch.page_paths for batch in packed.batches] == [(small,)]
    assert [(part.page, part.tokens) for part in packed.oversized_parts] == [(large, ONE_PAGE_TOKENS + SOURCE_READS * SOURCE_TOKENS)]
    assert packed.oversized_parts[0].reason.startswith(f"{large} and the files it cites cost")


def test_pages_whose_fix_goes_on_a_journey_are_packed_first_with_the_journey_pages_cost(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    pages = [_page(tmp_path, f"{name}.md", cites=False) for name in ("a", "b", "c")]
    journey = JourneyPages(pages=(flow,), flow_folder=f"{BOOK}/flows")

    batches = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),) for page in pages}, journey, frozenset(pages[1:]), ceiling=2 * ONE_PAGE_TOKENS).batches

    assert [(batch.page_paths, batch.journey) for batch in batches] == [
        ((pages[1],), journey),
        ((pages[2],), journey),
        ((pages[0],), None),
    ]
    assert batches[0].tokens == ONE_PAGE_TOKENS + BOOK_HOLDS * PAGE_TOKENS
    assert not batches[2].owns(flow)


def test_each_journey_batch_may_write_one_new_flow_page_named_when_it_is_planned(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    pages = [_page(tmp_path, f"{folder}/add.md", cites=False) for folder in ("ops", "admin")]
    journey = JourneyPages(pages=(flow,), flow_folder=f"{BOOK}/flows")

    batches = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),) for page in pages}, journey, frozenset(pages), ceiling=2 * ONE_PAGE_TOKENS).batches

    assert [batch.new_flow_page for batch in batches] == [f"{BOOK}/flows/add-2.md", f"{BOOK}/flows/add-3.md"]
    assert batches[0].owns(f"{BOOK}/flows/add-2.md")
    assert not batches[0].owns(f"{BOOK}/flows/add-3.md")
    assert not batches[0].owns(f"{BOOK}/flows/other.md")


def test_a_page_over_the_ceiling_with_the_journey_pages_is_reported_with_them(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    page = _page(tmp_path, "a.md", cites=False)
    journey = JourneyPages(pages=(flow,), flow_folder=f"{BOOK}/flows")

    packed = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),)}, journey, frozenset({page}), ceiling=BOOK_HOLDS * PAGE_TOKENS + 1)

    assert packed.batches == ()
    assert packed.oversized_parts[0].reason.endswith("split the page or the flow pages")


def test_a_page_that_cites_one_declaration_costs_that_declaration_not_the_file(tmp_path: Path) -> None:
    declaration = "def main():\n    return 0\n"
    source = tmp_path / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    _ = source.write_text(declaration + "#" * SOURCE_TOKENS * CHARS_PER_TOKEN + "\n", encoding="utf-8")
    page = _page(tmp_path, "a.md", cites=True)

    batch = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),)}).batches[0]

    assert batch.sources == (f"{SOURCE}:1-2",)
    assert batch.tokens == BOOK_HOLDS * PAGE_TOKENS + 1 + SOURCE_READS * -(-len(declaration) // CHARS_PER_TOKEN)


def test_a_journey_batch_counts_the_flow_pages_whole_and_the_headings_of_the_entry_pages(tmp_path: Path) -> None:
    flow = _page(tmp_path, "flows/add.md", cites=False)
    entry = _page(tmp_path, "ledger.md", cites=False)
    page = _page(tmp_path, "a.md", cites=False)
    journey = JourneyPages(pages=(entry, flow), flow_folder=f"{BOOK}/flows")

    batch = pack_repairs(tmp_path, {page: (PageProblem(page, "p"),)}, journey, frozenset({page})).batches[0]

    heading_tokens = -(-len("# ledger.md") // CHARS_PER_TOKEN)
    assert batch.tokens == BOOK_HOLDS * PAGE_TOKENS + 1 + BOOK_HOLDS * PAGE_TOKENS + BOOK_HOLDS * heading_tokens
    assert batch.owns(entry)


def _server_page(root: Path, nodes: dict[str, int]) -> str:
    page = f"{BOOK}/http/ledger-api.md"
    path = root / page
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"### {node}\n\n{'x' * tokens * CHARS_PER_TOKEN}\n\n" for node, tokens in nodes.items())
    _ = path.write_text(f"# Ledger API\n\n## Endpoints\n\n{body}", encoding="utf-8")
    return page


def test_a_page_over_the_ceiling_is_sent_only_the_sections_its_problems_sit_in(tmp_path: Path) -> None:
    page = _server_page(tmp_path, {"list-rows": PAGE_TOKENS, "drop-row": PAGE_TOKENS, "add-row": PAGE_TOKENS})
    problems = (
        PageProblem(page, f"each of 2 claims on {page}#drop-row does not compile", node=f"{page}#drop-row"),
        PageProblem(page, f"each of 3 claims on {page}#add-row does not compile", node=f"{page}#add-row"),
    )

    packed = pack_repairs(tmp_path, {page: problems}, ceiling=BOOK_HOLDS * 5 * PAGE_TOKENS // 2)

    assert packed.oversized_parts == ()
    assert [(repair.sections, repair.problems) for batch in packed.batches for repair in batch.pages] == [
        (("drop-row", "add-row"), tuple(problem.text for problem in problems))
    ]


def test_a_section_alone_over_the_ceiling_is_reported_by_its_heading(tmp_path: Path) -> None:
    page = _server_page(tmp_path, {"list-rows": PAGE_TOKENS, "drop-row": 4 * PAGE_TOKENS})
    problems = (
        PageProblem(page, f"{page}#list-rows is broken", node=f"{page}#list-rows"),
        PageProblem(page, f"{page}#drop-row is broken", node=f"{page}#drop-row"),
    )

    packed = pack_repairs(tmp_path, {page: problems}, ceiling=BOOK_HOLDS * 2 * PAGE_TOKENS)

    assert [repair.sections for batch in packed.batches for repair in batch.pages] == [("list-rows",)]
    assert [large.subject for large in packed.oversized_parts] == [f"{page}, ### drop-row"]
    assert packed.oversized_parts[0].reason.endswith("split the section")
