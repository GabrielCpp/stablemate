"""The review as a state machine: read, group, account and write."""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.review_debt.nodes import account, read_register, write_trends
from workhorse_workflows.review_debt.schemas import Accounting, TrendReport


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
            return Done(written).because("trends.md written")
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
