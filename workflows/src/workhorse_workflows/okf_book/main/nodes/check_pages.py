"""The check the writer runs on its book, or on the pages its turn repairs. It prints each problem, or "No problems"."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_MODULE,
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    CommandOutput,
    printed_lines,
    run_quietly,
    WriterCommandState,
    spend_check_or_scenario_run,
)
from workhorse_workflows.okf_book.shared.page_check import page_problems

USAGE = f"usage: python -m {CHECK_MODULE} <writer-commands.json>"
NO_PROBLEMS_LINE = "No problems"


def scoped_problems(state: WriterCommandState) -> tuple[str, ...]:
    """Every problem on the book, or, when the state names pages, every problem on those pages and every problem the turn made elsewhere."""
    root = state.root.resolve()
    problems = page_problems(root, state.service)
    if not state.pages:
        return tuple(problem.text for problem in problems)
    scope = frozenset(state.pages)
    problems_at_turn_start = frozenset(state.problems_at_turn_start)
    return tuple(problem.text for problem in problems if problem.page in scope or problem.text not in problems_at_turn_start)


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
