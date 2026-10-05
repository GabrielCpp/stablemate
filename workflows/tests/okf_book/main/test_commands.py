"""The commands the owner runs read the command state the run writes."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from workhorse.config_run import AgentResilience
from workhorse.testing import make_git_repo

from workhorse_workflows.okf_book.main.nodes import check_pages, exercise, writer_stack
from workhorse_workflows.okf_book.main.nodes.check_pages import NO_PROBLEMS_LINE, checked, run_check, scoped_problems
from workhorse_workflows.okf_book.main.nodes.check_pages import USAGE as CHECK_USAGE
from workhorse_workflows.okf_book.main.nodes.exercise import USAGE as EXERCISE_USAGE
from workhorse_workflows.okf_book.main.nodes.exercise import run_exercise
from workhorse_workflows.okf_book.main.nodes.writer_jobs import Start, Work, finish_job
from workhorse_workflows.okf_book.main.nodes.writer_stack import KeptStack
from workhorse_workflows.okf_book.main.nodes.writer_ostler import INDEX_DIR_REFUSED, USAGE as OSTLER_USAGE, run_ostler
from workhorse_workflows.okf_book.main.nodes.turn_budget import PROMPT_AND_SKILL_ALLOWANCE_TOKENS, folder_tokens
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_MODULE,
    CHECK_AND_SCENARIO_RUN_CAP,
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    CommandOutput,
    OSTLER_MODULE,
    OSTLER_RUN_CAP,
    OSTLER_RUNS_SPENT_MESSAGE,
    WriterCommandState,
    check_command,
    exercise_command,
    ostler_command,
    command_state_path,
    read_command_state,
    write_command_state,
)


def test_the_command_state_reads_back_what_the_run_wrote(tmp_path: Path) -> None:
    state = WriterCommandState(root=tmp_path / "repo", service="tally")

    path = write_command_state(tmp_path / "run", state)

    assert path == command_state_path(tmp_path / "run")
    assert read_command_state(path) == state


def test_each_command_runs_this_interpreter_on_the_command_state(tmp_path: Path) -> None:
    path = str(command_state_path(tmp_path))

    assert check_command(tmp_path) == f"{sys.executable} -m {CHECK_MODULE} {path}"
    assert exercise_command(tmp_path).split()[-1] == path
    assert ostler_command(tmp_path) == f"{sys.executable} -m {OSTLER_MODULE} {path}"


def test_the_writer_waits_on_an_exercise_past_the_cli_default_and_inside_the_silence_budget(tmp_path: Path) -> None:
    request = WriterRequest(
        surface=Surface(service="tally", kind=SurfaceKind.CLI, entry="tally"),
        repo_root=tmp_path,
        book_folder="docs",
        source_folder="src",
        source_view=tmp_path,
        ostler_command_line=ostler_command(tmp_path),
        check_command_line=check_command(tmp_path),
        exercise_command_line=exercise_command(tmp_path),
        qa_tools=(),
    )

    limit = request.profile.command_timeout_s

    assert limit is not None
    assert 120 < limit < AgentResilience().silence_timeout_s


def test_each_command_names_its_usage_without_one_command_state() -> None:
    assert run_check([]) == CommandOutput(2, (CHECK_USAGE,))
    assert run_exercise([]) == CommandOutput(2, (EXERCISE_USAGE,))


def _stub_exercise(
    monkeypatch: pytest.MonkeyPatch, stack: StackReadiness, outcome: CompileOutcome | None = None
) -> list[StackReadiness]:
    released: list[StackReadiness] = []

    def _compile(*_args: object) -> CompileOutcome:
        return outcome or CompileOutcome(gaps=(), planned=True)

    def _bring_up(*_args: object) -> StackReadiness:
        return stack

    def _run_plan(*_args: object) -> ExerciseResult:
        raise RuntimeError("the runner died")

    def _release(_logger: logging.Logger, readiness: StackReadiness) -> None:
        if readiness.owned:
            released.append(readiness)

    def _stack_pages(*_args: object) -> tuple[str, ...]:
        return ()

    monkeypatch.setattr(exercise, "compile_scenarios", _compile)
    monkeypatch.setattr(writer_stack, "bring_up", _bring_up)
    monkeypatch.setattr(writer_stack, "stack_pages", _stack_pages)
    monkeypatch.setattr(exercise, "run_plan", _run_plan)
    monkeypatch.setattr(exercise, "release", _release)
    monkeypatch.setattr(writer_stack, "release", _release)
    return released


def _kept(tmp_path: Path) -> KeptStack:
    return KeptStack(tmp_path, logging.getLogger(__name__))


def test_a_scenario_run_whose_runner_dies_leaves_its_stack_for_the_turn_s_end_to_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stack = StackReadiness(up=True, serving=True, notes="", owned=("4242",))
    released = _stub_exercise(monkeypatch, stack)

    with pytest.raises(RuntimeError):
        _ = exercise.exercise_book(_kept(tmp_path), tmp_path, "ledger", tmp_path / "spec")
    assert released == []

    _kept(tmp_path).release()
    assert [readiness.owned for readiness in released] == [("4242",)]


def test_a_scenario_run_whose_stack_failed_stops_the_servers_it_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stack = StackReadiness(up=False, serving=False, notes="the launch exited 1", owned=("4242",))
    released = _stub_exercise(monkeypatch, stack)

    result = exercise.exercise_book(_kept(tmp_path), tmp_path, "ledger", tmp_path / "spec")

    assert result.stack_down
    assert released == [stack]


def test_a_page_no_scenario_runs_is_named_back_before_the_stack_comes_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stack = StackReadiness(up=True, serving=True, notes="", owned=("4242",))
    released = _stub_exercise(monkeypatch, stack, CompileOutcome(gaps=(), planned=True, unmatched=("docs/x.md",)))

    result = exercise.exercise_book(_kept(tmp_path), tmp_path, "ledger", tmp_path / "spec", ("docs/x.md",))

    assert result.lines == ("problem: no scenario runs docs/x.md: name a page of the book a scenario covers, or a fixture page a claim arranges",)
    assert released == []


def test_the_check_prints_each_problem_of_a_book_with_no_entries_page(app: Callable[[str], Path], tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_command_state(tmp_path / "run", WriterCommandState(root=repo, service="ledger"))

    output = run_check([str(path)])

    assert output.code == 1
    assert output.lines
    assert NO_PROBLEMS_LINE not in output.lines


def _here(work: Work) -> Start:
    def start(job: Path, argv: Sequence[str]) -> None:
        finish_job(job, work, argv)

    return start


def test_a_turn_that_spent_its_check_runs_is_told_to_stop_and_still_reads_its_last_result(app: Callable[[str], Path], tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_command_state(tmp_path / "run", WriterCommandState(root=repo, service="ledger", check_and_scenario_runs=CHECK_AND_SCENARIO_RUN_CAP - 1))

    last = run_check([str(path)], _here(checked))

    assert read_command_state(path).check_and_scenario_runs == CHECK_AND_SCENARIO_RUN_CAP
    assert run_check([str(path)], _here(checked)) == last
    assert run_exercise([str(path)]) == CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))


def test_the_ostler_command_runs_only_scaffold_and_fmt(tmp_path: Path) -> None:
    path = write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path, service="ledger"))

    assert run_ostler([str(path), "checks"]) == CommandOutput(2, (OSTLER_USAGE,))
    assert run_ostler([str(path)]) == CommandOutput(2, (OSTLER_USAGE,))
    assert run_ostler([str(path), "fmt", "docs", "--index-dir=docs"]) == CommandOutput(2, (INDEX_DIR_REFUSED,))
    assert read_command_state(path).ostler_runs == 0


def test_the_ostler_command_counts_its_runs_and_stops_at_the_cap(
    app: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    path = write_command_state(tmp_path / "run", WriterCommandState(root=repo, service="ledger", ostler_runs=OSTLER_RUN_CAP - 1))
    monkeypatch.chdir(repo)

    output = run_ostler([str(path), "fmt", "docs"])

    assert (output.code, read_command_state(path).ostler_runs) == (0, OSTLER_RUN_CAP)
    assert output.lines
    assert run_ostler([str(path), "fmt", "docs"]) == CommandOutput(1, (OSTLER_RUNS_SPENT_MESSAGE,))


def test_the_source_size_skips_dependency_folders(tmp_path: Path) -> None:
    _ = (tmp_path / "main.go").write_text("a" * 40, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    _ = (tmp_path / "node_modules" / "lib.js").write_text("b" * 4000, encoding="utf-8")

    assert folder_tokens(tmp_path) == 10


def _noisy_problems(root: Path, service: str) -> tuple[PageProblem, ...]:
    print(f"stdout from {root.name}")
    logging.getLogger("noisy").warning("a warning")
    _ = os.write(2, b"a raw write\n")
    _ = subprocess.run([sys.executable, "-c", "print('a child process')"], check=True)
    return (PageProblem("docs/features/ledger/ledger.md", f"problem in {service}"),)


def test_a_check_prints_only_its_own_lines(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(check_pages, "page_problems", _noisy_problems)
    path = write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path / "repo", service="ledger"))

    output = run_check([str(path)], _here(checked))

    assert output == CommandOutput(1, ("problem in ledger",))
    assert capfd.readouterr() == ("", "")


def _problems_on(*pages: str) -> Callable[[Path, str], tuple[PageProblem, ...]]:
    def _problems(_root: Path, _service: str) -> tuple[PageProblem, ...]:
        return tuple(PageProblem(page, f"{page} is broken") for page in pages)

    return _problems


def test_a_check_scoped_to_pages_prints_their_problems_and_those_the_turn_made_but_not_those_of_other_changed_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = make_git_repo(tmp_path / "repo")
    book = repo / "docs/features/ledger"
    book.mkdir(parents=True)
    _ = (book / "touched.md").write_text("changed\n", encoding="utf-8")
    pages = (
        "docs/features/ledger/mine.md",
        "docs/features/ledger/touched.md",
        "docs/features/ledger/other.md",
        "docs/features/ledger/orphaned.md",
    )
    monkeypatch.setattr(check_pages, "page_problems", _problems_on(*pages))
    problems_at_turn_start = tuple(PageProblem(page, f"{page} is broken") for page in pages[:3])
    state = WriterCommandState(root=repo, service="ledger", pages=(pages[0],), problems_at_turn_start=problems_at_turn_start)

    printed = scoped_problems(state)

    assert printed == (f"{pages[0]} is broken", f"{pages[3]} is broken")


def _page_problems_returning(problems: tuple[PageProblem, ...]) -> Callable[[Path, str], tuple[PageProblem, ...]]:
    def _problems(_root: Path, _service: str) -> tuple[PageProblem, ...]:
        return problems

    return _problems


def test_a_check_scoped_to_sections_prints_their_problems_and_not_one_an_edit_above_only_moved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = "docs/features/ledger/http/ledger-api.md"
    path = tmp_path / page
    path.parent.mkdir(parents=True)
    _ = path.write_text("# Ledger API\n\n### list-rows\n\n- does: lists\n\n### drop-row\n\n- does: drops\n", encoding="utf-8")
    now = (
        PageProblem(page, f"{page}:5: step-no-verify: a claim has no verify", line=5),
        PageProblem(page, f"{page}:9: step-no-verify: a claim has no verify", line=9),
        PageProblem(page, f"{page}:1: title-stale: the title is stale", line=1),
    )
    monkeypatch.setattr(check_pages, "page_problems", _page_problems_returning(now))
    problems_at_turn_start = (
        PageProblem(page, f"{page}:4: step-no-verify: a claim has no verify", line=4),
        PageProblem(page, f"{page}:8: step-no-verify: a claim has no verify", line=8),
    )
    state = WriterCommandState(
        root=tmp_path, service="ledger", pages=(page,), sections_by_page={page: ("list-rows",)}, problems_at_turn_start=problems_at_turn_start
    )

    printed = scoped_problems(state)

    assert printed == (now[0].text, now[2].text)


def test_a_command_state_reads_the_problems_at_turn_start_an_earlier_run_wrote_as_texts(tmp_path: Path) -> None:
    page = "docs/features/ledger/http/ledger-api.md"
    texts = [f"{page}:4: step-no-verify: a claim has no verify", f"{page} is missing"]

    state = WriterCommandState.model_validate({"root": str(tmp_path), "service": "ledger", "problems_at_turn_start": texts})

    assert state.problems_at_turn_start == (PageProblem(page, texts[0], line=4), PageProblem("", texts[1]))
    assert [problem.text_ignoring_line() for problem in state.problems_at_turn_start] == [
        f"{page}: step-no-verify: a claim has no verify",
        texts[1],
    ]


def test_the_prompt_and_skill_allowance_covers_the_prompt_and_the_format_skill() -> None:
    repo = Path(__file__).resolve().parents[4]
    prompt = repo / "workflows/src/workhorse_workflows/okf_book/main/prompts/write-book.md"

    assert folder_tokens(repo / "base-library/library/skills/ostler/ostler-okf") + folder_tokens(prompt.parent) <= PROMPT_AND_SKILL_ALLOWANCE_TOKENS


def test_a_check_named_pages_checks_only_those_pages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pages = ("docs/features/ledger/mine.md", "docs/features/ledger/other.md")
    monkeypatch.setattr(check_pages, "page_problems", _problems_on(*pages))
    problems_at_turn_start = tuple(PageProblem(page, f"{page} is broken") for page in pages)
    path = write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path, service="ledger", problems_at_turn_start=problems_at_turn_start))
    (tmp_path / pages[0]).parent.mkdir(parents=True)
    _ = (tmp_path / pages[0]).write_text("# mine\n", encoding="utf-8")

    output = checked([str(path), pages[0]])

    assert output == CommandOutput(1, (f"{pages[0]} is broken",))
