"""The writer's three commands and the state they share: the book's repo, its service and the runs the turn has spent."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from workhorse_workflows.okf_book.shared.page_check import PageProblem

CHECK_MODULE = f"{__package__}.check_pages"
EXERCISE_MODULE = f"{__package__}.exercise"
OSTLER_MODULE = f"{__package__}.writer_ostler"
STATE_FILE = "writer-commands.json"
MAX_PRINTED_LINES = 20
PRINTED_LINE_CHARS = 200
CHECK_AND_SCENARIO_RUN_CAP = 24
OSTLER_RUN_CAP = 40
OSTLER_MAX_PRINTED_LINES = 3
CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE = f"the {CHECK_AND_SCENARIO_RUN_CAP} runs of the check and the scenarios this turn may make are spent: stop, and reply with what is left to fix"
OSTLER_RUNS_SPENT_MESSAGE = f"the {OSTLER_RUN_CAP} ostler runs this turn may make are spent: edit the pages by hand"
_EARLIER_LOCATION = re.compile(r"^(?P<page>[^:\s]+):(?P<line>\d+): ")


@dataclass(frozen=True, slots=True)
class CommandOutput:
    """What one of the writer's commands exits with, and the lines it prints."""

    code: int
    lines: tuple[str, ...]

    def print_and_exit_code(self) -> int:
        """Print the lines, and return the exit code."""
        for line in self.lines:
            print(line)
        return self.code


class WriterCommandState(BaseModel):
    """The book the writer's commands work on, the pages its check is scoped to, and how many runs of the checks and of ostler the turn has spent.

    With no pages named, the check covers the whole book. With pages named, it covers those pages
    and every problem not in `problems_at_turn_start`, the problems the book had when the turn started.
    A page in `sections_by_page` is covered only in the `###` sections named for it. The field also
    reads its earlier key, `sections`, and `problems_at_turn_start` also reads its earlier form, the
    problems' texts. With `records_dir` naming the run's records, the check leaves out every problem
    the last lead of the book's page check held for another side than the book.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    service: str
    pages: tuple[str, ...] = ()
    sections_by_page: dict[str, tuple[str, ...]] = Field(default={}, validation_alias=AliasChoices("sections_by_page", "sections"))
    problems_at_turn_start: tuple[PageProblem, ...] = ()
    records_dir: Path | None = None
    check_and_scenario_runs: int = 0
    ostler_runs: int = 0

    @field_validator("problems_at_turn_start", mode="before")
    @classmethod
    def _problems_from_earlier_texts(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        items = cast("Sequence[object]", value)
        return tuple(_problem_from_earlier_text(item) if isinstance(item, str) else item for item in items)

    def with_check_or_scenario_run_spent(self) -> WriterCommandState:
        """This state with one more check or scenario run spent."""
        return self.model_copy(update={"check_and_scenario_runs": self.check_and_scenario_runs + 1})

    def with_ostler_run_spent(self) -> WriterCommandState:
        """This state with one more ostler run spent."""
        return self.model_copy(update={"ostler_runs": self.ostler_runs + 1})


def _problem_from_earlier_text(text: str) -> PageProblem:
    located = _EARLIER_LOCATION.match(text)
    if located is None:
        return PageProblem("", text)
    return PageProblem(located.group("page"), text, line=int(located.group("line")))


def command_state_path(run_dir: Path) -> Path:
    """Where the writer's command state is."""
    return run_dir / STATE_FILE


def write_command_state(run_dir: Path, state: WriterCommandState) -> Path:
    """Write the writer's command state, and return where it is."""
    path = command_state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(state.model_dump_json(), encoding="utf-8")
    return path


def read_command_state(path: Path) -> WriterCommandState:
    """The command state written at `path`."""
    return WriterCommandState.model_validate_json(path.read_text(encoding="utf-8"))


def _write_and_return_state(path: Path, state: WriterCommandState) -> WriterCommandState:
    _ = path.write_text(state.model_dump_json(), encoding="utf-8")
    return state


def spend_check_or_scenario_run(path: Path) -> WriterCommandState | None:
    """The state at `path` after one more check run is spent, or None when the turn has spent them all."""
    state = read_command_state(path)
    if state.check_and_scenario_runs >= CHECK_AND_SCENARIO_RUN_CAP:
        return None
    return _write_and_return_state(path, state.with_check_or_scenario_run_spent())


def spend_ostler_run(path: Path) -> WriterCommandState | None:
    """The state at `path` after one more ostler run is spent, or None when the turn has spent them all."""
    state = read_command_state(path)
    if state.ostler_runs >= OSTLER_RUN_CAP:
        return None
    return _write_and_return_state(path, state.with_ostler_run_spent())


def _clipped(line: str, chars: int) -> str:
    return line if len(line) <= chars else line[: chars - 1] + "…"


def printed_lines(lines: Sequence[str], limit: int = MAX_PRINTED_LINES) -> tuple[str, ...]:
    """The lines a command prints into the writer's turn, then how many more wait behind them.

    A run prints at most `limit` lines and at most `limit` times `PRINTED_LINE_CHARS` characters.
    Each line is printed whole, since a problem names its remedy and its claims last. Only a
    first line longer than the whole run's characters is clipped.
    """
    chars_left = limit * PRINTED_LINE_CHARS
    shown: list[str] = []
    for line in lines[:limit]:
        if shown and len(line) > chars_left:
            break
        shown.append(_clipped(line, chars_left))
        chars_left -= len(shown[-1])
    if len(shown) == len(lines):
        return tuple(shown)
    return (*shown, f"… and {len(lines) - len(shown)} more: fix these, then run it again")


def run_quietly[T](work: Callable[[], T]) -> tuple[T, str]:
    """Run `work` with everything it or a child process prints kept out of the writer's turn, and return its result and what it printed."""
    _ = sys.stdout.flush(), sys.stderr.flush()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as sink:
        saved = (os.dup(1), os.dup(2))
        try:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with redirect_stdout(sink), redirect_stderr(sink):
                result = work()
        finally:
            sink.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
        _ = sink.seek(0)
        return result, sink.read()


def check_command(run_dir: Path) -> str:
    """The page check the writer runs, from any directory."""
    return f"{sys.executable} -m {CHECK_MODULE} {command_state_path(run_dir)}"


def exercise_command(run_dir: Path) -> str:
    """The scenario run the writer runs, from any directory."""
    return f"{sys.executable} -m {EXERCISE_MODULE} {command_state_path(run_dir)}"


def ostler_command(run_dir: Path) -> str:
    """The ostler scaffold and fmt the writer runs, from its book folder."""
    return f"{sys.executable} -m {OSTLER_MODULE} {command_state_path(run_dir)}"
