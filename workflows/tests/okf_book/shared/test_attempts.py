"""A run keeps the nodes its judges cleared across jobs, one entry per node."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.shared.attempts import ClearedNode, read_cleared, record_cleared


def test_a_run_with_no_cleared_record_has_no_cleared_nodes(tmp_path: Path) -> None:
    assert read_cleared(tmp_path) == ()


def test_a_node_cleared_again_replaces_its_entry_and_keeps_the_others(tmp_path: Path) -> None:
    kept = ClearedNode(node="a.md", digest="1")
    record_cleared(tmp_path, (kept, ClearedNode(node="b.md", digest="1")))
    record_cleared(tmp_path, (ClearedNode(node="b.md", digest="2", claims=("It works.",)),))

    assert read_cleared(tmp_path) == (kept, ClearedNode(node="b.md", digest="2", claims=("It works.",)))
