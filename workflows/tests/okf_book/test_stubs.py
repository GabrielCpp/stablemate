"""A stub page cites its surface's entry, and a retry after a crash finishes the page it left."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.stubs import write_stubs
from workhorse_workflows.okf_book.surface import EntryPoint, Surface, SurfaceKind

TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
POINTS = (EntryPoint(slug="init", title="Init"), EntryPoint(slug="add", title="Add"))


def test_a_retry_cites_the_entry_a_crash_left_uncited(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    shutil.rmtree(repo / "docs/features/tally")
    links = write_stubs(repo, TALLY, POINTS)
    page = repo / "docs/features/tally" / links[0].target.partition("#")[0]
    cited = page.read_text(encoding="utf-8")
    _ = page.write_text(cited.replace(f"- code: {TALLY.entry}\n", "- code:\n", 1), encoding="utf-8")

    _ = write_stubs(repo, TALLY, POINTS)

    assert page.read_text(encoding="utf-8") == cited
    assert cited.count(f"- code: {TALLY.entry}\n") == 1
