"""The two commands the writer runs read the command state the run writes, and the source a writer reads is measured first."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse.config_run import AgentResilience
from workhorse.testing import make_git_repo

from workhorse_workflows.okf_book.main.nodes import check_pages
from workhorse_workflows.okf_book.main.nodes.check_pages import NO_PROBLEMS_LINE, run_check, scoped_problems
from workhorse_workflows.okf_book.main.nodes.check_pages import USAGE as CHECK_USAGE
from workhorse_workflows.okf_book.main.nodes.exercise import USAGE as EXERCISE_USAGE
from workhorse_workflows.okf_book.main.nodes.exercise import run_exercise
from workhorse_workflows.okf_book.main.nodes.writer_ostler import USAGE as OSTLER_USAGE
from workhorse_workflows.okf_book.main.nodes.writer_ostler import run_ostler
from workhorse_workflows.okf_book.main.nodes.turn_budget import (
    BOOK_HOLDS,
    BOOK_PER_SOURCE_TOKEN,
    PROMPT_AND_SKILL_ALLOWANCE_TOKENS,
    SOURCE_AND_BOOK_CEILING_TOKENS,
    ceiling_blocker_reason,
    SOURCE_READS,
    folder_tokens,
    source_and_book_tokens,
)
from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view, source_view_folder
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_MODULE,
    CHECK_AND_SCENARIO_RUN_CAP,
    PRINTED_LINE_CHARS,
    MAX_PRINTED_LINES,
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    CommandOutput,
    OSTLER_MODULE,
    OSTLER_RUN_CAP,
    OSTLER_RUNS_SPENT_MESSAGE,
    WriterCommandState,
    check_command,
    exercise_command,
    ostler_command,
    printed_lines,
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
    assert run_exercise(["a", "b"]) == CommandOutput(2, (EXERCISE_USAGE,))


def test_the_check_prints_each_problem_of_a_book_with_no_entries_page(app: Callable[[str], Path], tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_command_state(tmp_path / "run", WriterCommandState(root=repo, service="ledger"))

    output = run_check([str(path)])

    assert output.code == 1
    assert output.lines
    assert NO_PROBLEMS_LINE not in output.lines


def test_a_turn_that_spent_its_check_runs_is_told_to_stop(app: Callable[[str], Path], tmp_path: Path) -> None:
    repo = app("tally-cli")
    path = write_command_state(tmp_path / "run", WriterCommandState(root=repo, service="ledger", check_and_scenario_runs=CHECK_AND_SCENARIO_RUN_CAP - 1))

    _ = run_check([str(path)])

    assert read_command_state(path).check_and_scenario_runs == CHECK_AND_SCENARIO_RUN_CAP
    assert run_check([str(path)]) == CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))
    assert run_exercise([str(path)]) == CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))


def test_the_ostler_command_runs_only_scaffold_and_fmt(tmp_path: Path) -> None:
    path = write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path, service="ledger"))

    assert run_ostler([str(path), "checks"]) == CommandOutput(2, (OSTLER_USAGE,))
    assert run_ostler([str(path)]) == CommandOutput(2, (OSTLER_USAGE,))
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
    assert ceiling_blocker_reason(SOURCE_AND_BOOK_CEILING_TOKENS) is None
    assert ceiling_blocker_reason(SOURCE_AND_BOOK_CEILING_TOKENS + 1) is not None


def test_the_source_copy_holds_the_product_files_at_their_paths_and_no_test(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo")
    (repo / "api" / "mocks").mkdir(parents=True)
    _ = (repo / "api" / "main.go").write_text("a" * 40, encoding="utf-8")
    _ = (repo / "api" / "main_test.go").write_text("b" * 4000, encoding="utf-8")
    _ = (repo / "api" / "mocks" / "repository.go").write_text("c" * 4000, encoding="utf-8")
    _ = (repo / "api" / "stale.go").write_text("d", encoding="utf-8")
    _ = build_source_view(repo, "api")
    (repo / "api" / "stale.go").unlink()

    view = build_source_view(repo, "api")

    assert view == source_view_folder(repo, "api")
    assert sorted(path.relative_to(view).as_posix() for path in view.rglob("*") if path.is_file()) == ["main.go"]
    assert (folder_tokens(view), folder_tokens(repo / "api")) == (10, 2010)
    assert ".git" in view.relative_to(repo).parts


def test_the_source_and_the_book_are_each_counted_twice() -> None:
    assert source_and_book_tokens(1000, 0) == SOURCE_READS * 1000 + BOOK_HOLDS * BOOK_PER_SOURCE_TOKEN * 1000
    assert source_and_book_tokens(1000, 5000) == SOURCE_READS * 1000 + BOOK_HOLDS * 5000



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

    output = run_check([str(path)])

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
    problems_at_turn_start = (f"{pages[0]} is broken", f"{pages[1]} is broken", f"{pages[2]} is broken")
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
        f"{page}:4: step-no-verify: a claim has no verify",
        f"{page}:8: step-no-verify: a claim has no verify",
    )
    state = WriterCommandState(
        root=tmp_path, service="ledger", pages=(page,), sections_by_page={page: ("list-rows",)}, problems_at_turn_start=problems_at_turn_start
    )

    printed = scoped_problems(state)

    assert printed == (now[0].text, now[2].text)


def test_a_command_prints_its_first_lines_and_counts_the_rest() -> None:
    lines = [f"problem {n}" for n in range(MAX_PRINTED_LINES + 5)]

    printed = printed_lines(lines)

    assert printed[:-1] == tuple(lines[:MAX_PRINTED_LINES])
    assert printed[-1].startswith("… and 5 more")
    assert printed_lines(lines[:3]) == tuple(lines[:3])


def test_a_command_clips_each_line_it_prints() -> None:
    printed = printed_lines(["x" * (PRINTED_LINE_CHARS * 3)])

    assert len(printed[0]) == PRINTED_LINE_CHARS
    assert printed[0].endswith("…")


def test_the_prompt_and_skill_allowance_covers_the_prompt_and_the_format_skill() -> None:
    repo = Path(__file__).resolve().parents[4]
    prompt = repo / "workflows/src/workhorse_workflows/okf_book/main/prompts/write-book.md"

    assert folder_tokens(repo / "base-library/library/skills/ostler/okf") + folder_tokens(prompt.parent) <= PROMPT_AND_SKILL_ALLOWANCE_TOKENS
