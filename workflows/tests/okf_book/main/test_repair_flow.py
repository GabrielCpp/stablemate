"""A book over the ceiling one writer reads is repaired a batch of problem pages at a time, and a book this workflow wrote that fails its run is a blocker."""
from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import (
    App,
    DriveBook,
    FAILED,
    FLOW_PAGE,
    NOTE,
    OTHER_PAGE,
    OUTSIDE_EDIT,
    PAGE,
    REFUSAL,
    TALLY,
    answering_operator,
    no_problems,
    page_problems_until_noted,
    refuse_commits_until_answered,
    stub_a_book_sent_to_repair,
    repairer_also_editing,
    stub_the_run_to,
)
from okf_book.support import ScriptedRunner, commits, git
from workhorse.pyflow import Continue, Done
from workhorse.pyflow import driver as pyflow_driver
from workhorse.runner.failure import BackendInvocationError

from workhorse_workflows.okf_book.main import flow, repair_book_flow, root_book_flow
from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import PageRepair
from workhorse_workflows.okf_book.main.nodes.repair_batches import pack_repairs
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.main.nodes.writer_commands import CHECK_MODULE, EXERCISE_MODULE, OSTLER_MODULE
from workhorse_workflows.okf_book.main.repair_book_flow import REPAIR_ROUNDS
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook


def _repairer(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        _ = (repo / "tally" / "cli.py").write_text("broken\n", encoding="utf-8")
        return {"value": "repaired tally.md"}

    return ScriptedRunner({"repair-pages": _reply})


@pytest.fixture
def over_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_a_book_sent_to_repair(monkeypatch)


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
    assert [command.split()[2] for command in node.agent.commands] == [OSTLER_MODULE, CHECK_MODULE, EXERCISE_MODULE]
    assert commits(repo)[:2] == ["docs(tally): repair pages of the tally book", "docs(tally): root the tally book"]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert "](tally.md)" in (repo / "docs/features/tally/entries.md").read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_retried_root_still_commits_the_entries_page_an_earlier_try_wrote(app: App) -> None:
    """No later state commits the entries page, so a try stopped between its write and its commit must not read as rooted."""
    repo = app("tally-cli")
    book = root_book_flow.RootBook(repo_dir=str(repo), service="tally")

    first = book.root_book(uncommitted_at_start=())
    written = (repo / "docs/features/tally/entries.md").read_text(encoding="utf-8")
    retried = book.root_book(uncommitted_at_start=())

    assert isinstance(first, Continue)
    assert isinstance(retried, Continue)
    assert (first.state, retried.state) == ("commit_root", "commit_root")
    assert retried.params == first.params
    assert (repo / "docs/features/tally/entries.md").read_text(encoding="utf-8") == written


def test_an_entries_page_someone_left_uncommitted_roots_the_book_as_it_is(app: App) -> None:
    repo = app("tally-cli")
    page = "docs/features/tally/entries.md"
    _ = (repo / page).write_text("---\ntype: entries\n---\n", encoding="utf-8")
    book = root_book_flow.RootBook(repo_dir=str(repo), service="tally")

    assert isinstance(book.root_book(uncommitted_at_start=(page,)), Done)


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_commit_the_repo_refuses_waits_for_the_operator_and_is_tried_again(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", refuse_commits_until_answered(repo, asked))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _repairer(repo))

    assert isinstance(result, BookReport)
    assert len(asked) == 1
    assert REFUSAL in asked[0]
    assert commits(repo)[:2] == ["docs(tally): repair pages of the tally book", "docs(tally): root the tally book"]


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
    workflow_blockers = [b for b in result.blockers if b.side is Side.WORKFLOW]
    assert runner.total == REPAIR_ROUNDS
    assert [b.phase for b in workflow_blockers] == [Phase.WRITE]
    assert workflow_blockers[0].reason.count("no result event") == REPAIR_ROUNDS


def _another_page_once_noted(root: Path, service: str) -> tuple[PageProblem, ...]:
    return page_problems_until_noted(root, service) or (PageProblem(OTHER_PAGE, "ledger-file.md needs a note"),)


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_problem_a_later_round_finds_on_a_page_outside_the_first_round_is_not_repaired(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _repairer(repo)
    monkeypatch.setattr(repair_book_flow, "page_problems", _another_page_once_noted)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.total == 1
    sent = TypeAdapter(tuple[PageRepair, ...]).validate_python(runner.args_of("repair-pages")[0]["pages"])
    assert [repair.page for repair in sent] == [PAGE]


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_page_too_large_for_one_writer_is_sent_no_turn_and_is_a_blocker_on_the_workflow(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _repairer(repo)
    monkeypatch.setattr(repair_book_flow, "pack_repairs", partial(pack_repairs, ceiling=1))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.total == 0
    workflow_blockers = [b for b in result.blockers if b.side is Side.WORKFLOW]
    assert [(b.phase, b.subject) for b in workflow_blockers] == [(Phase.WRITE, f"tally: {PAGE}, the lines under no ### heading")]
    assert workflow_blockers[0].reason.endswith("split the section")


ADD = Scenario(id="tally-add", covers=(f"okf:{PAGE}#add:does:1",))
FAILED_ADD_CHECK = FailedCheck(label="adds an expense", expected="0", actual="1")
FAILED_ADD = FAILED.model_copy(
    update={"summary": RunSummary(status="failed", scenarios={ADD.id: ScenarioOutcome(status="failed", failed_checks=(FAILED_ADD_CHECK,))})}
)


def _planned(_root: Path, _spec: Path) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
    return (ADD,), ()


def _no_page_problems(_root: Path, _service: str) -> tuple[PageProblem, ...]:
    return ()


@pytest.fixture
def failing_add(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_the_run_to(monkeypatch, FAILED_ADD)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(flow, "plan_scenarios", _planned)
    monkeypatch.setattr(repair_book_flow, "page_problems", _no_page_problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answering_operator([]))


def _assert_repaired_once_on_the_failed_page(runner: ScriptedRunner, result: object) -> None:
    assert runner.total == 1
    sent = TypeAdapter(tuple[PageRepair, ...]).validate_python(runner.args_of("repair-pages")[0]["pages"])
    run_failure = "the run of scenario tally-add failed: adds an expense: expected 0, observed 1"
    assert [(repair.page, repair.problems) for repair in sent] == [(PAGE, (run_failure,))]
    assert runner.args_of("repair-pages")[0]["exercise"]
    assert isinstance(result, BookReport)
    assert [b.phase for b in result.blockers] == [Phase.EXERCISE]


@pytest.mark.usefixtures("failing_add")
def test_an_existing_book_over_the_ceiling_that_fails_its_run_is_repaired_once_on_the_pages_that_failed(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _repairer(repo)
    monkeypatch.setattr(turn_budget, "SOURCE_AND_BOOK_CEILING_TOKENS", 10)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    _assert_repaired_once_on_the_failed_page(runner, result)


def _repo_with_a_book_this_workflow_wrote(app: App) -> Path:
    repo = app("tally-cli")
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    _ = git(repo, "commit", "-qam", "docs(tally): write the tally book")
    return repo


@pytest.mark.usefixtures("failing_add")
def test_a_book_this_workflow_wrote_that_fails_its_run_is_a_blocker_and_no_repair(app: App, drive_book: DriveBook) -> None:
    repo = _repo_with_a_book_this_workflow_wrote(app)
    runner = _repairer(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.EXERCISE, Side.BOOK)]
    assert commits(repo)[0] == "docs(tally): write the tally book"


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_page_the_turn_changed_outside_its_batch_is_put_back(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = repairer_also_editing(repo, OTHER_PAGE, FLOW_PAGE)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.args_of("repair-pages")[0]["journey_pages"] == []
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert OUTSIDE_EDIT.strip() not in (repo / OTHER_PAGE).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_turn_that_changed_a_page_someone_left_uncommitted_waits_for_the_operator(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answering_operator(asked))
    _ = (repo / OTHER_PAGE).write_text((repo / OTHER_PAGE).read_text(encoding="utf-8") + "their edit\n", encoding="utf-8")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), repairer_also_editing(repo, OTHER_PAGE))

    assert isinstance(result, BookReport)
    assert len(asked) == 1
    assert OTHER_PAGE in asked[0]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert git(repo, "status", "--porcelain").split() == ["M", OTHER_PAGE]
