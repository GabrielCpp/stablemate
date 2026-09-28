"""One confined writer per surface writes the book, and the run commits, checks, runs and reports it."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
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
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.graph import preflight, registry_graphs, state_graph
from workhorse.runner.failure import BackendInvocationError

from workhorse_workflows.okf_book.main import exercise_book_flow, flow, repair_book_flow, root_book_flow, write_book_flow
from workhorse_workflows.okf_book.main.nodes import turn_budget
from workhorse_workflows.okf_book.main.nodes.source_view import source_view_folder
from workhorse_workflows.okf_book.main.nodes.writer_commands import CHECK_MODULE, EXERCISE_MODULE, OSTLER_MODULE
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.shared.book_run import StackReadiness
from workhorse_workflows.okf_book.workflow import OkfBook, workflow


def _writer(repo: Path, *, stray: bool = False) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        if stray:
            _ = (repo / "tally" / "cli.py").write_text("broken\n", encoding="utf-8")
        return {"value": "wrote tally.md"}

    return ScriptedRunner({"write-book": _reply})


@pytest.fixture
def passing(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", until_noted)


@pytest.mark.usefixtures("passing")
def test_the_writer_runs_in_its_book_and_reads_only_the_surface_source(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    node = runner.nodes[0]
    assert runner.total == 1
    assert node.cwd == str(repo / "docs/features/tally")
    assert node.timeout == float("inf")
    assert node.add_dirs == [str(source_view_folder(repo, "tally"))]
    assert node.agent is not None
    assert node.agent.confined
    assert [command.split()[2] for command in node.agent.commands] == [OSTLER_MODULE, CHECK_MODULE, EXERCISE_MODULE]
    assert runner.args_of("write-book")[0]["book_folder"] == "docs/features/tally"
    assert runner.args_of("write-book")[0]["source_folder"] == "tally"
    assert (source_view_folder(repo, "tally") / "cli.py").is_file()


@pytest.mark.usefixtures("passing")
def test_the_writer_is_told_the_qa_tools_its_scenarios_may_run(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = app("tally-cli")
    config = tmp_path / "config.toml"
    _ = config.write_text('[qa_tools.python3]\ncommand = "python3"\ndescription = "the interpreter"\n', encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    runner = _writer(repo)

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.args_of("write-book")[0]["qa_tools"] == [{"name": "python3", "description": "the interpreter"}]


@pytest.mark.usefixtures("passing")
def test_a_clean_book_is_committed_and_ends_the_run(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert result.blockers == ()
    assert commits(repo)[0] == "docs(tally): write the tally book"
    assert NOTE.strip() in git(repo, "show", "HEAD", "--", PAGE)
    assert result.costs[0].subject == "tally"


@pytest.mark.usefixtures("passing")
def test_a_write_outside_the_book_is_put_back_before_the_commit(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo, stray=True))

    assert git(repo, "status", "--porcelain").strip() == ""
    assert "broken" not in (repo / "tally" / "cli.py").read_text(encoding="utf-8")
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


@pytest.mark.usefixtures("passing")
def test_a_book_commit_the_repo_refuses_waits_for_the_operator_and_is_tried_again(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", refuse_commits_until_answered(repo, asked))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert result.blockers == ()
    assert len(asked) == 1
    assert REFUSAL in asked[0]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


def test_a_book_that_fails_its_run_waits_for_the_operator_once(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    stub_the_run_to(monkeypatch, FAILED)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer(asked))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert len(asked) == 1
    assert isinstance(result, BookReport)
    assert [b.phase for b in result.blockers] == [Phase.EXERCISE]
    assert "scenario add" in result.blockers[0].reason


def test_each_problem_the_check_finds_is_its_own_blocker(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []

    def _problems(_root: Path, _service: str) -> tuple[str, ...]:
        return ("a.md is linked from no page", "b.md: unparsed-check")

    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", _problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer(asked))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert [b.subject for b in result.blockers] == ["tally: a.md is linked from no page", "tally: b.md: unparsed-check"]


def test_a_source_over_the_ceiling_with_no_book_is_a_blocker_and_sends_no_writer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    _ = git(repo, "rm", "-rq", "docs/features/tally")
    _ = git(repo, "commit", "-q", "-m", "drop the book")
    runner = _writer(repo)
    monkeypatch.setattr(turn_budget, "SOURCE_AND_BOOK_CEILING_TOKENS", 10)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.subject, b.side) for b in result.blockers] == [("tally", Side.WORKFLOW)]
    assert "split the surface" in result.blockers[0].reason


def test_an_existing_book_that_checks_and_runs_clean_sends_no_writer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", no_problems)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert result.blockers == ()


def _written_by_the_workflow(repo: Path) -> None:
    _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    _ = git(repo, "add", PAGE)
    _ = git(repo, "commit", "-q", "-m", "docs(tally): write the tally book")


def test_a_book_this_workflow_wrote_that_fails_its_rerun_is_a_blocker_and_sends_no_writer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)
    _written_by_the_workflow(repo)
    stub_the_run_to(monkeypatch, FAILED)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [b.phase for b in result.blockers] == [Phase.EXERCISE]


def test_a_book_this_workflow_wrote_is_run_even_when_its_source_is_over_the_ceiling(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)
    _written_by_the_workflow(repo)
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(turn_budget, "SOURCE_AND_BOOK_CEILING_TOKENS", 10)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert result.blockers == ()


def test_a_book_this_workflow_wrote_that_fails_its_check_is_a_blocker_and_sends_no_writer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)
    _written_by_the_workflow(repo)

    def _problems(_root: Path, _service: str) -> tuple[str, ...]:
        return ("a.md is linked from no page",)

    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", _problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.WRITE, Side.BOOK)]


@pytest.mark.usefixtures("passing")
def test_a_writer_turn_that_ends_without_a_reply_is_a_blocker_and_keeps_its_pages_as_unfinished(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")

    def _dies(_args: dict[str, object]) -> dict[str, object]:
        _ = (repo / PAGE).write_text("half a page\n", encoding="utf-8")
        _ = (repo / "docs/features/tally/draft.md").write_text("a draft\n", encoding="utf-8")
        _ = (repo / "tally" / "cli.py").write_text("broken\n", encoding="utf-8")
        raise BackendInvocationError("no result event")

    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), ScriptedRunner({"write-book": _dies}))

    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.WRITE, Side.WORKFLOW)]
    assert "no result event" in result.blockers[0].reason
    assert commits(repo)[0] == "docs(tally): keep the unfinished tally book"
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == ["docs/features/tally/draft.md", PAGE]
    assert git(repo, "status", "--porcelain").strip() == ""


def test_a_stack_that_cannot_come_up_is_the_apps_blocker_and_sends_no_writer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    runner = _writer(repo)

    def _down(_logger: logging.Logger, _root: Path, _service: str) -> StackReadiness:
        return StackReadiness(up=False, serving=False, notes="port 8080 is taken")

    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _down)
    monkeypatch.setattr(flow, "book_problems", no_problems)
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answer([]))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert [(b.phase, b.side) for b in result.blockers] == [(Phase.EXERCISE, Side.APP)]
    assert "port 8080 is taken" in result.blockers[0].reason


def test_a_run_with_no_surface_fails(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    with pytest.raises(WorkflowFailed, match="no surface"):
        _ = drive_book(OkfBook(repo_dir=str(repo)), ScriptedRunner({}))


@pytest.mark.parametrize(
    "machine", [OkfBook, exercise_book_flow.ExerciseBook, write_book_flow.WriteBook, repair_book_flow.RepairBook, root_book_flow.RootBook]
)
def test_every_transition_says_why(
    machine: type[OkfBook]
    | type[exercise_book_flow.ExerciseBook]
    | type[write_book_flow.WriteBook]
    | type[repair_book_flow.RepairBook]
    | type[root_book_flow.RootBook],
) -> None:
    edges = [edge for node in state_graph(machine).states for edge in node.edges]
    assert edges
    assert [edge.target for edge in edges if not edge.reason] == []


def test_the_dry_run_reads_every_prompt_and_every_transition() -> None:
    graphs = registry_graphs(workflow)
    prompts = {step.name for graph in graphs for node in graph.states for step in node.steps if step.kind == "agent"}
    assert preflight(graphs, workflow.directory()) == []
    assert prompts == {p.relative_to(workflow.directory()).as_posix() for p in workflow.directory().glob("*/prompts/*.md") if not p.name.startswith("_")}
