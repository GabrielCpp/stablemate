"""One service's book run against the app: compile the book, bring the stack up, and run every scenario."""
from __future__ import annotations

from workhorse.pyflow import Continue, Done
from workhorse_workflows.okf_book.shared.book_run import bring_up, compile_scenarios, failed_run, run_plan, stack_down_result
from workhorse_workflows.okf_book.shared.book_flow import BookFlow

SPEC_DIR = "spec"


class ExerciseBook(BookFlow):
    """Runs one service's book against the real app, and ends on what the run did for the caller to settle."""

    service: str = ""

    def start(self) -> Continue[...] | Done:
        """Compile the book into scenarios. A book that compiles to no plan has failed its run."""
        outcome = compile_scenarios(self.root, self.service, self.records_dir / SPEC_DIR / self.service)
        if not outcome.planned:
            return Done(failed_run(outcome.gaps, "the book compiles to no plan")).because("the book compiles to no plan")
        return Continue(outcome, self.bring_up_stack, gaps=outcome.gaps).because("bring the app's stack up")

    def bring_up_stack(self, gaps: tuple[str, ...]) -> Continue[...] | Done:
        """Bring the app's stack up, or adopt one serving. A stack that cannot come up ends the run."""
        stack = bring_up(self.logger, self.root, self.service)
        if not stack.up:
            return Done(stack_down_result(gaps, stack.notes)).because("the app's stack cannot come up")
        return Continue(stack, self.run_scenarios, gaps=gaps, serving=stack.serving).because("run the scenarios")

    def run_scenarios(self, gaps: tuple[str, ...], serving: bool) -> Done:
        """Run every scenario against the app, on a copy of it when it serves nothing."""
        exercised = run_plan(self.root, self.records_dir / SPEC_DIR / self.service, gaps, serving)
        return Done(exercised).because("the scenarios ran")
