"""A stub page cites its surface's entry, and a retry after a crash finishes the page it left."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.stubs import entry_slugs, write_stubs
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


def test_the_reusable_slugs_are_the_surfaces_entry_points_and_nothing_else(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    slugs = entry_slugs(repo, TALLY)
    assert {"init", "add"} <= set(slugs)
    assert "ledger-file" not in slugs
    assert entry_slugs(repo, Surface(service="nothing", kind=SurfaceKind.CLI, entry="x.py")) == ()
    assert entry_slugs(repo, Surface(service="tally", kind=SurfaceKind.WEB, entry="x.py")) == ()
