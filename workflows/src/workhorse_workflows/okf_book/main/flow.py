"""The okf-book run: one confined owner per surface writes its whole book, code checks it and runs it between the owner's turns, and the run reports."""
from __future__ import annotations

from pathlib import Path

from ostler.qa.attribution import Cause, Signature
from workhorse.pyflow import Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import last_commit_subject, last_commit_trailer
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.nodes import gate
from workhorse_workflows.okf_book.main.nodes.check_lead import latest_check_findings, record_check, unheld
from workhorse_workflows.okf_book.main.nodes.gate import ESCALATED_SIDES, SIDE_BY_ESCALATED_CAUSE, RunFailures, keep_failures, rerun_command, take_failures
from workhorse_workflows.okf_book.main.nodes.lead_findings import (
    Escalation,
    LeadFinding,
    attributed,
    led_escalations,
    read_findings,
    run_escalations,
    service_findings,
    with_instructions,
)
from workhorse_workflows.okf_book.main.nodes.operator_answer import answer_below, write_answer
from workhorse_workflows.okf_book.main.nodes.progress_ledger import LapCounts, lap_counts, read_laps, record_lap, service_laps, stalled, trend
from workhorse_workflows.okf_book.main.nodes.report import build_report, write_report
from workhorse_workflows.okf_book.main.nodes.stale_citations import Regrounded
from workhorse_workflows.okf_book.main.reground_book_flow import RegroundBook
from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.surface_pass import read_pass, write_pass
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook, WriteOutcome
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, blockers_by_side, forget_blocker, forget_blockers, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_commits import (
    BOOK_TRAILER,
    REPAIRED,
    book_commit_subject,
    repaired_book_commit_subject,
)
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult, stack_down_failures
from workhorse_workflows.okf_book.shared.citations import cites_changed_file
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems
from workhorse_workflows.okf_book.shared.scenarios import PLAN_NAME, plan_scenarios, spec_dir, write_run

OPERATOR_NAME = "operator.md"

WRITER_CAUSES = frozenset({Cause.BOOK, Cause.ARRANGEMENT})


def _book_folder(service: str) -> str:
    return (FEATURES_DIR / service).as_posix()


def _source_folder(root: Path, surface: Surface) -> str:
    entry = Path(surface.entry)
    return (entry if (root / entry).is_dir() else entry.parent).as_posix()


def _escalated_signatures(exercised: ExerciseResult) -> tuple[Signature, ...]:
    """The signatures of the run that a party other than the book's writer must fix."""
    signatures = exercised.summary.signatures if exercised.summary is not None else ()
    return tuple(signature for signature in signatures if signature.cause in SIDE_BY_ESCALATED_CAUSE)


def _stall(exercised: ExerciseResult, laps: tuple[LapCounts, ...]) -> str:
    """Why the lap after a repair did not help, or nothing when it lowered the book's failed checks."""
    if exercised.summary is None:
        return "the run after the repair counted no check, so it cannot show that the repair helped"
    if stalled(laps):
        return f"the repair did not lower the book's failed checks, lap by lap: {trend(laps)}"
    return ""


class OkfBook(BookFlow):
    """The run: each surface's book is written by its owner's turns, each committed, checked and run against the app."""

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
        forget_blockers(self.records_dir, Phase.WRITE, Side.BOOK, service)
        _ = record_blocker(self.records_dir, blocker)
        return self._next_surface(reason, index)

    def route_book(self, index: int, regrounded: bool = False) -> Continue[...]:
        """A missing book, or one the gate left failures for, goes to its owner, so a rerun after the operator's fix repairs what the last run left. A book citing a file that changed since its stamp is regrounded first. A book with problems, or one this workflow last committed, goes through the check again, and any other one goes straight to its run."""
        surface = self.surfaces[index]
        service = surface.service
        book = _book_folder(service)
        if not (self.root / book).is_dir():
            return Continue(None, self.copy_source, index=index).because("no book yet: write it")
        if not regrounded and cites_changed_file(self.root, service):
            return Continue(service, self.reground_book, index=index).because("the code the book cites has changed: read the changes first")
        pending = take_failures(self.records_dir, service)
        if pending:
            return Continue(pending, self.copy_source, index=index, run_failures=pending).because(
                "the gate left this book's owner failures to fix"
            )
        found = page_problems(self.root, service, _source_folder(self.root, surface))
        if found:
            return Continue(len(found), self.check_book, index=index).because("the existing book has problems: check it")
        _ = record_check(self.records_dir, self.root, service, found)
        ours = last_commit_subject(self.root, book) in (book_commit_subject(service), repaired_book_commit_subject(service))
        if ours or last_commit_trailer(self.root, BOOK_TRAILER, book) == REPAIRED:
            return Continue(book, self.check_book, index=index).because("this workflow wrote the book: check it")
        return Continue(found, self.run_book, index=index, run_failures_repaired=False).because(
            "the existing book checks clean"
        )

    def reground_book(self, index: int) -> Continue[...]:
        """Hand the book to its regrounding. The nodes a change bears on are kept as failures for the book's owner, and the book is routed again."""
        service = self.surfaces[index].service
        regrounded = Regrounded.model_validate(self.handoff(RegroundBook, parent_records_dir=str(self.records_dir), service=service))
        keep_failures(self.records_dir, service, regrounded.failures)
        return Continue(regrounded, self.route_book, index=index, regrounded=True).because("the changed files are read: route the book")

    def copy_source(
        self, index: int, run_failures: RunFailures | None = None, problems: tuple[PageProblem, ...] = (), exercised: ExerciseResult | None = None,
    ) -> Continue[...]:
        """Copy the surface's product source for its owner. A surface whose source is no folder is a blocker."""
        surface = self.surfaces[index]
        source = _source_folder(self.root, surface)
        if not (self.root / source).is_dir():
            return self._block_surface_and_move_on(index, f"the entry {surface.entry} is in no source folder")
        view = build_source_view(self.root, source)
        return Continue(view.as_posix(), self.write_book, index=index, run_failures=run_failures, problems=problems, exercised=exercised).because(
            "send the book's owner"
        )

    def write_book(
        self, index: int, run_failures: RunFailures | None = None, problems: tuple[PageProblem, ...] = (), exercised: ExerciseResult | None = None,
    ) -> Continue[...]:
        """Hand the book to one turn of its owner, with the gates it last failed. A turn sent the failures of a run is a repair, and the run after it must lower them."""
        surface = self.surfaces[index]
        written = WriteOutcome.model_validate(
            self.handoff(
                WriteBook,
                parent_records_dir=str(self.records_dir),
                surface=surface,
                book_folder=_book_folder(surface.service),
                source_folder=_source_folder(self.root, surface),
                exercised=exercised,
                problems=problems,
                run_failures=run_failures or {},
            )
        )
        return Continue(
            written, self.settle_write, index=index, written=written, run_failures_repaired=run_failures is not None
        ).because("settle the owner's turn")

    def settle_write(self, index: int, written: WriteOutcome, run_failures_repaired: bool = False) -> Continue[...]:
        """A turn that ended without a reply and left no page is a blocker on the surface. A committed book goes to its check, whatever ended the turn that wrote it, since the check judges the pages and not the turn."""
        if not written.committed:
            return self._block_surface_and_move_on(index, written.failure)
        if written.failure:
            self.logger.warning("%s: %s; the pages it left go to the check", self.surfaces[index].service, written.failure)
        return Continue(written, self.check_book, index=index, run_failures_repaired=run_failures_repaired, repaired=True).because(
            "check the committed book"
        )

    def check_book(self, index: int, run_failures_repaired: bool = False, repaired: bool = False) -> Continue[...]:
        """Repeat the owner's own page check. A problem in a group the owner named another side's is held: it is a blocker on that side. Each problem left is a blocker on its page, and goes back to the owner. After its turn the problems left go back only when they are fewer than the last check left, so a person is asked only about what a turn did not lower."""
        surface = self.surfaces[index]
        service = surface.service
        problems = page_problems(self.root, service, _source_folder(self.root, surface))
        findings = latest_check_findings(read_findings(self.records_dir), service)
        left = unheld(problems, findings)
        before = record_check(self.records_dir, self.root, service, problems, findings)
        if left and (not repaired or not before or len(left) < before):
            return Continue(len(left), self.copy_source, index=index, problems=problems, run_failures={} if run_failures_repaired else None).because(
                "the check finds problems the book holds: back to its owner"
            )
        return Continue(problems, self.run_book, index=index, run_failures_repaired=run_failures_repaired).because("run the book against the app")

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

    def _owned(self, service: str, exercised: ExerciseResult) -> tuple[ExerciseResult, tuple[LeadFinding, ...]]:
        """The run with each group the owner named moved to the side it named, and what it named."""
        findings = service_findings(read_findings(self.records_dir), service)
        return attributed(exercised, findings), findings

    def settle_run(self, index: int, run_failures_repaired: bool, exercised: ExerciseResult) -> Continue[...]:
        """A passing book is done. A run the runner itself stopped measured nothing of the book, so it is a blocker on the runner's side and no lap. Each failure another party must fix is a blocker, one per signature, on the side the owner named when it named one. A stack that cannot come up goes to the owner of the runbooks it came up from, and is a blocker on the app when the book declares none or the owner's repair left it down. A book whose run failed goes to the mapping of its failures. Either way the book stays."""
        service = self.surfaces[index].service
        if gate.block_stopped_runner(self.records_dir, service, exercised):
            return self._next_surface(exercised.passed, index)
        if exercised.summary is not None:
            _ = write_run(self.records_dir, exercised.summary)
            _ = record_lap(self.records_dir, lap_counts(service, exercised.summary.signatures, len(exercised.summary.gaps),
                                                        probes_only=exercised.stopped_at_probes,
                                                        stopped_on=exercised.summary.stopped_on))
        led, findings = self._owned(service, exercised)
        self._block_escalated_signatures(service, led, led_escalations(exercised, led, findings) if findings else None)
        if exercised.passed:
            return self._next_surface(exercised.passed, index)
        runbooks = {} if run_failures_repaired else stack_down_failures(self.root, service, exercised)
        if runbooks:
            return Continue(runbooks, self.copy_source, index=index, run_failures=runbooks, exercised=exercised).because(
                "the stack cannot come up: repair its runbook"
            )
        if exercised.stack_down:
            _ = record_blocker(self.records_dir, Blocker(subject=service, service=service, phase=Phase.EXERCISE, side=Side.APP, reason="\n".join(line for line in exercised.lines if not line.startswith("gap: "))))
            return self._next_surface(exercised.passed, index)
        return Continue(exercised.passed, self.map_run_failures, index=index, exercised=exercised,
                        run_failures_repaired=run_failures_repaired).because("the book fails its run")

    def _block_escalated_signatures(self, service: str, exercised: ExerciseResult, escalations: tuple[Escalation, ...] | None = None) -> None:
        """Record one blocker per signature the book's owner cannot fix, after dropping the ones an earlier run of this book recorded."""
        for side in ESCALATED_SIDES:
            forget_blockers(self.records_dir, Phase.EXERCISE, side, service)
        for signature, side, reason in run_escalations(exercised) if escalations is None else escalations:
            _ = record_blocker(self.records_dir, self._signature_blocker(service, exercised, signature, side, reason))

    def _signature_blocker(self, service: str, exercised: ExerciseResult, signature: Signature, side: Side, reason: str) -> Blocker:
        pages = exercised.summary.signature_pages(signature) if exercised.summary is not None else ()
        return Blocker(subject=f"{service}: {signature.text()}", service=service, phase=Phase.EXERCISE, side=side, reason=reason,
                       cause=signature.cause.value, pages=pages, rerun=rerun_command(self.records_dir, service, Phase.EXERCISE, pages))

    def _book_failures(self, index: int, exercised: ExerciseResult) -> RunFailures:
        if exercised.summary is None:
            return {}
        spec = spec_dir(self.records_dir) / self.surfaces[index].service
        scenarios, _problems = plan_scenarios(self.root, spec)
        plan = spec / PLAN_NAME
        return exercised.summary.failures_by_page(scenarios, plan.read_text(encoding="utf-8") if plan.is_file() else "")

    def map_run_failures(self, index: int, exercised: ExerciseResult, run_failures_repaired: bool = False) -> Continue[...]:
        """Map each failure of the run the owner can fix to the page that covers it, and hand the book back to its owner with the whole run, since a claim the run cannot exercise is a defect of the book. A run whose every failure is escalated has nothing for the owner. A turn that did not lower the book's failed checks stops the laps, and the attendant is asked with their trend."""
        service = self.surfaces[index].service
        led, findings = self._owned(service, exercised)
        failures = with_instructions(self._book_failures(index, led), findings)
        if not failures and _escalated_signatures(led):
            return self._next_surface(exercised.passed, index)
        if not run_failures_repaired:
            return Continue(failures, self.copy_source, index=index, run_failures=failures, exercised=exercised).because(
                "the book's owner repairs what the run failed on"
            )
        stall = _stall(exercised, service_laps(read_laps(self.records_dir), service))
        if stall:
            self._block_stall(service, led, stall, failures)
            return self._next_surface(exercised.passed, index)
        return Continue(failures, self.copy_source, index=index, run_failures=failures, exercised=exercised).because(
            "the owner's turn lowered the book's failed checks: send it again"
        )

    def _block_stall(self, service: str, exercised: ExerciseResult, stall: str, failures: RunFailures) -> None:
        """Record one blocker per defect the book's owner could not fix, with its pages and the command that reruns them, or one on the workflow when no signature names one."""
        signatures = exercised.summary.signatures if exercised.summary is not None else ()
        mine = [signature for signature in signatures if signature.cause in WRITER_CAUSES]
        for signature in mine:
            reason = f"{stall}; {signature.count} checks failed this way, for example {signature.sample}"
            _ = record_blocker(self.records_dir, self._signature_blocker(service, exercised, signature, Side.BOOK, reason))
        if not mine:
            pages = tuple(failures)
            _ = record_blocker(self.records_dir, Blocker(
                subject=f"{service}: the book's failed checks did not fall", service=service, phase=Phase.EXERCISE,
                side=Side.WORKFLOW, reason="\n".join((stall, *exercised.lines)), pages=pages,
                rerun=rerun_command(self.records_dir, service, Phase.EXERCISE, pages)))

    def report(self) -> Await[...] | Done:
        """Publish the report. Any blocker stops the run at a gate, whose answer has the run settle each blocker itself."""
        report = build_report(self.root, self.records_dir, self.services)
        page = write_report(self.records_dir, report)
        blockers = read_blockers(self.records_dir)
        if not blockers:
            return Done(report).because("no blocker: the books are done")
        gate.open_gate(self.root, self.records_dir, self.services)
        question = (
            f"The run stopped on {len(blockers)} blockers ({blockers_by_side(blockers)}), each listed in {page} with its cause, its pages "
            + "and the command that reruns only its checks. "
            + "Fix the book, ostler, the app or the workflow each one names, and reload the run when you changed its code. "
            + "Answer here, and the run reruns each blocker's checks itself: it closes those that pass, keeps those another party "
            + "must still fix, and sends the rest to their writers with the new result. A claim's expected outcome you changed "
            + "goes back to its page's writer as a finding. Fixture, precondition and setup edits stay as you made them."
        )
        gate_path = self.run_dir / OPERATOR_NAME
        return Await(gate_path, question, self.resume, gate_path=str(gate_path), question=question).because("blockers wait for the operator")

    def resume(self, gate_path: str = "", question: str = "") -> Continue[...]:
        """The operator has fixed what the blockers named, or said how. Each book's owner reads their answer on its next turn."""
        gate_text = Path(gate_path).read_text(encoding="utf-8") if gate_path and Path(gate_path).is_file() else ""
        write_answer(self.records_dir, answer_below(gate_text, question))
        return Continue(None, self.settle_gate).because("the operator's answer is kept for the owners")

    def settle_gate(self) -> Continue[...]:
        """Rerun each blocker's checks, close those that pass, and leave each writer what still fails and every claim the answer changed."""
        routed = gate.settle_gate(self.root, self.records_dir, self.services)
        return Continue(routed, self.route_blocked, routed=routed).because("the gate's blockers are settled")

    def route_blocked(self, routed: tuple[str, ...] | None = None) -> Continue[...]:
        """The books the gate's settlement routes pass again, and their blockers are forgotten, since that pass records again each one that still holds. Blockers left only on another party reopen the gate. Without a settlement, the books the blockers named pass again, and a blocker that names no service sends every book."""
        blockers = read_blockers(self.records_dir)
        if routed is None:
            named = {blocker.service for blocker in blockers}
            routed = tuple(service for service in self.services if service in named and "" not in named) or self.services
        if not routed:
            return Continue(None, self.report).because("every blocker left waits on another party: reopen the gate")
        write_pass(self.records_dir, routed)
        for blocker in blockers:
            if blocker.service in routed or not blocker.service:
                forget_blocker(self.records_dir, blocker)
        first = self._routed_after(-1)
        return Continue(None, self.route_book, index=first or 0).because("the operator answered: route the blocked books again")
