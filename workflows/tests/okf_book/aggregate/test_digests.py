"""Each judged page and each headed section in it is keyed to a digest of its own text."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.aggregate.digests import node_digests

PAGE = "docs/features/tally/concepts/ledger-file.md"
TEXT = "---\ntype: concept\n---\n\n# The ledger file\n\nA.\n\n## Kept\n\nIt stays.\n\n## Tail\n\nTally keeps a ledger.\n"


def _write(root: Path, text: str) -> None:
    path = root / PAGE
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def test_the_page_and_each_headed_section_get_a_digest(tmp_path: Path) -> None:
    _write(tmp_path, TEXT)

    assert set(node_digests(tmp_path, [PAGE])) == {PAGE, f"{PAGE}#the-ledger-file", f"{PAGE}#kept", f"{PAGE}#tail"}


def test_an_edit_changes_the_digest_of_its_section_and_every_section_holding_it_only(tmp_path: Path) -> None:
    _write(tmp_path, TEXT)
    before = node_digests(tmp_path, [PAGE])
    _write(tmp_path, TEXT + "More.\n")

    after = node_digests(tmp_path, [PAGE])

    assert {node for node in before if before[node] != after[node]} == {PAGE, f"{PAGE}#the-ledger-file", f"{PAGE}#tail"}
