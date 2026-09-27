"""A book over the ceiling one writer reads, or one this workflow wrote that fails its run, is repaired a batch of problem pages at a time."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import (
    App,
    DriveBook,
    FAILED,
    NOTE,
    PAGE,
    PASSED,
    REFUSAL,
    TALLY,
    answer,
    no_problems,
    refuse_commits_until_answered,
    stub_the_run_to,
    until_noted,
)
from okf_book.support import ScriptedRunner, commits, git
from workhorse.pyflow import driver as pyflow_driver
from workhorse.runner.failure import BackendInvocationError

from workhorse_workflows.okf_book.main import exercise_book_flow, flow, repair_book_flow
from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.repair_batches import PageRepair
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.main.nodes.writer_commands import CHECK_MODULE, EXERCISE_MODULE, OSTLER_MODULE
from workhorse_workflows.okf_book.main.repair_book_flow import REPAIR_ROUNDS
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
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
    assert [command.split()[2] for command in node.agent.commands] == [OSTLER_MODULE, CHECK_MODULE, EXERCISE_MODULE]
    assert commits(repo)[:2] == ["docs(tally): repair pages of the tally book", "docs(tally): root the tally book"]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert "](tally.md)" in (repo / "docs/features/tally/entries.md").read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


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
    failed = [b for b in result.blockers if b.side is Side.WORKFLOW]
    assert runner.total == REPAIR_ROUNDS
    assert [b.phase for b in failed] == [Phase.WRITE]
    assert failed[0].reason.count("no result event") == REPAIR_ROUNDS


ADD = Scenario(id="tally-add", covers=(f"okf:{PAGE}#add:does:1",))
REFUSED = FailedCheck(label="adds an expense", expected="0", actual="1")
FAILED_ADD = FAILED.model_copy(
    update={"summary": RunSummary(status="failed", scenarios={ADD.id: ScenarioOutcome(status="failed", failed_checks=(REFUSED,))})}
)


def _planned(_root: Path, _spec: Path) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
    return (ADD,), ()


def _no_pages(_root: Path, _service: str) -> tuple[PageProblem, ...]:
    return ()


@pytest.fixture
def failing_add(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_the_run_to(monkeypatch, FAILED_ADD)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(flow, "plan_scenarios", _planned)
    monkeypatch.setattr(repair_book_flow, "page_problems", _no_pages)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))


def _repaired_once_on_the_failed_page(runner: ScriptedRunner, result: object) -> None:
    assert runner.total == 1
    sent = TypeAdapter(tuple[PageRepair, ...]).validate_python(runner.args_of("repair-pages")[0]["pages"])
    ran = "the run of scenario tally-add failed: adds an expense: expected 0, observed 1"
    assert [(repair.page, repair.problems) for repair in sent] == [(PAGE, (ran,))]
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

    _repaired_once_on_the_failed_page(runner, result)


@pytest.mark.usefixtures("failing_add")
def test_a_book_this_workflow_wrote_that_fails_its_run_is_repaired_once_on_the_pages_that_failed(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    _ = git(repo, "commit", "-qam", "docs(tally): write the tally book")
    runner = _repairer(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    _repaired_once_on_the_failed_page(runner, result)


def _failing_add_observing(actual: str) -> ExerciseResult:
    refused = FailedCheck(label="adds an expense", expected="0", actual=actual)
    outcome = ScenarioOutcome(status="failed", failed_checks=(refused,))
    return FAILED.model_copy(update={"summary": RunSummary(status="failed", scenarios={ADD.id: outcome})})


def _runs_in_turn(monkeypatch: pytest.MonkeyPatch, *results: ExerciseResult) -> None:
    runs = iter(results)

    def _run(_root: Path, _spec: Path, _gaps: tuple[str, ...], _serving: bool) -> ExerciseResult:
        return next(runs)

    monkeypatch.setattr(exercise_book_flow, "run_plan", _run)


def _a_book_this_workflow_wrote(app: App) -> Path:
    repo = app("tally-cli")
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    _ = git(repo, "commit", "-qam", "docs(tally): write the tally book")
    return repo


@pytest.mark.usefixtures("failing_add")
def test_a_run_that_fails_differently_after_a_repair_is_repaired_again(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _a_book_this_workflow_wrote(app)
    runner = _repairer(repo)
    _runs_in_turn(monkeypatch, _failing_add_observing("1"), _failing_add_observing("2"), PASSED)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 2
    assert isinstance(result, BookReport)
    assert result.blockers == ()


@pytest.mark.usefixtures("failing_add")
def test_a_run_that_keeps_failing_differently_is_a_blocker_once_its_repairs_run_out(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _a_book_this_workflow_wrote(app)
    runner = _repairer(repo)
    _runs_in_turn(monkeypatch, *(_failing_add_observing(str(n)) for n in range(flow.RUN_REPAIRS + 1)))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == flow.RUN_REPAIRS
    assert isinstance(result, BookReport)
    assert [b.phase for b in result.blockers] == [Phase.EXERCISE]


@pytest.mark.usefixtures("failing_add")
def test_a_check_problem_the_repaired_book_no_longer_has_is_no_blocker(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _a_book_this_workflow_wrote(app)
    checks = iter((("a.md is linked from no page",), ()))

    def _problems(_root: Path, _service: str) -> tuple[str, ...]:
        return next(checks)

    monkeypatch.setattr(flow, "book_problems", _problems)
    _runs_in_turn(monkeypatch, FAILED_ADD, PASSED)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _repairer(repo))

    assert isinstance(result, BookReport)
    assert result.blockers == ()
