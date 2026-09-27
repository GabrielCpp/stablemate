"""The okf-book run: one confined writer per surface writes its whole book, then the run checks it, runs it and reports."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import last_commit_subject
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.repair_book_flow import RepairBook, RepairOutcome
from workhorse_workflows.okf_book.main.nodes.report import build_report, read_report, write_report
from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view, source_view_folder
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.turn_budget import (
    ceiling_blocker_reason,
    folder_tokens,
    source_and_book_tokens,
)
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook, WriteOutcome
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.citations import book_pages
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import book_problems
from workhorse_workflows.okf_book.shared.scenarios import plan_scenarios, spec_dir, write_run

OPERATOR_NAME = "operator.md"


def _book_folder(service: str) -> str:
    return (FEATURES_DIR / service).as_posix()


def _source_folder(root: Path, surface: Surface) -> str:
    entry = Path(surface.entry)
    return (entry if (root / entry).is_dir() else entry.parent).as_posix()


class OkfBook(BookFlow):
    """The run: each surface's book is written by one confined turn, committed, checked and run against the app."""

    surfaces: tuple[Surface, ...] = ()

    @property
    def services(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(surface.service for surface in self.surfaces))

    def start(self) -> Continue[...]:
        """A run with no surface has no book to write."""
        if not self.surfaces:
            raise WorkflowFailed("the run names no surface: pass each one under `surfaces`")
        return Continue(None, self.route_book, index=0).because("route the first surface's book")

    def _next_surface(self, result: object, index: int) -> Continue[...]:
        if index + 1 < len(self.surfaces):
            return Continue(result, self.route_book, index=index + 1).because("this surface is settled: next one")
        return Continue(result, self.report).because("every surface is settled")

    def _block_surface_and_move_on(self, index: int, reason: str) -> Continue[...]:
        blocker = Blocker(subject=self.surfaces[index].service, phase=Phase.WRITE, side=Side.WORKFLOW, reason=reason)
        _ = record_blocker(self.records_dir, blocker)
        return self._next_surface(reason, index)

    def route_book(self, index: int) -> Continue[...]:
        """A book this workflow last committed is checked and run, never rewritten. Any other book with no problem goes on to its run. A missing or failing one goes to the writer."""
        service = self.surfaces[index].service
        book = _book_folder(service)
        if not (self.root / book).is_dir():
            return Continue(None, self.copy_source, index=index).because("no book yet: write it")
        if last_commit_subject(self.root, book) == book_commit_subject(service):
            return Continue(book, self.check_book, index=index).because("this workflow wrote the book: check it")
        problems = book_problems(self.root, service)
        if problems:
            return Continue(problems, self.copy_source, index=index).because("the existing book has problems")
        return Continue(problems, self.run_book, index=index, written_by_workflow=False).because(
            "the existing book checks clean"
        )

    def copy_source(self, index: int) -> Continue[...]:
        """Copy the surface's product source for its writer. A surface whose source is no folder is a blocker."""
        surface = self.surfaces[index]
        source = _source_folder(self.root, surface)
        if not (self.root / source).is_dir():
            return self._block_surface_and_move_on(index, f"the entry {surface.entry} is in no source folder")
        view = build_source_view(self.root, source)
        return Continue(view.as_posix(), self.measure_source, index=index).because("measure the writer's source")

    def measure_source(self, index: int) -> Continue[...]:
        """A book over the ceiling one writer reads is repaired a batch of pages at a time. A surface with no book over it is a blocker."""
        surface = self.surfaces[index]
        view = source_view_folder(self.root, _source_folder(self.root, surface))
        tokens = source_and_book_tokens(folder_tokens(view), folder_tokens(self.root / _book_folder(surface.service)))
        reason = ceiling_blocker_reason(tokens)
        if reason is None:
            return Continue(tokens, self.write_book, index=index).because("the source fits one writer")
        if book_pages(self.root, surface.service):
            return Continue(tokens, self.repair_book, index=index).because("the book is over one writer: repair it in batches")
        return self._block_surface_and_move_on(index, reason)

    def repair_book(self, index: int, run_failures: dict[str, tuple[str, ...]] | None = None) -> Continue[...]:
        """Hand the book to its repair, with the failures of the run it failed when it failed one."""
        surface = self.surfaces[index]
        repaired = RepairOutcome.model_validate(
            self.handoff(
                RepairBook,
                parent_records_dir=str(self.records_dir),
                surface=surface,
                book_folder=_book_folder(surface.service),
                source_folder=_source_folder(self.root, surface),
                run_failures=run_failures or {},
            )
        )
        return Continue(repaired, self.settle_repair, index=index, repaired=repaired, after_run=bool(run_failures)).because(
            "settle the repair"
        )

    def settle_repair(self, index: int, repaired: RepairOutcome, after_run: bool = False) -> Continue[...]:
        """The repair turns that ended without a reply are one blocker on the workflow. The repaired book goes to its check."""
        service = self.surfaces[index].service
        if repaired.failed_turns:
            reason = "\n".join(repaired.failed_turns)
            _ = record_blocker(self.records_dir, Blocker(subject=service, phase=Phase.WRITE, side=Side.WORKFLOW, reason=reason))
        return Continue(repaired, self.check_book, index=index, after_run=after_run).because("check the repaired book")

    def write_book(self, index: int) -> Continue[...]:
        """Hand the surface to its writer."""
        surface = self.surfaces[index]
        source = _source_folder(self.root, surface)
        written = WriteOutcome.model_validate(
            self.handoff(
                WriteBook,
                parent_records_dir=str(self.records_dir),
                surface=surface,
                book_folder=_book_folder(surface.service),
                source_folder=source,
            )
        )
        return Continue(written, self.settle_write, index=index, written=written).because("settle the writer's turn")

    def settle_write(self, index: int, written: WriteOutcome) -> Continue[...]:
        """A turn that ended without a reply is a blocker on the surface. A committed book goes to its check."""
        if not written.committed:
            return self._block_surface_and_move_on(index, written.failure)
        return Continue(written, self.check_book, index=index).because("check the committed book")

    def check_book(self, index: int, after_run: bool = False) -> Continue[...]:
        """Repeat the writer's own page check. Each problem it finds is a blocker."""
        service = self.surfaces[index].service
        problems = book_problems(self.root, service)
        for problem in problems:
            _ = record_blocker(self.records_dir, Blocker(subject=f"{service}: {problem}", phase=Phase.WRITE, side=Side.BOOK, reason=problem))
        return Continue(problems, self.run_book, index=index, written_by_workflow=True, after_run=after_run).because(
            "run the book against the app"
        )

    def run_book(self, index: int, written_by_workflow: bool, after_run: bool = False) -> Continue[...]:
        """Run the book against the app, by handing off to the run flow."""
        service = self.surfaces[index].service
        exercised = ExerciseResult.model_validate(self.handoff(ExerciseBook, parent_records_dir=str(self.records_dir), service=service))
        return Continue(
            exercised, self.settle_run, index=index, written_by_workflow=written_by_workflow, exercised=exercised, after_run=after_run
        ).because("settle the run")

    def settle_run(self, index: int, written_by_workflow: bool, exercised: ExerciseResult, after_run: bool = False) -> Continue[...]:
        """A passing book is done. A stack that cannot come up is the app's blocker, and the book stays. A failing book goes to the writer once, and a book this workflow wrote goes to its repair once, with the failures on the pages they cover. A book that fails again is a blocker."""
        service = self.surfaces[index].service
        if exercised.summary is not None:
            _ = write_run(self.records_dir, exercised.summary)
        if exercised.passed:
            return self._next_surface(exercised.passed, index)
        if not exercised.stack_down and not written_by_workflow:
            return Continue(exercised.passed, self.copy_source, index=index).because("the existing book fails its run")
        failures = self._run_failures(service, exercised) if not exercised.stack_down and not after_run else {}
        if failures:
            view = build_source_view(self.root, _source_folder(self.root, self.surfaces[index]))
            return Continue(view.as_posix(), self.repair_book, index=index, run_failures=failures).because(
                "the book this workflow wrote fails its run: repair the pages that failed"
            )
        side = Side.APP if exercised.stack_down else Side.BOOK
        reason = "\n".join(exercised.lines)
        _ = record_blocker(self.records_dir, Blocker(subject=service, phase=Phase.EXERCISE, side=side, reason=reason))
        return self._next_surface(exercised.passed, index)

    def _run_failures(self, service: str, exercised: ExerciseResult) -> dict[str, tuple[str, ...]]:
        if exercised.summary is None:
            return {}
        scenarios, _problems = plan_scenarios(self.root, spec_dir(self.records_dir) / service)
        return exercised.summary.failures_by_page(scenarios)

    def report(self) -> Await[...] | Done:
        """Publish the report. Any blocker stops the run at the operator, once."""
        report = build_report(self.root, self.records_dir, self.services)
        page = write_report(self.records_dir, report)
        blockers = read_blockers(self.records_dir)
        if not blockers:
            return Done(report).because("no blocker: the books are done")
        return Await(
            self.run_dir / OPERATOR_NAME,
            f"The run stopped on {len(blockers)} blockers, each listed in {page}. "
            + "Fix the book, ostler, the app or the workflow each one names, then restart the run. "
            + "Answer here to close this run.",
            self.finish,
        ).because("blockers wait for the operator")

    def finish(self) -> Done:
        """The operator has read the report."""
        return Done(read_report(self.records_dir)).because("the operator read the report")
