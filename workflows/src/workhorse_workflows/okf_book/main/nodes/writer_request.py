"""What one writer turn is sent: its prompt arguments, the source copy it reads, and the profile that confines it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ostler.qa.tools import catalog
from workhorse.runner.backends import AgentProfile
from workhorse_workflows.okf_book.shared.book_run import stack_pages
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import RepairBatch
from workhorse_workflows.okf_book.main.nodes.repair_put_back import fixture_folder
from workhorse_workflows.okf_book.main.nodes.source_view import source_view_folder
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
REPAIR_PROFILE_NAME = "okf-book-repairer"
WRITER_COMMAND_TIMEOUT_S = 600


@dataclass(frozen=True, slots=True)
class QaTool:
    """A program the repo lets a scenario run, and what it is for."""

    name: str
    description: str


def offered_qa_tools(root: Path) -> tuple[QaTool, ...]:
    """The QA tools the repo opts into that this machine can run."""
    specs, _unresolved = catalog(root)
    return tuple(QaTool(name=spec.name, description=spec.description) for _, spec in sorted(specs.items()) if spec.available)


@dataclass(frozen=True, slots=True)
class WriterRequest:
    """One writer turn: the surface it writes, where its book and source are, the runbook pages its stack starts from, and the three commands it may run."""

    surface: Surface
    repo_root: Path
    book_folder: str
    source_folder: str
    source_view: Path
    ostler_command_line: str
    check_command_line: str
    exercise_command_line: str
    qa_tools: tuple[QaTool, ...]
    stack_pages: tuple[str, ...] = ()

    def template_args(self) -> dict[str, object]:
        """The write-book prompt's arguments."""
        return {
            "service": self.surface.service,
            "kind": self.surface.kind.value,
            "repo_root": self.repo_root.as_posix(),
            "entry": self.surface.entry,
            "source_view": self.source_view.as_posix(),
            "source_folder": self.source_folder,
            "book_folder": self.book_folder,
            "ostler": self.ostler_command_line,
            "ostler_run_cap": OSTLER_RUN_CAP,
            "check": self.check_command_line,
            "exercise": self.exercise_command_line,
            "check_and_scenario_run_cap": CHECK_AND_SCENARIO_RUN_CAP,
            "qa_tools": [{"name": tool.name, "description": tool.description} for tool in self.qa_tools],
        }

    def repair_template_args(self, batch: RepairBatch, *, failed_run: bool) -> dict[str, object]:
        """The repair-pages prompt's arguments for one batch, and whether the book failed its run."""
        return {
            "service": self.surface.service,
            "kind": self.surface.kind.value,
            "repo_root": self.repo_root.as_posix(),
            "source_view": self.source_view.as_posix(),
            "source_folder": self.source_folder,
            "book_folder": self.book_folder,
            "ostler": self.ostler_command_line,
            "ostler_run_cap": OSTLER_RUN_CAP,
            "check": self.check_command_line,
            "check_run_cap": CHECK_AND_SCENARIO_RUN_CAP,
            "exercise": self.exercise_command_line if failed_run else "",
            "pages": [repair.model_dump() for repair in batch.pages],
            "journey_pages": list(batch.journey.pages) if batch.journey else [],
            "flow_folder": batch.journey.flow_folder if batch.journey else "",
            "new_flow_page": batch.new_flow_page,
            "fixture_folder": fixture_folder(self.surface.service),
            "stack_pages": list(self.stack_pages),
        }

    @property
    def repair_profile(self) -> AgentProfile:
        """The profile that denies every tool and allows only ostler, the check and the scenario run."""
        return AgentProfile(
            name=REPAIR_PROFILE_NAME,
            tools={"*": False},
            steps=WRITER_STEPS,
            confined=True,
            commands=(self.ostler_command_line, self.check_command_line, self.exercise_command_line),
            command_timeout_s=WRITER_COMMAND_TIMEOUT_S,
        )

    @property
    def profile(self) -> AgentProfile:
        """The profile that denies every tool and allows only the three commands."""
        return AgentProfile(
            name=WRITER_PROFILE_NAME,
            tools={"*": False},
            steps=WRITER_STEPS,
            confined=True,
            commands=(self.ostler_command_line, self.check_command_line, self.exercise_command_line),
            command_timeout_s=WRITER_COMMAND_TIMEOUT_S,
        )


def writer_request(run_dir: Path, root: Path, surface: Surface, book_folder: str, source_folder: str) -> WriterRequest:
    """The turn that writes the surface's book with the QA tools its scenarios may run, and may run only the three commands on the run's command state."""
    return WriterRequest(
        surface=surface,
        repo_root=root,
        book_folder=book_folder,
        source_folder=source_folder,
        source_view=source_view_folder(root, source_folder),
        ostler_command_line=ostler_command(run_dir),
        check_command_line=check_command(run_dir),
        exercise_command_line=exercise_command(run_dir),
        qa_tools=offered_qa_tools(root),
        stack_pages=stack_pages(root, surface.service),
    )
