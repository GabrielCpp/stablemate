"""Phase 3 brings the stack up from the book, runs its flows, charges each failure to a side, and stops once."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from okf_book.support import ExerciseOnly, Reply, ScriptedRunner, always
from ostler.qa.compile import Plan
from ostler.qa.plan_source import Gap
from workhorse.pyflow import driver as pyflow_driver

from workhorse_workflows.okf_book.exercise import flow as exercise_flow
from workhorse_workflows.okf_book.exercise import nodes as exercise_nodes
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side
from workhorse_workflows.okf_book.shared.page_check import BookCompilation
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.workflow import OkfBook
from workhorse_workflows.kit.qa.schemas import StackStatus

App = Callable[[str], Path]
DriveBook = Callable[[OkfBook, ScriptedRunner], object]
PASSED = ScenarioOutcome(status="passed", assertions=1)


def _failed(message: str) -> ScenarioOutcome:
    return ScenarioOutcome(status="failed", assertions=1, failures=1, message=message)


@dataclass
class Stack:
    """The stack, the compiler and the runner phase 3 calls, scripted, with the scenarios each run was asked for."""

    ready: str = "yes"
    gaps: tuple[Gap, ...] = ()
    scenarios: tuple[Scenario, ...] = (Scenario(id="add-an-expense", covers=("okf:tally.md#add",)),)
    outcomes: dict[str, ScenarioOutcome] = field(default_factory=lambda: {"add-an-expense": PASSED})
    runs: list[tuple[str, ...]] = field(default_factory=list[tuple[str, ...]])

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(exercise_flow, "ensure_stack", self.ensure_stack)
        monkeypatch.setattr(exercise_flow, "compile_book", self.compile_book)
        monkeypatch.setattr(exercise_flow, "plan_scenarios", self.plan_scenarios)
        monkeypatch.setattr(exercise_nodes, "plan_scenarios", self.plan_scenarios)
        monkeypatch.setattr(exercise_flow, "run_scenarios", self.run_scenarios)

    def ensure_stack(self, _logger: object, *, repo_dir: str) -> StackStatus:
        return StackStatus(ready="yes" if self.ready == "yes" else "no", notes=f"step 2 of {repo_dir} exited 1")

    def compile_book(self, _root: Path, _services: Iterable[str], _spec: Path) -> BookCompilation:
        return BookCompilation(plan=Plan(source="", gaps=[]), gaps=self.gaps)

    def plan_scenarios(self, _root: Path, _spec: Path) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
        return self.scenarios, ()

    def run_scenarios(self, _root: Path, _spec: Path, only: Iterable[str]) -> RunSummary:
        self.runs.append(tuple(only))
        failing = any(o.status != "passed" for o in self.outcomes.values())
        return RunSummary(status="failed" if failing else "passed", scenarios=self.outcomes, report_path="run.html")


def _operator(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def answer(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        _ = path.write_text("STATUS: ANSWERED\n\nRead.\n", encoding="utf-8")

    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer)
    return asked


def _exercise(app: App, drive_book: DriveBook, runner: ScriptedRunner) -> BookReport:
    result = drive_book(ExerciseOnly(repo_dir=str(app("tally-cli"))), runner)
    assert isinstance(result, BookReport)
    return result


def _runner(pick: Reply = always({"ids": []}), judge: Reply = always({"side": "book", "reason": "stub"})) -> ScriptedRunner:
    return ScriptedRunner({"pick-flows": pick, "judge-failure": judge})


def test_a_runbook_that_cannot_bring_the_stack_up_is_the_books_blocker(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = Stack(ready="no")
    stack.install(monkeypatch)
    asked = _operator(monkeypatch)
    runner = _runner()

    report = _exercise(app, drive_book, runner)

    [blocker] = report.blockers
    assert (blocker.subject, blocker.phase, blocker.side) == ("runbook", Phase.EXERCISE, Side.BOOK)
    assert "exited 1" in blocker.reason
    assert len(asked) == 1
    assert "1 blockers" in asked[0]
    assert runner.total == 0
    assert stack.runs == []


def test_a_book_whose_flows_pass_ends_without_the_operator(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = Stack()
    stack.install(monkeypatch)
    asked = _operator(monkeypatch)
    runner = _runner(pick=always({"ids": ["add-an-expense", "not-a-scenario"]}))

    report = _exercise(app, drive_book, runner)

    assert report.blockers == ()
    assert report.run is not None
    assert report.run.status == "passed"
    assert stack.runs == [("add-an-expense",)]
    assert asked == []


def test_an_empty_pick_runs_every_scenario(app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch) -> None:
    stack = Stack()
    stack.install(monkeypatch)
    _ = _operator(monkeypatch)

    _ = _exercise(app, drive_book, _runner())

    assert stack.runs == [()]


def test_each_failed_scenario_is_charged_to_the_side_its_judge_names(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = Stack(
        scenarios=(Scenario(id="add-an-expense", covers=("okf:tally.md#add",)), Scenario(id="report-totals")),
        outcomes={"add-an-expense": _failed("exit 2, want 0"), "report-totals": _failed("total 12, want 10")},
    )
    stack.install(monkeypatch)
    asked = _operator(monkeypatch)

    def judge(args: dict[str, object]) -> dict[str, object]:
        if args["scenario"] == "add-an-expense":
            return {"side": "app", "reason": "The book says add exits 0 on a new ledger."}
        return {"side": "book", "reason": "The book leaves out the refund rows."}

    runner = _runner(judge=judge)

    report = _exercise(app, drive_book, runner)

    assert [(b.subject, b.side) for b in report.blockers] == [("add-an-expense", Side.APP), ("report-totals", Side.BOOK)]
    [first, _second] = runner.args_of("judge-failure")
    assert (first["covers"], first["message"]) == (["okf:tally.md#add"], "exit 2, want 0")
    assert "report_path" not in first
    assert len(asked) == 1


def test_the_judge_reads_each_failed_check_before_the_runs_own_message(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = FailedCheck(label='created(subject="trip.csv")', expected="true", actual="false")
    outcome = ScenarioOutcome(status="failed", assertions=2, failures=1, message="exit 2", failed_checks=(check,))
    Stack(outcomes={"add-an-expense": outcome}).install(monkeypatch)
    _ = _operator(monkeypatch)
    runner = _runner(judge=always({"side": "book", "reason": "The export writes out.csv."}))

    _ = _exercise(app, drive_book, runner)

    [args] = runner.args_of("judge-failure")
    assert args["message"] == 'created(subject="trip.csv"): expected true, observed false\nexit 2'


def test_the_judge_reads_how_the_command_a_failed_check_observed_ended(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = FailedCheck(label="exit_status(code=0)", expected="0", actual="1",
                        command_ending_text="exit 1, stderr: No module named tally")
    outcome = ScenarioOutcome(status="failed", assertions=1, failures=1, failed_checks=(check,))
    Stack(outcomes={"add-an-expense": outcome}).install(monkeypatch)
    _ = _operator(monkeypatch)
    runner = _runner(judge=always({"side": "book", "reason": "The command cannot find its module."}))

    _ = _exercise(app, drive_book, runner)

    [args] = runner.args_of("judge-failure")
    assert args["message"] == (
        "exit_status(code=0): expected 0, observed 1 "
        "(the command it observed ended with exit 1, stderr: No module named tally)"
    )


def test_an_obligation_that_does_not_compile_is_charged_to_the_side_that_can_fix_it(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    book_gap = Gap("okf:tally.md#add:does:1", "no-verify-declared", "the book declares no check")
    ostler_gap = Gap("okf:tally.md#export:contract", "needs-target-backend", "no backend runs it")
    stack = Stack(gaps=(book_gap, ostler_gap))
    stack.install(monkeypatch)
    _ = _operator(monkeypatch)

    report = _exercise(app, drive_book, _runner())

    assert report.blockers == (
        Blocker(subject=book_gap.obligation_id, phase=Phase.EXERCISE, side=Side.BOOK,
                reason="no-verify-declared: the book declares no check"),
        Blocker(subject=ostler_gap.obligation_id, phase=Phase.EXERCISE, side=Side.OSTLER,
                reason="needs-target-backend: no backend runs it"),
    )
    assert stack.runs == [()]
