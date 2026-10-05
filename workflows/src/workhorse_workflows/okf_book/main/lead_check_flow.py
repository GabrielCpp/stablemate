"""The lead of one page check: one wide turn reads every problem the check found before any page is repaired, and names the side each rule's problems sit on.

A page repair can only edit its pages, so a problem the toolchain raises because it cannot yet
express what the page rightly says is never fixed by one: the repair weakens the page until the
rule stops firing. The lead sees every group of the check, every problem kept in one file and what
earlier leads of the check named, and its verdict decides which problems reach a page repair. It
runs on the strongest model the run has and changes no file: code puts back what its turn wrote.
"""
from __future__ import annotations

import time
from pathlib import Path

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Continue, Done
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.okf_book.main.lead_lap_flow import LEAD_PROFILE, LEAD_TIMEOUT
from workhorse_workflows.okf_book.main.nodes.check_lead import check_findings, check_lead_template_args, next_check_lap, write_check_problems
from workhorse_workflows.okf_book.main.nodes.lead_findings import LeadVerdict, LedLap, read_findings, record_findings, service_findings
from workhorse_workflows.okf_book.main.nodes.source_view import turn_folder
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import changed_since, restore, snapshot
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.page_check import PageProblem

CHECK_LEAD_PROMPT = "main/prompts/lead-check.md"
CHECK_LEAD_FOLDER = "lead-check"


class LeadCheck(BookFlow):
    """Sends one lead turn over a page check, and ends on what it named for the caller to route."""

    service: str = ""
    problems: tuple[PageProblem, ...] = ()

    def start(self) -> Continue[...]:
        """Send the lead turn. A turn that ends without a verdict names nothing, and what the last lead of the check named stands."""
        earlier = service_findings(read_findings(self.records_dir), self.service, measured="check")
        kept = write_check_problems(turn_folder(self.root, CHECK_LEAD_FOLDER), self.problems)
        before = snapshot(self.root)
        started = time.monotonic()
        verdict: LeadVerdict | None = None
        try:
            verdict = self.agent(
                CHECK_LEAD_PROMPT,
                returns=LeadVerdict,
                power="high",
                timeout=LEAD_TIMEOUT,
                args=check_lead_template_args(self.service, self.problems, earlier, kept),
                cwd=self.root,
                profile=LEAD_PROFILE,
            )
        except (AgentTurnFailed, AgentTimeout, OutputParseError) as ended:
            self.logger.warning("the lead turn on %s's page check ended without a verdict: %s", self.service, ended)
        _ = restore(self.root, changed_since(self.root, before), before)
        node = Path(CHECK_LEAD_PROMPT).stem
        metric = turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        return Continue(verdict, self.record_lead, verdict=verdict, metric=metric).because("record what the lead named")

    def record_lead(self, verdict: LeadVerdict | None, metric: TurnMetric) -> Done:
        """Record what the turn cost and what it named, so the page repairs and the next check's lead read it."""
        record_turn(self.records_dir, metric)
        if verdict is None:
            return Done(LedLap()).because("the lead named nothing")
        lap = next_check_lap(read_findings(self.records_dir), self.service)
        findings = check_findings(self.service, lap, self.problems, verdict)
        record_findings(self.records_dir, findings)
        return Done(LedLap(findings=findings)).because("the lead named a side for each rule")
