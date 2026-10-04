"""A book over one writer's ceiling with no entry page stops at the operator and sends no repair."""
from __future__ import annotations

import pytest
from okf_book.main.tally import TALLY, App, DriveBook, stopping_operator
from okf_book.support import ScriptedRunner, git
from workhorse.pyflow import park as pyflow_park

from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.workflow import OkfBook


def test_a_source_over_the_ceiling_whose_book_has_no_entry_page_is_a_blocker_and_sends_no_repair(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    _ = git(repo, "rm", "-q", "docs/features/tally/tally.md")
    _ = git(repo, "commit", "-q", "-m", "drop the command page")
    runner = ScriptedRunner({})
    monkeypatch.setattr(turn_budget, "SOURCE_AND_BOOK_CEILING_TOKENS", 10)
    monkeypatch.setattr(pyflow_park, "wait_for_answer", stopping_operator([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    reasons = [b.reason for b in result.blockers if b.subject == "tally"]
    assert len(reasons) == 1
    assert "no cli, server or screen page" in reasons[0] and "split the surface" in reasons[0]
