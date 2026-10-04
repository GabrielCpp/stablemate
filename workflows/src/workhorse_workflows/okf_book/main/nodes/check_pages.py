"""The check the writer runs on its book, or on the pages its turn repairs. It prints each problem, or "No problems"."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.page_sections import page_sections
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_MODULE,
    CommandOutput,
    printed_lines,
    read_command_state,
    run_quietly,
    WriterCommandState,
)
from workhorse_workflows.okf_book.main.nodes.writer_jobs import Start, detached, run_or_attach
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems

USAGE = f"usage: python -m {CHECK_MODULE} <writer-commands.json> [page ...]"
NO_PROBLEMS_LINE = "No problems"


def _in_scope(state: WriterCommandState, root: Path, problem: PageProblem) -> bool:
    if problem.page not in state.pages:
        return False
    sections = state.sections_by_page.get(problem.page)
    if sections is None:
        return True
    path = root / problem.page
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return page_sections(text).section_id_of_problem(problem) in sections


def scoped_problems(state: WriterCommandState) -> tuple[str, ...]:
    """Every problem on the book, or, when the state names pages, every problem on those pages, or their named sections, and every problem the turn made elsewhere.

    A problem counts as one the book had when the turn started when its text, with its line number
    left out, matches one of those.
    """
    root = state.root.resolve()
    problems = page_problems(root, state.service)
    if not state.pages:
        return tuple(problem.text for problem in problems)
    problems_at_turn_start = frozenset(problem.text_ignoring_line() for problem in state.problems_at_turn_start)
    return tuple(
        problem.text
        for problem in problems
        if _in_scope(state, root, problem) or problem.text_ignoring_line() not in problems_at_turn_start
    )


def checked(argv: Sequence[str]) -> CommandOutput:
    """What the check of the command state file named first in `argv`, on the pages after it when it names any, exits with and prints."""
    state = read_command_state(Path(argv[0]))
    unknown = [page for page in argv[1:] if not (state.root / page).is_file()]
    if unknown:
        return CommandOutput(2, (*(f"{page} is no page: name each page by its path from the repository root" for page in unknown), USAGE))
    if argv[1:]:
        state = state.model_copy(update={"pages": tuple(argv[1:]), "sections_by_page": {}})
    problems, _ = run_quietly(lambda: scoped_problems(state))
    return CommandOutput(1, printed_lines(problems)) if problems else CommandOutput(0, (NO_PROBLEMS_LINE,))


def run_check(argv: Sequence[str], start: Start | None = None) -> CommandOutput:
    """What the writer's call of the check on the command state file named first in `argv`, and the pages after it, exits with and prints."""
    if not argv:
        return CommandOutput(2, (USAGE,))
    return run_or_attach(CHECK_MODULE, argv, start or detached(checked))


def main() -> int:
    """Check the current book, and print what the run's own check after the turn would report."""
    return run_check(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
