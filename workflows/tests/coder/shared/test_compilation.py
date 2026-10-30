"""The book's compile, read as the gaps the story's own pages owe."""
from __future__ import annotations

import logging
from pathlib import Path

from _compiling_book import LIST_ENTRIES, write_packet

from workhorse_workflows.coder.shared.compilation import compile_gaps

LOG = logging.getLogger("test")
OTHER_PAGE = "docs/services/ledger/entries.md"


def test_a_surface_with_no_runbook_driver_is_a_gap_on_a_touched_page(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=False)

    result = compile_gaps(LOG, spec_dir=str(spec), story="STORY-1", pages=(LIST_ENTRIES,))

    assert [gap.split(" ")[0] for gap in result.gaps] == ["uncompilable-claim"], result.gaps
    assert f"okf:{LIST_ENTRIES}:does:1" in result.gaps[0], result.gaps


def test_a_gap_on_a_page_the_story_did_not_touch_is_not_reported(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=False)

    result = compile_gaps(LOG, spec_dir=str(spec), story="STORY-1", pages=(OTHER_PAGE,))

    assert result.gaps == []


def test_a_book_that_compiles_has_no_gap(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=True)

    result = compile_gaps(LOG, spec_dir=str(spec), story="STORY-1", pages=(LIST_ENTRIES,))

    assert result.gaps == []
