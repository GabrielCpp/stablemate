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

from workhorse_workflows.okf_book.main import flow, repair_book_flow
from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.repair_batches import PageRepair, pack_repairs
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


OTHER_PAGE = "docs/features/tally/concepts/ledger-file.md"


def _another_page_once_noted(root: Path, service: str) -> tuple[PageProblem, ...]:
    return _pages_until_noted(root, service) or (PageProblem(OTHER_PAGE, "ledger-file.md needs a note"),)


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
    oversized_pages = [b for b in result.blockers if b.side is Side.WORKFLOW]
    assert [(b.phase, b.subject) for b in oversized_pages] == [(Phase.WRITE, f"tally: {PAGE}, the lines under no ### heading")]
    assert oversized_pages[0].reason.endswith("split the section")


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
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))


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


def _a_book_this_workflow_wrote(app: App) -> Path:
    repo = app("tally-cli")
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    _ = git(repo, "commit", "-qam", "docs(tally): write the tally book")
    return repo


@pytest.mark.usefixtures("failing_add")
def test_a_book_this_workflow_wrote_that_fails_its_run_is_a_blocker_and_no_repair(app: App, drive_book: DriveBook) -> None:
    repo = _a_book_this_workflow_wrote(app)
    runner = _repairer(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.EXERCISE, Side.BOOK)]
    assert commits(repo)[0] == "docs(tally): write the tally book"


OUTSIDE_EDIT = "\nan edit outside the batch\n"
FLOW_PAGE = "docs/features/tally/flows/track-a-trip.md"
NEW_FLOW = "docs/features/tally/flows/split-a-bill.md"


def _repairer_also_editing(repo: Path, *pages: str) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        for page in pages:
            text = (repo / page).read_text(encoding="utf-8") if (repo / page).is_file() else ""
            _ = (repo / page).write_text(text + OUTSIDE_EDIT, encoding="utf-8")
        return {"value": f"repaired {PAGE}"}

    return ScriptedRunner({"repair-pages": _reply})


def _off_journey_until_noted(root: Path, service: str) -> tuple[PageProblem, ...]:
    return tuple(PageProblem(p.page, p.text, needs_journey=True) for p in _pages_until_noted(root, service))


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_page_the_turn_changed_outside_its_batch_is_put_back(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _repairer_also_editing(repo, OTHER_PAGE, FLOW_PAGE)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.args_of("repair-pages")[0]["journey_pages"] == []
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert OUTSIDE_EDIT.strip() not in (repo / OTHER_PAGE).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_batch_with_a_page_off_the_journey_owns_the_entry_and_flow_pages_and_a_new_flow(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", _off_journey_until_noted)
    runner = _repairer_also_editing(repo, OTHER_PAGE, FLOW_PAGE, NEW_FLOW)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.args_of("repair-pages")[0]["journey_pages"] == [PAGE, FLOW_PAGE]
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == sorted([PAGE, FLOW_PAGE, NEW_FLOW])
    assert OUTSIDE_EDIT.strip() not in (repo / OTHER_PAGE).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


def _writes_a_flow_then_notes(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        if (repo / NEW_FLOW).is_file():
            _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        else:
            _ = (repo / NEW_FLOW).write_text(OUTSIDE_EDIT, encoding="utf-8")
        return {"value": f"repaired {PAGE}"}

    return ScriptedRunner({"repair-pages": _reply})


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_later_round_keeps_the_journey_pages_the_first_round_planned(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", _off_journey_until_noted)
    runner = _writes_a_flow_then_notes(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.total == 2
    assert [args["journey_pages"] for args in runner.args_of("repair-pages")] == [[PAGE, FLOW_PAGE], [PAGE, FLOW_PAGE]]
    assert (repo / NEW_FLOW).is_file()


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_turn_that_changed_a_page_someone_left_uncommitted_waits_for_the_operator(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer(asked))
    _ = (repo / OTHER_PAGE).write_text((repo / OTHER_PAGE).read_text(encoding="utf-8") + "their edit\n", encoding="utf-8")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _repairer_also_editing(repo, OTHER_PAGE))

    assert isinstance(result, BookReport)
    assert len(asked) == 1
    assert OTHER_PAGE in asked[0]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
    assert git(repo, "status", "--porcelain").split() == ["M", OTHER_PAGE]


LINK_LINE = "- [Track a trip](flows/track-a-trip.md)\n"


def _flow_until_noted(root: Path, _service: str) -> tuple[PageProblem, ...]:
    noted = NOTE.strip() in (root / FLOW_PAGE).read_text(encoding="utf-8")
    return () if noted else (PageProblem(FLOW_PAGE, "track-a-trip.md needs a note", needs_journey=True),)


def _notes_the_flow_and_adds_to_the_entry_page(repo: Path, addition: str) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        for page, text in ((FLOW_PAGE, NOTE), (PAGE, addition)):
            _ = (repo / page).write_text((repo / page).read_text(encoding="utf-8") + text, encoding="utf-8")
        return {"value": f"repaired {FLOW_PAGE}"}

    return ScriptedRunner({"repair-pages": _reply})


@pytest.mark.usefixtures("over_the_ceiling")
@pytest.mark.parametrize(("addition", "kept"), [(LINK_LINE, True), (LINK_LINE + OUTSIDE_EDIT, False)])
def test_a_turn_keeps_an_entry_page_it_only_added_link_lines_to(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch, addition: str, kept: bool
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", _flow_until_noted)
    committed = (repo / PAGE).read_text(encoding="utf-8")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _notes_the_flow_and_adds_to_the_entry_page(repo, addition))

    assert isinstance(result, BookReport)
    assert (LINK_LINE.strip() in (repo / PAGE).read_text(encoding="utf-8")) is kept
    assert kept or (repo / PAGE).read_text(encoding="utf-8") == committed
    assert git(repo, "status", "--porcelain").strip() == ""
