"""What one writer turn is sent: its prompt arguments, the source copy it reads, and the profile that confines it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workhorse.runner.backends import AgentProfile
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.turn_budget import WRITER_STEPS
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_AND_SCENARIO_RUN_CAP,
    OSTLER_RUN_CAP,
    check_command,
    exercise_command,
    ostler_command,
)

WRITER_PROFILE_NAME = "okf-book-writer"


@dataclass(frozen=True, slots=True)
class WriterRequest:
    """One writer turn: the surface it writes, where its book and source are, and the three commands it may run."""

    surface: Surface
    book_folder: str
    source_folder: str
    source_view: Path
    ostler_command_line: str
    check_command_line: str
    exercise_command_line: str

    def template_args(self) -> dict[str, object]:
        """The write-book prompt's arguments."""
        return {
            "service": self.surface.service,
            "kind": self.surface.kind.value,
            "entry": self.surface.entry,
            "source_view": self.source_view.as_posix(),
            "source_folder": self.source_folder,
            "book_folder": self.book_folder,
            "ostler": self.ostler_command_line,
            "ostler_run_cap": OSTLER_RUN_CAP,
            "check": self.check_command_line,
            "exercise": self.exercise_command_line,
            "check_and_scenario_run_cap": CHECK_AND_SCENARIO_RUN_CAP,
        }

    @property
    def profile(self) -> AgentProfile:
        """The profile that denies every tool and allows only the three commands."""
        return AgentProfile(
            name=WRITER_PROFILE_NAME,
            tools={"*": False},
            steps=WRITER_STEPS,
            confined=True,
            commands=(self.ostler_command_line, self.check_command_line, self.exercise_command_line),
        )


def writer_request(run_dir: Path, surface: Surface, book_folder: str, source_folder: str, source_view: Path) -> WriterRequest:
    """The turn that writes the surface's book and may run only the three commands on the run's command state."""
    return WriterRequest(
        surface=surface,
        book_folder=book_folder,
        source_folder=source_folder,
        source_view=source_view,
        ostler_command_line=ostler_command(run_dir),
        check_command_line=check_command(run_dir),
        exercise_command_line=exercise_command(run_dir),
    )
