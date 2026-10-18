"""The entry of a surface names its source folder, and one that names none is a blocker a person can act on."""
from __future__ import annotations

import pytest
from okf_book.main.tally import PASSED, App, DriveBook, stopping_operator, stub_the_run_to
from okf_book.support import ScriptedRunner
from workhorse.pyflow import park as pyflow_park

from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.workflow import OkfBook


def test_an_entry_in_no_folder_of_the_repository_is_a_blocker_that_names_the_nearest_folder(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    stub_the_run_to(monkeypatch, PASSED)
    ghost = Surface(service="ghost", kind=SurfaceKind.HTTP, entry="tally/services/ghost/main.py")
    runner = ScriptedRunner({})
    monkeypatch.setattr(pyflow_park, "wait_for_answer", stopping_operator([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(ghost,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.WRITE, Side.WORKFLOW)]
    reason = result.blockers[0].reason
    assert "`tally/services/ghost/main.py`" in reason
    assert "source folder, relative to the repository root" in reason
    assert "nearest folder that exists is `tally/`" in reason
