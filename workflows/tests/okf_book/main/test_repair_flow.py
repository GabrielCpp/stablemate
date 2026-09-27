"""A book over the ceiling one writer reads is rooted, then repaired a batch of problem pages at a time."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import App, DriveBook, NOTE, PAGE, PASSED, TALLY, answer, stub_the_run_to, until_noted
from okf_book.support import ScriptedRunner, commits, git
from workhorse.pyflow import driver as pyflow_driver
from workhorse.runner.failure import BackendInvocationError

from workhorse_workflows.okf_book.main import flow, repair_book_flow
from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.repair_batches import PageRepair
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.main.nodes.writer_commands import CHECK_MODULE, OSTLER_MODULE
from workhorse_workflows.okf_book.main.repair_book_flow import REPAIR_ROUNDS
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.workflow import OkfBook


def _repairer(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        _ = (repo / "tally" / "cli.py").write_text("broken\n", encoding="utf-8")
        return {"value": "repaired tally.md"}

    return ScriptedRunner({"repair-pages": _reply})


def _pages_until_noted(root: Path, _service: str) -> tuple[PageProblem, ...]:
    return () if NOTE.strip() in (root / PAGE).read_text(encoding="utf-8") else (PageProblem(PAGE, "tally.md needs a note"),)


@pytest.fixture
def over_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", until_noted)
    monkeypatch.setattr(turn_budget, "SOURCE_AND_BOOK_CEILING_TOKENS", 10)
    monkeypatch.setattr(repair_book_flow, "page_problems", _pages_until_noted)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))


@pytest.mark.usefixtures("over_the_ceiling")
def test_an_existing_book_over_the_ceiling_is_rooted_repaired_page_by_page_and_run(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _repairer(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert result.blockers == ()
    assert runner.total == 1
    sent = TypeAdapter(tuple[PageRepair, ...]).validate_python(runner.args_of("repair-pages")[0]["pages"])
    assert [(repair.page, repair.problems) for repair in sent] == [(PAGE, ("tally.md needs a note",))]
    node = runner.nodes[0]
    assert node.agent is not None
    assert [command.split()[2] for command in node.agent.commands] == [OSTLER_MODULE, CHECK_MODULE]
    assert commits(repo)[:2] == ["docs(tally): repair pages of the tally book", "docs(tally): root the tally book"]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert "](tally.md)" in (repo / "docs/features/tally/entries.md").read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_page_someone_left_uncommitted_is_sent_to_no_repair_turn_and_stays_theirs(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _repairer(repo)
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + "their edit\n", encoding="utf-8")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.total == 0
    assert git(repo, "status", "--porcelain").split() == ["M", PAGE]
    assert "their edit" in (repo / PAGE).read_text(encoding="utf-8")


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_repair_turn_that_ends_without_a_reply_is_a_blocker_and_the_rounds_still_end(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    def _dies(_args: dict[str, object]) -> dict[str, object]:
        raise BackendInvocationError("no result event")

    runner = ScriptedRunner({"repair-pages": _dies})

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    failed = [b for b in result.blockers if b.side is Side.WORKFLOW]
    assert runner.total == REPAIR_ROUNDS
    assert [b.phase for b in failed] == [Phase.WRITE]
    assert failed[0].reason.count("no result event") == REPAIR_ROUNDS
