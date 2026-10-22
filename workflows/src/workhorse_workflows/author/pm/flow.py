"""One fresh product-manager review of a stage's output, from every angle of that stage."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.pm.angles import ANGLES, Angle, stage_prompt
from workhorse_workflows.author.pm.nodes import record_pm_receipt
from workhorse_workflows.author.pm.schemas import PMFinding, PMReceipt, PMResult, Verdict
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import Config

FINDING_FIELDS = ("target", "issue", "repair")


def complete(angles: Sequence[Angle]) -> Callable[[Verdict], None]:
    """The check a reply must pass: every angle of the stage once, no other, and each verdict well formed."""
    expected = [angle.name for angle in angles]

    def check(verdict: Verdict) -> None:
        seen = [entry.angle for entry in verdict.angles]
        problems: list[str] = []
        missing = [name for name in expected if name not in seen]
        extra = sorted({name for name in seen if name not in expected})
        repeated = sorted({name for name in seen if seen.count(name) > 1})
        if missing:
            problems.append(f"no verdict for the angles {missing}")
        if extra:
            problems.append(f"{extra} are not angles of this review")
        if repeated:
            problems.append(f"the angles {repeated} appear more than once")
        for entry in verdict.angles:
            if entry.status == "failed" and not entry.findings:
                problems.append(f"angle '{entry.angle}' failed without a finding to repair")
            if entry.status == "passed" and entry.findings:
                problems.append(f"angle '{entry.angle}' passed but lists findings")
            for number, finding in enumerate(entry.findings, start=1):
                empty = [name for name in FINDING_FIELDS if not getattr(finding, name).strip()]
                if empty:
                    problems.append(
                        f"finding {number} of angle '{entry.angle}' has an empty {', '.join(empty)}"
                    )
        if problems:
            raise ValueError(
                "; ".join(problems) + f". Return exactly one verdict for each of {expected}."
            )

    return check


def format_findings(findings: Sequence[PMFinding]) -> str:
    """One line per finding, as a writer reads them and as the next review verifies them."""
    return "\n".join(
        f"[{finding.angle}] {finding.target}: {finding.issue.rstrip('. ')}. "
        f"Repair: {finding.repair}"
        for finding in findings
    )


class PMReview(Workflow):
    """Judge one stage's output as the product manager, in a session no earlier turn touched."""

    stage: str = ""
    subject: str = ""
    epic: str = ""
    detail: str = ""
    prior: str = ""

    def setup(self) -> Config:
        return self.call(load_config, mode="pm")

    def labels(self) -> dict[str, str]:
        return {
            "work_id": self.subject or self.stage,
            "epic": self.epic,
            "progress": f"reviewing the {self.stage}",
        }

    def _review_args(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_prompt": stage_prompt(self.stage),
            "angles": [{"name": angle.name, "prompt": angle.prompt} for angle in ANGLES[self.stage]],
            "subject": self.subject,
            "epic": self.epic,
            "detail": self.detail,
            "prior": self.prior,
            "milestone_dir": self.ctx.milestone_dir,
            "ledger": self.ctx.pm_ledger,
            "services_dir": self.ctx.services_dir,
        }

    def start(self) -> Continue:
        if self.stage not in ANGLES:
            raise WorkflowFailed(
                f"the PM has no angles for stage '{self.stage}'; "
                f"its stages are {sorted(ANGLES)}",
                failure_class="pm-review-unknown-stage",
            )
        return Continue(None, self.review)

    def review(self) -> Done:
        accept = complete(ANGLES[self.stage])
        if self.subagents:
            verdict = self.agent(
                "pm/prompts/review-delegated.md",
                returns=Verdict,
                power="high",
                cwd=self.ctx.repo_root,
                args=self._review_args(),
                accept=accept,
            )
        else:
            verdict = self.agent(
                "pm/prompts/review-inline.md",
                returns=Verdict,
                power="high",
                cwd=self.ctx.repo_root,
                args=self._review_args(),
                accept=accept,
            )
        findings = [
            PMFinding(angle=entry.angle, **finding.model_dump())
            for entry in verdict.angles
            for finding in entry.findings
        ]
        passed = all(entry.status == "passed" for entry in verdict.angles)
        receipt = (
            self.call(record_pm_receipt, self.stage, self.subject) if passed else PMReceipt()
        )
        return Done(
            PMResult(
                stage=self.stage,
                passed=passed,
                findings=findings,
                notes=format_findings(findings),
                receipt_path=receipt.path,
            )
        )


__all__ = ["PMReview", "complete", "format_findings"]
