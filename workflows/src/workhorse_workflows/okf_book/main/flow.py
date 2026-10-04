"""The okf-book run: one confined writer per surface writes its whole book, then the run checks it, runs it and reports."""
from __future__ import annotations

from pathlib import Path

from ostler.qa.attribution import Cause, Signature
from workhorse.pyflow import Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import last_commit_subject, last_commit_trailer
from workhorse_workflows.okf_book.main.exercise_book_flow import ExerciseBook
from workhorse_workflows.okf_book.main.nodes import gate
from workhorse_workflows.okf_book.main.lead_lap_flow import LeadLap
from workhorse_workflows.okf_book.main.nodes.gate import ESCALATED_SIDES, SIDE_BY_ESCALATED_CAUSE, RunFailures, keep_failures, rerun_command, take_failures
from workhorse_workflows.okf_book.main.nodes.lead_findings import (
    Escalation,
    LeadFinding,
    LedLap,
    attributed,
    lead_groups,
    led_escalations,
    run_escalations,
    with_instructions,
)
from workhorse_workflows.okf_book.main.nodes.operator_answer import answer_below, write_answer
from workhorse_workflows.okf_book.main.nodes.progress_ledger import LapCounts, lap_counts, read_laps, record_lap, service_laps, stalled, trend
from workhorse_workflows.okf_book.main.nodes.repair_ledger import RepairOutcome
from workhorse_workflows.okf_book.main.repair_book_flow import RepairBook
from workhorse_workflows.okf_book.main.nodes.report import build_report, write_report
from workhorse_workflows.okf_book.main.nodes.stale_citations import Regrounded
from workhorse_workflows.okf_book.main.reground_book_flow import RegroundBook
from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view, source_view_folder
from workhorse_workflows.okf_book.main.nodes.surface import Surface
from workhorse_workflows.okf_book.main.nodes.surface_pass import read_pass, write_pass
from workhorse_workflows.okf_book.main.nodes.turn_budget import (
    ceiling_blocker_reason,
    folder_tokens,
    source_and_book_tokens,
)
from workhorse_workflows.okf_book.main.write_book_flow import WriteBook, WriteOutcome
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, blockers_by_side, forget_blocker, forget_blockers, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_commits import (
    BOOK_TRAILER,
    REPAIRED,
    book_commit_subject,
    repaired_book_commit_subject,
)
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.citations import book_pages, cites_changed_file
from workhorse_workflows.okf_book.main.nodes.root_entries import NO_ENTRY_PAGE, entry_links
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR, read_entries
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems, tool_blockers
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
        forget_blockers(self.records_dir, Phase.WRITE, Side.BOOK, service)
        _ = record_blocker(self.records_dir, blocker)
        return self._next_surface(reason, index)

    def route_book(self, index: int, regrounded: bool = False) -> Continue[...]:
        """A missing book, or one with problems, goes to the writer, so a rerun after the operator's fix repairs what the last run left. A book citing a file that changed since its stamp is regrounded first. A book this workflow's writer or repair last committed with no problem goes through the check again, and any other one goes straight to its run."""
        service = self.surfaces[index].service
        book = _book_folder(service)
        if not (self.root / book).is_dir():
            return Continue(None, self.copy_source, index=index).because("no book yet: write it")
        if not regrounded and cites_changed_file(self.root, service):
            return Continue(service, self.reground_book, index=index).because("the code the book cites has changed: read the changes first")
        pending = take_failures(self.records_dir, service)
        if pending:
            return Continue(pending, self.copy_source, index=index, run_failures=pending).because(
                "the gate left this book's writer failures to fix"
            )
        found = page_problems(self.root, service)
        problems = tuple(problem.text for problem in found)
        _ = self._record_check(service, found)
        if problems:
            return Continue(problems, self.copy_source, index=index).because("the existing book has problems")
        ours = last_commit_subject(self.root, book) in (book_commit_subject(service), repaired_book_commit_subject(service))
        if ours or last_commit_trailer(self.root, BOOK_TRAILER, book) == REPAIRED:
            return Continue(book, self.check_book, index=index).because("this workflow wrote the book: check it")
        return Continue(problems, self.run_book, index=index, run_failures_repaired=False).because(
            "the existing book checks clean"
        )

    def reground_book(self, index: int) -> Continue[...]:
        """Hand the book to its regrounding. The nodes a change bears on are kept as failures for the book's writer, and the book is routed again."""
        service = self.surfaces[index].service
        regrounded = Regrounded.model_validate(self.handoff(RegroundBook, parent_records_dir=str(self.records_dir), service=service))
        keep_failures(self.records_dir, service, regrounded.failures)
        return Continue(regrounded, self.route_book, index=index, regrounded=True).because("the changed files are read: route the book")

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
        """A book over the ceiling one writer reads is repaired a batch of pages at a time, with the failures of the run it failed. A surface with no book over it is a blocker, and so is one whose book has no entry page, since no repair turn can make its pages reachable."""
        surface = self.surfaces[index]
        view = source_view_folder(self.root, _source_folder(self.root, surface))
        tokens = source_and_book_tokens(folder_tokens(view), folder_tokens(self.root / _book_folder(surface.service)))
        reason = ceiling_blocker_reason(tokens)
        if reason is None:
            return Continue(tokens, self.write_book, index=index, run_failures_repaired=run_failures is not None).because(
                "the source fits one writer"
            )
        if entry_links(self.root, surface.service) or read_entries(self.root, surface.service):
            return Continue(tokens, self.repair_book, index=index, run_failures=run_failures).because(
                "the book is over one writer: repair it in batches"
            )
        if book_pages(self.root, surface.service):
            reason = f"{NO_ENTRY_PAGE} {reason}"
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

    def _record_check(self, service: str, problems: tuple[PageProblem, ...]) -> int:
        """Make each problem of a check a blocker on its page, in place of the ones the last check left. Returns how many that one left."""
        before = sum(1 for blocker in read_blockers(self.records_dir)
                     if blocker.phase is Phase.WRITE and blocker.side is Side.BOOK and blocker.service == service)
        forget_blockers(self.records_dir, Phase.WRITE, Side.BOOK, service)
        forget_blockers(self.records_dir, Phase.WRITE, Side.ENVIRONMENT, service)
        for tool in tool_blockers(self.root, service):
            _ = record_blocker(self.records_dir, tool)
        for problem in problems:
            blocker = Blocker(subject=f"{service}: {problem.text}", service=service, phase=Phase.WRITE, side=Side.BOOK, reason=problem.text,
                              cause=Cause.BOOK.value, pages=(problem.page,),
                              rerun=rerun_command(self.records_dir, service, Phase.WRITE, (problem.page,)))
            _ = record_blocker(self.records_dir, blocker)
        return before

    def check_book(self, index: int, run_failures_repaired: bool = False) -> Continue[...]:
        """Repeat the writer's own page check. Each problem it finds is a blocker on its page, and one an earlier check found that this one does not is no longer. A book with fewer problems than its last check found goes back to its repair, so a person is asked only about what a repair did not lower."""
        service = self.surfaces[index].service
        problems = page_problems(self.root, service)
        before = self._record_check(service, problems)
        if problems and (not before or len(problems) < before):
            return Continue(problems, self.copy_source, index=index, run_failures={} if run_failures_repaired else None).because(
                "the check finds fewer problems than the last one did: repair what is left"
            )
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
            _ = record_lap(self.records_dir, lap_counts(service, exercised.summary.signatures, len(exercised.summary.gaps),
                                                        probes_only=exercised.stopped_at_probes))
        self._block_escalated_signatures(service, exercised)
        if exercised.passed:
            return self._next_surface(exercised.passed, index)
        if exercised.stack_down:
            reason = "\n".join(exercised.lines)
            _ = record_blocker(self.records_dir, Blocker(subject=service, service=service, phase=Phase.EXERCISE, side=Side.APP, reason=reason))
            return self._next_surface(exercised.passed, index)
        if lead_groups(exercised):
            return Continue(exercised.passed, self.lead_lap, index=index, exercised=exercised,
                            run_failures_repaired=run_failures_repaired).because("the book fails its run: the lead reads the whole lap first")
        return Continue(exercised.passed, self.map_run_failures, index=index, exercised=exercised,
                        run_failures_repaired=run_failures_repaired).because("the book fails its run")

    def lead_lap(self, index: int, exercised: ExerciseResult, run_failures_repaired: bool = False) -> Continue[...]:
        """Hand the lap to its lead, which names the side of each group of failed checks before any page is repaired. Each group it named another side's is a blocker on that side, and the rest go to their mapping as it attributed them. A lead that named nothing leaves the run's own attribution."""
        service = self.surfaces[index].service
        led = LedLap.model_validate(self.handoff(LeadLap, parent_records_dir=str(self.records_dir), service=service, exercised=exercised))
        result = attributed(exercised, led.findings)
        if led.findings:
            self._block_escalated_signatures(service, result, led_escalations(exercised, result, led.findings))
        return Continue(led, self.map_run_failures, index=index, exercised=result, run_failures_repaired=run_failures_repaired,
                        lead=led.findings).because("map the failures the lead left to the book")

    def _block_escalated_signatures(self, service: str, exercised: ExerciseResult, escalations: tuple[Escalation, ...] | None = None) -> None:
        """Record one blocker per signature the book's writer cannot fix, after dropping the ones an earlier run of this book recorded."""
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

    def map_run_failures(
        self, index: int, exercised: ExerciseResult, run_failures_repaired: bool = False, lead: tuple[LeadFinding, ...] = (),
    ) -> Continue[...]:
        """Map each failure of the run the writer can fix to the page that covers it, and hand the book to the writer, since a claim the run cannot exercise is a defect of the book. A run whose every failure is escalated has nothing for the writer. A repair that did not lower the book's failed checks stops the laps, and the attendant is asked with their trend."""
        failures = with_instructions(self._book_failures(index, exercised), lead)
        if not failures and _escalated_signatures(exercised):
            return self._next_surface(exercised.passed, index)
        if not run_failures_repaired:
            return Continue(failures, self.copy_source, index=index, run_failures=failures).because("repair the pages the run failed on")
        service = self.surfaces[index].service
        stall = _stall(exercised, service_laps(read_laps(self.records_dir), service))
        if stall:
            self._block_stall(service, exercised, stall, failures)
            return self._next_surface(exercised.passed, index)
        return Continue(failures, self.copy_source, index=index, run_failures=failures).because(
            "the repair lowered the book's failed checks: repair again"
        )

    def _block_stall(self, service: str, exercised: ExerciseResult, stall: str, failures: RunFailures) -> None:
        """Record one blocker per defect the book's writer could not fix, with its pages and the command that reruns them, or one on the workflow when no signature names one."""
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
        """The operator has fixed what the blockers named, or said how. Their answer is kept for every repair turn."""
        gate_text = Path(gate_path).read_text(encoding="utf-8") if gate_path and Path(gate_path).is_file() else ""
        write_answer(self.records_dir, answer_below(gate_text, question))
        return Continue(None, self.settle_gate).because("the operator's answer is kept for the repair turns")

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
