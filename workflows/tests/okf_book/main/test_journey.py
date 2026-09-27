"""A book's journey pages are the pages its entries page links and its flow pages, and a flow a turn writes new."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages, adds_only_links, journey_pages

BOOK = "docs/features/ledger"


def _page(root: Path, name: str) -> str:
    page = f"{BOOK}/{name}"
    path = root / page
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"# {name}\n", encoding="utf-8")
    return page


def test_the_journey_pages_are_the_linked_and_flow_pages_left_committed_and_a_flow_the_turn_creates(tmp_path: Path) -> None:
    root_page = _page(tmp_path, "ledger.md")
    flows = [_page(tmp_path, f"flows/{name}.md") for name in ("add", "split")]
    _ = _page(tmp_path, "concepts/entry.md")
    _ = (tmp_path / BOOK / "entries.md").write_text("---\ntype: entries\n---\n\n- [Ledger](ledger.md)\n", encoding="utf-8")

    journey = journey_pages(tmp_path, "ledger", frozenset({flows[1]}))

    assert journey == JourneyPages(pages=(root_page, flows[0]), flow_folder=f"{BOOK}/flows")
    assert journey.owns(f"{BOOK}/flows/new.md", frozenset({f"{BOOK}/flows/new.md"}))
    assert not journey.owns(f"{BOOK}/flows/new.md")
    assert not journey.owns(flows[1], frozenset({f"{BOOK}/flows/new.md"}))
    assert not journey.owns(f"{BOOK}/concepts/entry.md")


@pytest.mark.parametrize(
    ("after", "only_links"),
    [
        ("# Ledger\n\n- [Add](flows/add.md)\n\nprose\n", True),
        ("# Ledger\n\nprose\n\n- [Add](flows/add.md)\n- [Split](flows/split.md)\n", True),
        ("# Ledger\n\nprose, see [Add](flows/add.md)\n", False),
        ("# Ledger\n\nprose\nmore prose\n", False),
        ("# Ledger\n", False),
    ],
)
def test_an_entry_page_change_is_only_links_when_every_added_line_holds_a_link_and_no_line_changed(
    after: str, only_links: bool
) -> None:
    assert adds_only_links("# Ledger\n\nprose\n", after) is only_links


def test_a_writer_reads_a_flow_page_whole_and_only_the_headings_of_an_entry_page() -> None:
    journey = JourneyPages(pages=(f"{BOOK}/ledger.md", f"{BOOK}/flows/add.md"), flow_folder=f"{BOOK}/flows")
    text = "---\ntitle: x\n---\n# Ledger\n\nprose\n## Add\nmore\n"

    assert journey.read_by_writer(f"{BOOK}/flows/add.md", text) == text
    assert journey.read_by_writer(f"{BOOK}/ledger.md", text) == "# Ledger\n## Add"
