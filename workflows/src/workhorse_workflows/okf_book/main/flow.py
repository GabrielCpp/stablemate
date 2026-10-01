"""The okf-book run: one confined writer per surface writes its whole book, then the run checks it, runs it and reports."""
from __future__ import annotations

from pathlib import Path

from ostler.qa.attribution import Cause, Signature
from workhorse.pyflow import Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import last_commit_subject
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.nodes.operator_answer import answer_below, write_answer
from workhorse_workflows.okf_book.main.nodes.progress_ledger import LapCounts, lap_counts, read_laps, record_lap, service_laps, stalled, trend
from workhorse_workflows.okf_book.main.nodes.repair_ledger import RepairOutcome
from workhorse_workflows.okf_book.main.repair_book_flow import RepairBook
from workhorse_workflows.okf_book.main.nodes.report import build_report, write_report
from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view, source_view_folder
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.surface_pass import read_pass, write_pass
from workhorse_workflows.okf_book.main.nodes.turn_budget import (
    ceiling_blocker_reason,
    folder_tokens,
    source_and_book_tokens,
)
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook, WriteOutcome
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, forget_blockers, forget_every_blocker, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject, repaired_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.citations import book_pages
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import PageProblem, book_problems
from workhorse_workflows.okf_book.shared.scenarios import PLAN_NAME, plan_scenarios, spec_dir, write_run

OPERATOR_NAME = "operator.md"

RunFailures = dict[str, tuple[PageProblem, ...]]

SIDE_BY_ESCALATED_CAUSE = {Cause.ENVIRONMENT: Side.ENVIRONMENT, Cause.APP: Side.APP, Cause.UNATTRIBUTED: Side.UNATTRIBUTED}


def _book_folder(service: str) -> str:
    return (FEATURES_DIR / service).as_posix()


def _source_folder(root: Path, surface: Surface) -> str:
    entry = Path(surface.entry)
    return (entry if (root / entry).is_dir() else entry.parent).as_posix()


def _escalated_signatures(exercised: ExerciseResult) -> tuple[Signature, ...]:
    """The signatures of the run that a party other than the book's writer must fix."""
    signatures = exercised.summary.signatures if exercised.summary is not None else ()
    return tuple(signature for signature in signatures if signature.cause in SIDE_BY_ESCALATED_CAUSE)


def _escalation_reason(signature: Signature) -> str:
    """Why a person must act on *signature*: a capability only a person can supply, or the checks another party must fix."""
    if signature.gap:
        return (f"the stack lacks the {signature.gap}, and only a person can supply it; "
                f"the {signature.count} checks that need it pass once it is there; for example {signature.sample}")
    return f"{signature.count} checks failed this way; for example {signature.sample}"


def _stall(exercised: ExerciseResult, laps: tuple[LapCounts, ...]) -> str:
    """Why the lap after a repair did not help, or nothing when it lowered the book's failed checks."""
    if exercised.summary is None:
        return "the run after the repair counted no check, so it cannot show that the repair helped"
    if stalled(laps):
        return f"the repair did not lower the book's failed checks, lap by lap: {trend(laps)}"
    return ""


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
        write_pass(self.records_dir, self.services)
        return Continue(None, self.route_book, index=0).because("route the first surface's book")

    def _routed_after(self, index: int) -> int | None:
        routed = read_pass(self.records_dir, self.services)
        return next((later for later in range(index + 1, len(self.surfaces)) if self.surfaces[later].service in routed), None)

    def _next_surface(self, result: object, index: int) -> Continue[...]:
        later = self._routed_after(index)
        if later is not None:
            return Continue(result, self.route_book, index=later).because("this surface is settled: next one")
        return Continue(result, self.report).because("every surface is settled")

    def _block_surface_and_move_on(self, index: int, reason: str) -> Continue[...]:
        service = self.surfaces[index].service
        blocker = Blocker(subject=service, service=service, phase=Phase.WRITE, side=Side.WORKFLOW, reason=reason)
        _ = record_blocker(self.records_dir, blocker)
        return self._next_surface(reason, index)

    def route_book(self, index: int) -> Continue[...]:
        """A missing book, or one with problems, goes to the writer, so a rerun after the operator's fix repairs what the last run left. A book this workflow's writer or repair last committed with no problem goes through the check again, and any other one goes straight to its run."""
        service = self.surfaces[index].service
        book = _book_folder(service)
        if not (self.root / book).is_dir():
            return Continue(None, self.copy_source, index=index).because("no book yet: write it")
        problems = book_problems(self.root, service)
        if problems:
            return Continue(problems, self.copy_source, index=index).because("the existing book has problems")
        if last_commit_subject(self.root, book) in (book_commit_subject(service), repaired_book_commit_subject(service)):
            return Continue(book, self.check_book, index=index).because("this workflow wrote the book: check it")
        return Continue(problems, self.run_book, index=index, run_failures_repaired=False).because(
            "the existing book checks clean"
        )

    def copy_source(self, index: int, run_failures: RunFailures | None = None) -> Continue[...]:
        """Copy the surface's product source for its writer. A surface whose source is no folder is a blocker."""
        surface = self.surfaces[index]
        source = _source_folder(self.root, surface)
        if not (self.root / source).is_dir():
            return self._block_surface_and_move_on(index, f"the entry {surface.entry} is in no source folder")
        view = build_source_view(self.root, source)
        return Continue(view.as_posix(), self.measure_source, index=index, run_failures=run_failures).because(
            "measure the writer's source"
        )

    def measure_source(self, index: int, run_failures: RunFailures | None = None) -> Continue[...]:
        """A book over the ceiling one writer reads is repaired a batch of pages at a time, with the failures of the run it failed. A surface with no book over it is a blocker."""
        surface = self.surfaces[index]
        view = source_view_folder(self.root, _source_folder(self.root, surface))
        tokens = source_and_book_tokens(folder_tokens(view), folder_tokens(self.root / _book_folder(surface.service)))
        reason = ceiling_blocker_reason(tokens)
        if reason is None:
            return Continue(tokens, self.write_book, index=index, run_failures_repaired=run_failures is not None).because(
                "the source fits one writer"
            )
        if book_pages(self.root, surface.service):
            return Continue(tokens, self.repair_book, index=index, run_failures=run_failures).because(
                "the book is over one writer: repair it in batches"
            )
        return self._block_surface_and_move_on(index, reason)

    def repair_book(self, index: int, run_failures: RunFailures | None = None) -> Continue[...]:
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
        return Continue(
            repaired, self.settle_repair, index=index, repaired=repaired, run_failures_repaired=run_failures is not None
        ).because("settle the repair")

    def settle_repair(self, index: int, repaired: RepairOutcome, run_failures_repaired: bool = False) -> Continue[...]:
        """The repair turns that ended without a reply are one blocker on the workflow, and each page too large for one writer is another. The repaired book goes to its check."""
        service = self.surfaces[index].service
        if repaired.failed_turns:
            reason = "\n".join(repaired.failed_turns)
            _ = record_blocker(self.records_dir, Blocker(subject=service, service=service, phase=Phase.WRITE, side=Side.WORKFLOW, reason=reason))
        for part in repaired.oversized_parts:
            blocker = Blocker(subject=f"{service}: {part.subject}", service=service, phase=Phase.WRITE, side=Side.WORKFLOW, reason=part.reason)
            _ = record_blocker(self.records_dir, blocker)
        return Continue(repaired, self.check_book, index=index, run_failures_repaired=run_failures_repaired).because(
            "check the repaired book"
        )

    def write_book(self, index: int, run_failures_repaired: bool = False) -> Continue[...]:
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
        return Continue(
            written, self.settle_write, index=index, written=written, run_failures_repaired=run_failures_repaired
        ).because("settle the writer's turn")

    def settle_write(self, index: int, written: WriteOutcome, run_failures_repaired: bool = False) -> Continue[...]:
        """A turn that ended without a reply is a blocker on the surface. A committed book goes to its check."""
        if not written.committed:
            return self._block_surface_and_move_on(index, written.failure)
        return Continue(written, self.check_book, index=index, run_failures_repaired=run_failures_repaired).because(
            "check the committed book"
        )

    def check_book(self, index: int, run_failures_repaired: bool = False) -> Continue[...]:
        """Repeat the writer's own page check. Each problem it finds is a blocker, and one an earlier check found that this one does not is no longer."""
        service = self.surfaces[index].service
        problems = book_problems(self.root, service)
        forget_blockers(self.records_dir, Phase.WRITE, Side.BOOK, service)
        for problem in problems:
            _ = record_blocker(self.records_dir, Blocker(subject=f"{service}: {problem}", service=service, phase=Phase.WRITE, side=Side.BOOK, reason=problem))
        return Continue(problems, self.run_book, index=index, run_failures_repaired=run_failures_repaired).because(
            "run the book against the app"
        )

    def run_book(self, index: int, run_failures_repaired: bool) -> Continue[...]:
        """Run the book against the app, by handing off to the run flow."""
        service = self.surfaces[index].service
        exercised = ExerciseResult.model_validate(self.handoff(ExerciseBook, parent_records_dir=str(self.records_dir), service=service))
        return Continue(
            exercised,
            self.settle_run,
            index=index,
            run_failures_repaired=run_failures_repaired,
            exercised=exercised,
        ).because("settle the run")

    def settle_run(self, index: int, run_failures_repaired: bool, exercised: ExerciseResult) -> Continue[...]:
        """A passing book is done. Each failure another party must fix is a blocker, one per signature. A stack that cannot come up is a blocker on the app. A book whose run failed goes to the mapping of its failures. Either way the book stays."""
        service = self.surfaces[index].service
        if exercised.summary is not None:
            _ = write_run(self.records_dir, exercised.summary)
            _ = record_lap(self.records_dir, lap_counts(service, exercised.summary.signatures, len(exercised.summary.gaps)))
        self._block_escalated_signatures(service, exercised)
        if exercised.passed:
            return self._next_surface(exercised.passed, index)
        if exercised.stack_down:
            reason = "\n".join(exercised.lines)
            _ = record_blocker(self.records_dir, Blocker(subject=service, service=service, phase=Phase.EXERCISE, side=Side.APP, reason=reason))
            return self._next_surface(exercised.passed, index)
        return Continue(exercised.passed, self.map_run_failures, index=index, exercised=exercised,
                        run_failures_repaired=run_failures_repaired).because("the book fails its run")

    def _block_escalated_signatures(self, service: str, exercised: ExerciseResult) -> None:
        """Record one blocker per signature the book's writer cannot fix, after dropping the ones an earlier run of this book recorded."""
        for side in SIDE_BY_ESCALATED_CAUSE.values():
            forget_blockers(self.records_dir, Phase.EXERCISE, side, service)
        for signature in _escalated_signatures(exercised):
            reason = _escalation_reason(signature)
            blocker = Blocker(subject=f"{service}: {signature.text()}", service=service, phase=Phase.EXERCISE,
                              side=SIDE_BY_ESCALATED_CAUSE[signature.cause], reason=reason)
            _ = record_blocker(self.records_dir, blocker)

    def _book_failures(self, index: int, exercised: ExerciseResult) -> RunFailures:
        if exercised.summary is None:
            return {}
        spec = spec_dir(self.records_dir) / self.surfaces[index].service
        scenarios, _problems = plan_scenarios(self.root, spec)
        plan = spec / PLAN_NAME
        return exercised.summary.failures_by_page(scenarios, plan.read_text(encoding="utf-8") if plan.is_file() else "")

    def map_run_failures(self, index: int, exercised: ExerciseResult, run_failures_repaired: bool = False) -> Continue[...]:
        """Map each failure of the run the writer can fix to the page that covers it, and hand the book to the writer, since a claim the run cannot exercise is a defect of the book. A run whose every failure is escalated has nothing for the writer. A repair that did not lower the book's failed checks stops the laps, and the attendant is asked with their trend."""
        failures = self._book_failures(index, exercised)
        if not failures and _escalated_signatures(exercised):
            return self._next_surface(exercised.passed, index)
        if not run_failures_repaired:
            return Continue(failures, self.copy_source, index=index, run_failures=failures).because("repair the pages the run failed on")
        service = self.surfaces[index].service
        stall = _stall(exercised, service_laps(read_laps(self.records_dir), service))
        if stall:
            blocker = Blocker(subject=f"{service}: the book's failed checks did not fall", service=service, phase=Phase.EXERCISE,
                              side=Side.WORKFLOW, reason="\n".join((stall, *exercised.lines)))
            _ = record_blocker(self.records_dir, blocker)
            return self._next_surface(exercised.passed, index)
        return Continue(failures, self.copy_source, index=index, run_failures=failures).because(
            "the repair lowered the book's failed checks: repair again"
        )

    def report(self) -> Await[...] | Done:
        """Publish the report. Any blocker stops the run at the operator, whose answer sends each blocked book back through its route."""
        report = build_report(self.root, self.records_dir, self.services)
        page = write_report(self.records_dir, report)
        blockers = read_blockers(self.records_dir)
        if not blockers:
            return Done(report).because("no blocker: the books are done")
        question = (
            f"The run stopped on {len(blockers)} blockers, each listed in {page}. "
            + "Fix the book, ostler, the app or the workflow each one names, and reload the run when you changed its code. "
            + "Answer here, and the run routes each blocked book again: a book that still fails goes back to its repair, "
            + "and every repair turn reads your answer."
        )
        gate_path = self.run_dir / OPERATOR_NAME
        return Await(gate_path, question, self.resume, gate_path=str(gate_path), question=question).because("blockers wait for the operator")

    def resume(self, gate_path: str = "", question: str = "") -> Continue[...]:
        """The operator has fixed what the blockers named, or said how. Their answer is kept for every repair turn."""
        gate_text = Path(gate_path).read_text(encoding="utf-8") if gate_path and Path(gate_path).is_file() else ""
        write_answer(self.records_dir, answer_below(gate_text, question))
        return Continue(None, self.route_blocked).because("the operator's answer is kept for the repair turns")

    def route_blocked(self) -> Continue[...]:
        """The books the blockers named pass again, and every blocker is forgotten, since that pass records again each one that still holds. A blocker that names no service sends every book."""
        blocked = {blocker.service for blocker in read_blockers(self.records_dir)}
        blocked_services = tuple(service for service in self.services if service in blocked)
        write_pass(self.records_dir, blocked_services if blocked_services and "" not in blocked else self.services)
        forget_every_blocker(self.records_dir)
        first = self._routed_after(-1)
        return Continue(None, self.route_book, index=first or 0).because("the operator answered: route the blocked books again")
