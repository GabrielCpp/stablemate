"""Phase 3: bring the stack up from the book, compile every obligation, run the flows, and stop at the operator once."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from workhorse.pyflow import Await, Continue, Done
from workhorse_workflows.okf_book.book_run import BookRun
from workhorse_workflows.okf_book.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.budget import (
    TURN_BUDGET_TOKENS,
    Packed,
    clip,
    estimated_tokens,
    file_tokens,
    name_tokens,
    pack_told,
    page_bodies,
    prompt_tokens,
)
from workhorse_workflows.okf_book.exercise import (
    RunSummary,
    Scenario,
    compile_book,
    plan_scenarios,
    read_run,
    run_scenarios,
    spec_dir,
    write_run,
)
from workhorse_workflows.okf_book.settled import committed_jobs
from workhorse_workflows.okf_book.metrics import TurnMetric, record_turn
from workhorse_workflows.okf_book.page_check import gap_side, obligation_page
from workhorse_workflows.okf_book.report import build_report, read_report, write_report
from workhorse_workflows.qa.runner import ensure_stack

OPERATOR_NAME = "operator.md"
PICK_PROMPT = "prompts/pick-flows.md"
JUDGE_PROMPT = "prompts/judge-failure.md"
WRITTEN_BUDGET_TOKENS = 4_000
COVERS_BUDGET_TOKENS = 2_000
MESSAGE_BUDGET_TOKENS = 2_000


class FlowPick(BaseModel):
    """The scenarios a turn chose to run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ids: tuple[str, ...]


class Judgement(BaseModel):
    """Which side a failed scenario is charged to, and why, as an agent holding only the book reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    side: Literal["app", "book"]
    reason: str


def _scenario_tokens(scenarios: tuple[Scenario, ...]) -> int:
    return estimated_tokens(sum(len(s.model_dump_json()) for s in scenarios))


def _covers_of(root: Path, run_dir: Path, scenario: str) -> tuple[str, ...]:
    scenarios, _problems = plan_scenarios(root, spec_dir(run_dir))
    return next((s.covers for s in scenarios if s.id == scenario), ())


def _covered_pages(root: Path, covers: tuple[str, ...], budget: int) -> Packed:
    named = dict.fromkeys(obligation_page(obligation) for obligation in covers)
    return pack_told(file_tokens(root, (page for page in named if page and (root / page).is_file())), budget)


@dataclass(frozen=True, slots=True)
class ScenarioSplit:
    """The scenarios one turn reads within budget, and the ids of the rest, which run without being picked."""

    read: tuple[Scenario, ...]
    unread_ids: tuple[str, ...]


def split_by_budget(scenarios: tuple[Scenario, ...], budget: int) -> ScenarioSplit:
    """The scenarios in order while they fit the budget, and every one after the first that does not."""
    read: list[Scenario] = []
    spent = 0
    for scenario in scenarios:
        spent += _scenario_tokens((scenario,))
        if spent > budget:
            break
        read.append(scenario)
    return ScenarioSplit(tuple(read), tuple(s.id for s in scenarios[len(read):]))


class Exercise(BookRun):
    """Phase 3 of the okf-book run, and the gate every phase's blockers reach."""

    def _block(self, subject: str, side: Side, reason: str) -> Blocker:
        return record_blocker(self.run_dir, Blocker(subject=subject, phase=Phase.EXERCISE, side=side, reason=reason))

    def bring_up(self) -> Continue[...]:
        """Bring the stack up from the book's runbook alone. A runbook that cannot is the book's blocker."""
        status = ensure_stack(self.logger, repo_dir=str(self.root))
        if status.ready in ("no", "none"):
            _ = self._block("runbook", Side.BOOK, status.notes)
            return Continue(status.ready, self.report)
        return Continue(status.ready, self.compile_obligations)

    def compile_obligations(self) -> Continue[...]:
        """Compile every obligation the book states. Each one that does not compile is a blocker."""
        compiled = compile_book(self.root, self.work_set.services, spec_dir(self.run_dir))
        for gap in compiled.gaps:
            _ = self._block(gap.obligation_id, gap_side(gap), f"{gap.kind}: {gap.detail}")
        if compiled.planned:
            return Continue(len(compiled.gaps), self.pick_flows)
        return Continue(len(compiled.gaps), self.report)

    def pick_flows(self) -> Continue[...]:
        """One turn picks the scenarios that exercise what this run wrote. An empty pick runs them all."""
        scenarios, problems = plan_scenarios(self.root, spec_dir(self.run_dir))
        if not scenarios:
            reason = " ".join(problems) or "The compiled plan has no scenario."
            _ = self._block("plan", Side.OSTLER, reason)
            return Continue(problems, self.report)
        written = pack_told(name_tokens(job.subject for job in committed_jobs(self.run_dir)), WRITTEN_BUDGET_TOKENS)
        fixed = prompt_tokens(PICK_PROMPT) + written.tokens
        split = split_by_budget(scenarios, TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        pick = self.agent(
            "prompts/pick-flows.md",
            returns=FlowPick,
            args={"scenarios": [s.model_dump() for s in split.read], "written": list(written.kept)},
        )
        known = {s.id for s in split.read}
        chosen = tuple(i for i in pick.ids if i in known)
        metric = TurnMetric(
            phase=Phase.EXERCISE,
            node="pick-flows",
            subjects=chosen,
            tokens=fixed + _scenario_tokens(split.read),
            minutes=(time.monotonic() - started) / 60,
        )
        only = (*chosen, *split.unread_ids) if chosen else ()
        return Continue(only, self.record_pick, only=only, metric=metric)

    def record_pick(self, only: tuple[str, ...], metric: TurnMetric) -> Continue[...]:
        """Record the pick turn before any scenario runs."""
        record_turn(self.run_dir, metric)
        return Continue(only, self.run_flows, only=only)

    def run_flows(self, only: tuple[str, ...]) -> Continue[...]:
        """Run the picked scenarios against the stack."""
        summary = run_scenarios(self.root, spec_dir(self.run_dir), only)
        return Continue(summary.status, self.record_run, summary=summary)

    def record_run(self, summary: RunSummary) -> Continue[...]:
        """Keep the run's summary for the judgements and the report, before anything reads it."""
        write_run(self.run_dir, summary)
        return Continue(summary.status, self.settle_run, summary=summary)

    def settle_run(self, summary: RunSummary) -> Continue[...]:
        """A plan the runner refuses is ostler's blocker. Each failed scenario goes to a judgement."""
        if summary.problems or summary.runner_errors:
            _ = self._block("plan", Side.OSTLER, " ".join((*summary.problems, *summary.runner_errors)))
        if summary.failed_scenarios:
            return Continue(summary.status, self.judge_failure, failed=summary.failed_scenarios, index=0)
        return Continue(summary.status, self.report)

    def judge_failure(self, failed: tuple[str, ...], index: int) -> Continue[...]:
        """A turn holding only the book says whether the app or the book is wrong about one failed scenario.

        It reads the run's message, cut to its budget, and the pages the scenario covers, packed into what is left.
        """
        root = self.root
        scenario = failed[index]
        summary = read_run(self.run_dir)
        outcome = summary.scenarios.get(scenario) if summary else None
        message = clip(outcome.message if outcome else "", MESSAGE_BUDGET_TOKENS)
        covers = pack_told(name_tokens(_covers_of(root, self.run_dir, scenario)), COVERS_BUDGET_TOKENS)
        fixed = prompt_tokens(JUDGE_PROMPT) + estimated_tokens(len(message)) + covers.tokens
        pages = _covered_pages(root, covers.kept, TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        judgement = self.agent(
            "prompts/judge-failure.md",
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
        record_turn(self.run_dir, metric)
        return Continue(metric, self.block_failure, failed=failed, index=index, judgement=judgement)

    def block_failure(self, failed: tuple[str, ...], index: int, judgement: Judgement) -> Continue[...]:
        """Put the judged scenario on the blocker list, charged to the side the judgement named."""
        _ = self._block(failed[index], Side(judgement.side), judgement.reason)
        if index + 1 < len(failed):
            return Continue(judgement, self.judge_failure, failed=failed, index=index + 1)
        return Continue(judgement, self.report)

    def report(self) -> Await[...] | Done:
        """Publish the report. Any blocker from any phase stops the run at the operator, once."""
        report = build_report(self.root, self.run_dir, self.work_set)
        page = write_report(self.run_dir, report)
        blockers = read_blockers(self.run_dir)
        if not blockers:
            return Done(report)
        return Await(
            self.run_dir / OPERATOR_NAME,
            f"The run stopped on {len(blockers)} blockers, each listed in {page}. "
            + "Fix the book, ostler, the app or the workflow each one names, then restart the run. "
            + "Answer here to close this run.",
            self.finish,
        )

    def finish(self) -> Done:
        """The operator has read the report."""
        return Done(read_report(self.run_dir))
