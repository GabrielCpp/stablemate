"""The check the writer runs on its book, or on the pages its turn repairs. It prints each problem, or "No problems"."""
from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.page_sections import page_sections
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_MODULE,
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    CommandOutput,
    printed_lines,
    run_quietly,
    WriterCommandState,
    spend_check_or_scenario_run,
)
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

USAGE = f"usage: python -m {CHECK_MODULE} <writer-commands.json>"
NO_PROBLEMS_LINE = "No problems"
_LOCATION = re.compile(r"^([^:\s]+):\d+: ")


def _unlocated(text: str) -> str:
    return _LOCATION.sub(r"\1: ", text)


def _in_scope(state: WriterCommandState, root: Path, problem: PageProblem) -> bool:
    if problem.page not in state.pages:
        return False
    sections = state.sections.get(problem.page)
    if sections is None:
        return True
    path = root / problem.page
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return page_sections(text).of_problem(problem.page, problem.text) in sections


def scoped_problems(state: WriterCommandState) -> tuple[str, ...]:
    """Every problem on the book, or, when the state names pages, every problem on those pages, or their named sections, and every problem the turn made elsewhere.

    A problem counts as one the book had when the turn started when its text matches but for its
    line number, since an edit above it moves it.
    """
    root = state.root.resolve()
    problems = page_problems(root, state.service)
    if not state.pages:
        return tuple(problem.text for problem in problems)
    problems_at_turn_start = frozenset(_unlocated(text) for text in state.problems_at_turn_start)
    return tuple(
        problem.text
        for problem in problems
        if _in_scope(state, root, problem) or _unlocated(problem.text) not in problems_at_turn_start
    )


def run_check(argv: Sequence[str]) -> CommandOutput:
    """What the check exits with and prints for command state file named in `argv`."""
    if len(argv) != 1:
        return CommandOutput(2, (USAGE,))
    state = spend_check_or_scenario_run(Path(argv[0]))
    if state is None:
        return CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))
    problems, _ = run_quietly(lambda: scoped_problems(state))
    return CommandOutput(1, printed_lines(problems)) if problems else CommandOutput(0, (NO_PROBLEMS_LINE,))


def main() -> int:
    """Check the current book, and print what the run's own check after the turn would report."""
    return run_check(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
