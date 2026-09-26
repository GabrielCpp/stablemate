"""The writer's three commands and the state they share: the book's repo, its service and the runs the turn has spent."""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

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
    """The book the writer's commands work on, and how many runs of the checks and of ostler the turn has spent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path
    service: str
    check_and_scenario_runs: int = 0
    ostler_runs: int = 0

    def with_check_or_scenario_run_spent(self) -> WriterCommandState:
        """This state with one more check or scenario run spent."""
        return WriterCommandState(root=self.root, service=self.service, check_and_scenario_runs=self.check_and_scenario_runs + 1, ostler_runs=self.ostler_runs)

    def with_ostler_run_spent(self) -> WriterCommandState:
        """This state with one more ostler run spent."""
        return WriterCommandState(root=self.root, service=self.service, check_and_scenario_runs=self.check_and_scenario_runs, ostler_runs=self.ostler_runs + 1)


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


def _clipped(line: str) -> str:
    return line if len(line) <= PRINTED_LINE_CHARS else line[: PRINTED_LINE_CHARS - 1] + "…"


def printed_lines(lines: Sequence[str], limit: int = MAX_PRINTED_LINES) -> tuple[str, ...]:
    """The lines a command prints into the writer's turn: the first `limit`, each clipped, then how many more wait behind them."""
    shown = tuple(_clipped(line) for line in lines[:limit])
    if len(lines) <= limit:
        return shown
    return (*shown, f"… and {len(lines) - limit} more: fix these, then run it again")


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
