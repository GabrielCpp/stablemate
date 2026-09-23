"""Phase 3: bring the stack up from the book, compile every obligation, run the flows, and charge each failure to a side."""
from __future__ import annotations

import time

from workhorse.pyflow import Continue, Done
from workhorse_workflows.okf_book.exercise.nodes import (
    FlowPick,
    Judgement,
    covered_pages,
    covers_of,
    scenario_tokens,
    split_by_budget,
)
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.budget import (
    TURN_BUDGET_TOKENS,
    clip,
    estimated_tokens,
    name_tokens,
    pack_told,
    page_bodies,
    prompt_tokens,
)
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn
from workhorse_workflows.okf_book.shared.page_check import gap_side
from workhorse_workflows.okf_book.shared.scenarios import (
    RunSummary,
    compile_book,
    plan_scenarios,
    read_run,
    run_scenarios,
    spec_dir,
    write_run,
)
from workhorse_workflows.okf_book.shared.work import DONE, JOB, ids
from workhorse_workflows.kit.qa.runner import ensure_stack

PICK_PROMPT = "exercise/prompts/pick-flows.md"
JUDGE_PROMPT = "exercise/prompts/judge-failure.md"
WRITTEN_BUDGET_TOKENS = 4_000
COVERS_BUDGET_TOKENS = 2_000
MESSAGE_BUDGET_TOKENS = 2_000


class Exercise(BookFlow):
    """Phase 3 of the okf-book run: the book brings the stack up, compiles, runs, and has each failure charged to a side."""

    services: tuple[str, ...] = ()

    def _block(self, subject: str, side: Side, reason: str) -> Blocker:
        return record_blocker(self.records_dir, Blocker(subject=subject, phase=Phase.EXERCISE, side=side, reason=reason))

    def start(self) -> Continue[...] | Done:
        """Bring the stack up from the book's runbook alone. A runbook that cannot is the book's blocker."""
        status = ensure_stack(self.logger, repo_dir=str(self.root))
        if status.ready in ("no", "none"):
            _ = self._block("runbook", Side.BOOK, status.notes)
            return Done(status.ready)
        return Continue(status.ready, self.compile_obligations)

    def compile_obligations(self) -> Continue[...] | Done:
        """Compile every obligation the book states. Each one that does not compile is a blocker."""
        compiled = compile_book(self.root, self.services, spec_dir(self.records_dir))
        for gap in compiled.gaps:
            _ = self._block(gap.obligation_id, gap_side(gap), f"{gap.kind}: {gap.detail}")
        if compiled.planned:
            return Continue(len(compiled.gaps), self.pick_flows)
        return Done(len(compiled.gaps))

    def pick_flows(self) -> Continue[...] | Done:
        """One turn picks the scenarios that exercise what this run wrote. An empty pick runs them all."""
        scenarios, problems = plan_scenarios(self.root, spec_dir(self.records_dir))
        if not scenarios:
            reason = " ".join(problems) or "The compiled plan has no scenario."
            _ = self._block("plan", Side.OSTLER, reason)
            return Done(problems)
        written = pack_told(name_tokens(ids(self.work, JOB, DONE)), WRITTEN_BUDGET_TOKENS)
        fixed = prompt_tokens(PICK_PROMPT) + written.tokens
        split = split_by_budget(scenarios, TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        pick = self.agent(
            "exercise/prompts/pick-flows.md",
            returns=FlowPick,
            args={"scenarios": [s.model_dump() for s in split.read], "written": list(written.kept)},
        )
        known = {s.id for s in split.read}
        chosen = tuple(i for i in pick.ids if i in known)
        metric = TurnMetric(
            phase=Phase.EXERCISE,
            node="pick-flows",
            subjects=chosen,
            tokens=fixed + scenario_tokens(split.read),
            minutes=(time.monotonic() - started) / 60,
        )
        only = (*chosen, *split.unread_ids) if chosen else ()
        return Continue(only, self.record_pick, only=only, metric=metric)

    def record_pick(self, only: tuple[str, ...], metric: TurnMetric) -> Continue[...]:
        """Record the pick turn before any scenario runs."""
        record_turn(self.records_dir, metric)
        return Continue(only, self.run_flows, only=only)

    def run_flows(self, only: tuple[str, ...]) -> Continue[...]:
        """Run the picked scenarios against the stack."""
        summary = run_scenarios(self.root, spec_dir(self.records_dir), only)
        return Continue(summary.status, self.record_run, summary=summary)

    def record_run(self, summary: RunSummary) -> Continue[...]:
        """Keep the run's summary for the judgements and the report, before anything reads it."""
        write_run(self.records_dir, summary)
        return Continue(summary.status, self.settle_run, summary=summary)

    def settle_run(self, summary: RunSummary) -> Continue[...] | Done:
        """A plan the runner refuses is ostler's blocker. Each failed scenario goes to a judgement."""
        if summary.problems or summary.runner_errors:
            _ = self._block("plan", Side.OSTLER, " ".join((*summary.problems, *summary.runner_errors)))
        if summary.failed_scenarios:
            return Continue(summary.status, self.judge_failure, failed=summary.failed_scenarios, index=0)
        return Done(summary.status)

    def judge_failure(self, failed: tuple[str, ...], index: int) -> Continue[...]:
        """A turn holding only the book says whether the app or the book is wrong about one failed scenario.

        It reads the run's message, cut to its budget, and the pages the scenario covers, packed into what is left.
        """
        root = self.root
        scenario = failed[index]
        summary = read_run(self.records_dir)
        outcome = summary.scenarios.get(scenario) if summary else None
        message = clip(outcome.message if outcome else "", MESSAGE_BUDGET_TOKENS)
        covers = pack_told(name_tokens(covers_of(root, self.records_dir, scenario)), COVERS_BUDGET_TOKENS)
        fixed = prompt_tokens(JUDGE_PROMPT) + estimated_tokens(len(message)) + covers.tokens
        pages = covered_pages(root, covers.kept, TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        judgement = self.agent(
            "exercise/prompts/judge-failure.md",
            returns=Judgement,
            args={
                "scenario": scenario,
                "covers": list(covers.kept),
                "message": message,
                "pages": [body.template_arg() for body in page_bodies(root, pages.kept)],
            },
        )
        metric = TurnMetric(
            phase=Phase.EXERCISE,
            node="judge-failure",
            subjects=(scenario,),
            tokens=fixed + pages.tokens,
            minutes=(time.monotonic() - started) / 60,
        )
        return Continue(judgement, self.record_judgement, failed=failed, index=index, judgement=judgement, metric=metric)

    def record_judgement(
        self, failed: tuple[str, ...], index: int, judgement: Judgement, metric: TurnMetric
    ) -> Continue[...]:
        """Record the judgement turn before its blocker is written."""
        record_turn(self.records_dir, metric)
        return Continue(metric, self.block_failure, failed=failed, index=index, judgement=judgement)

    def block_failure(self, failed: tuple[str, ...], index: int, judgement: Judgement) -> Continue[...] | Done:
        """Put the judged scenario on the blocker list, charged to the side the judgement named."""
        _ = self._block(failed[index], Side(judgement.side), judgement.reason)
        if index + 1 < len(failed):
            return Continue(judgement, self.judge_failure, failed=failed, index=index + 1)
        return Done(judgement)
