"""The review as a state machine: read, group, account, write and propose decisions."""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.review_debt.nodes import (
    account, file_decision, narrow_candidate, read_register, select_candidates, write_trends,
)
from workhorse_workflows.review_debt.schemas import (
    Accounting, Candidate, DecisionDraft, Proposed, TrendReport,
)


def gap(accounting: Accounting) -> str:
    """The ids a report got wrong, named by kind."""
    parts = [
        f"{label}: {', '.join(found)}"
        for label, found in (
            ("missing from the report", accounting.missing),
            ("listed more than once", accounting.duplicated),
            ("not on the register", accounting.unknown),
        )
        if found
    ]
    return "; ".join(parts)


class ReviewDebt(Workflow):
    """Group every record of the debt register by shared cause, and write the accounted report."""

    max_sendbacks: int = 2
    decision_threshold: int = 3

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def start(self) -> Continue | Done:
        """Read every record on the register, or end when there is none."""
        read = self.call(read_register)
        if not read.ids:
            self.logger.info("register is empty, nothing to review")
            return Done(read).because("register is empty")
        self.logger.info("reviewing %d records", len(read.ids))
        return Continue(read, self.group)

    def group(self, feedback: str = "", sendbacks: int = 0) -> Continue | Done:
        """Ask for the trend report, send it back with its gap named until it covers the read, then write and commit `trends.md`."""
        read = self.output(read_register)
        report = self.agent(
            "prompts/review-register.md",
            returns=TrendReport,
            args={"listing": "\n".join(read.listing), "shelf": read.shelf, "feedback": feedback},
        )
        accounting = self.call(account, read.ids, report)
        if accounting.ok:
            written = self.call(write_trends, read, report)
            return Continue(written, self.plan_decisions, report=report).because("trends.md written")
        if sendbacks >= self.max_sendbacks:
            raise WorkflowFailed(
                f"the trend report still fails accounting after {sendbacks} send-back(s), "
                f"so trends.md is not written. {gap(accounting)}"
            )
        note = (
            f"The report does not cover the register. {gap(accounting)}. "
            "Every listed id appears exactly once across clusters and singletons."
        )
        return Continue(accounting, self.group, feedback=note, sendbacks=sendbacks + 1).because(
            "report failed accounting"
        )

    def plan_decisions(self, report: TrendReport) -> Continue | Done:
        """Pick the clusters with enough unbound records for a decision, or end when none has."""
        found = self.call(select_candidates, report, self.decision_threshold)
        if not found.clusters:
            return Done(Proposed()).because("no cluster reaches the threshold")
        return Continue(found, self.draft, candidates=found.clusters, proposed=[]).because(
            "clusters are ready for a decision"
        )

    def draft(self, candidates: list[Candidate], proposed: list[str]) -> Continue | Done:
        """Draft and file the decision for the first candidate whose records are still unbound, then take the next."""
        current = self.call(narrow_candidate, candidates[0])
        filed = proposed
        if len(current.ids) >= self.decision_threshold:
            drafted = self.agent(
                "prompts/draft-decision.md",
                returns=DecisionDraft,
                args={
                    "name": current.name,
                    "cause": current.cause,
                    "listing": "\n".join(current.lines),
                    "shelf": self.output(read_register).shelf,
                },
            )
            result = self.call(file_decision, current, drafted)
            if not result.ok:
                raise WorkflowFailed(f"the decision for '{current.name}' was refused: {result.message}")
            filed = [*proposed, result.id]
        if len(candidates) > 1:
            return Continue(None, self.draft, candidates=candidates[1:], proposed=filed).because(
                "next cluster"
            )
        return Done(Proposed(decisions=filed)).because("decisions proposed")
