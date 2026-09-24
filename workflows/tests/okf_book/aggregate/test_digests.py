"""Each judged page and each headed section in it is keyed to a digest of its own text."""
from __future__ import annotations

from pathlib import Path

from ostler.stamp import stamp_page

from workhorse_workflows.okf_book.aggregate.digests import node_digests, node_digests_on_pages_of

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


def test_the_pages_the_nodes_sit_on_are_digested_and_a_deleted_one_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, TEXT)

    assert node_digests_on_pages_of(tmp_path, [f"{PAGE}#kept", f"{PAGE}#tail", "docs/features/tally/gone.md#x"]) == node_digests(tmp_path, [PAGE])


def test_a_stamp_on_a_code_bullet_leaves_every_digest_as_it_was(tmp_path: Path) -> None:
    _write(tmp_path, TEXT + "\n- code: `tally/ledger.py::load`\n")
    source = tmp_path / "tally/ledger.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def load():\n    pass\n", encoding="utf-8")
    before = node_digests(tmp_path, [PAGE])

    assert stamp_page(tmp_path, tmp_path / "docs/features", PAGE).changed

    assert node_digests(tmp_path, [PAGE]) == before
