"""The lead of one failed lap: one wide turn reads the whole run before any page is repaired, and names the side each group of failed checks sits on.

A page repair can only edit its pages, so a cause that sits in the toolchain, the app or the
environment is never fixed by one. The lead sees every group of the lap, the test plan the
toolchain sent and what earlier laps' leads named, and its verdict decides which groups reach a
page repair. It runs on the strongest model the run has and changes no file: code puts back what
its turn wrote.
"""
from __future__ import annotations

import time
from pathlib import Path

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Continue, Done, WorkflowFailed
from workhorse.runner.backends import AgentProfile
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.okf_book.main.nodes.lead_findings import (
    LeadVerdict,
    LedLap,
    lead_findings,
    lead_template_args,
    read_findings,
    record_findings,
    service_findings,
)
from workhorse_workflows.okf_book.main.nodes.source_view import kept_for_turn
from workhorse_workflows.okf_book.main.nodes.progress_ledger import read_laps, service_laps
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.confine import changed_since, restore, snapshot
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn, turn_metric
from workhorse_workflows.okf_book.shared.scenarios import PLAN_NAME, RUN_NAME, spec_dir

LEAD_PROMPT = "main/prompts/lead-lap.md"
LEAD_FOLDER = "lead"
LEAD_PROFILE = AgentProfile(name="okf-book-lead", confined=True)
LEAD_TIMEOUT = 3600.0


class LeadLap(BookFlow):
    """Sends one lead turn over a failed run, and ends on what it named for the caller to route."""

    service: str = ""
    exercised: ExerciseResult | None = None

    @property
    def run(self) -> ExerciseResult:
        if self.exercised is None:
            raise WorkflowFailed("the lead flow is handed no run")
        return self.exercised

    def start(self) -> Continue[...]:
        """Send the lead turn. A turn that ends without a verdict names nothing, and the run's own attribution stands."""
        earlier = service_findings(read_findings(self.records_dir), self.service)
        summary, plan = kept_for_turn(self.root, LEAD_FOLDER, (self.records_dir / RUN_NAME, spec_dir(self.records_dir) / self.service / PLAN_NAME))
        before = snapshot(self.root)
        started = time.monotonic()
        verdict: LeadVerdict | None = None
        try:
            verdict = self.agent(
                LEAD_PROMPT,
                returns=LeadVerdict,
                power="high",
                timeout=LEAD_TIMEOUT,
                args=lead_template_args(self.service, self.run, earlier, summary, plan),
                cwd=self.root,
                profile=LEAD_PROFILE,
            )
        except (AgentTurnFailed, AgentTimeout, OutputParseError) as ended:
            self.logger.warning("the lead turn on %s ended without a verdict: %s", self.service, ended)
        _ = restore(self.root, changed_since(self.root, before), before)
        node = Path(LEAD_PROMPT).stem
        metric = turn_metric(Phase.EXERCISE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node))
        return Continue(verdict, self.record_lead, verdict=verdict, metric=metric).because("record what the lead named")

    def record_lead(self, verdict: LeadVerdict | None, metric: TurnMetric) -> Done:
        """Record what the turn cost and what it named, so the next lap's lead reads it."""
        record_turn(self.records_dir, metric)
        if verdict is None:
            return Done(LedLap()).because("the lead named nothing")
        lap = len(service_laps(read_laps(self.records_dir), self.service))
        findings = lead_findings(self.service, lap, self.run, verdict)
        record_findings(self.records_dir, findings)
        return Done(LedLap(findings=findings)).because("the lead named a side for each group")
