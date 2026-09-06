"""Standalone read-only model assessment of explicitly selected source and book."""
from __future__ import annotations

from pathlib import Path

from ostler.behavior import AuditVerdicts
from pydantic import Field
from workhorse.pyflow import AgentTimeout, Await, Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.okf_builder.shared import audit as audit_nodes
from workhorse_workflows.okf_builder.shared.audit import (
    AuditScope, ReviewContractChanged, assess_audit, record_audit_budget_stop, record_audit_error,
    record_audit_verdicts,
)


class Audit(Workflow):
    """Assess bounded Python evidence; return a report, never mutate the book."""

    docs_path: str = ""
    source_path: str = ""
    context_paths: tuple[str, ...] = ()
    service: str = ""
    max_packets: int | None = Field(default=None, gt=0)
    packet_max_items: int = Field(default=80, ge=2)
    packet_max_chars: int = Field(default=60000, gt=0)
    #: Reviewer turns this pass may spend; 0 is unbudgeted. A retry on an invalid reply is
    #: a turn. At the budget the pass ends with the unaudited packets listed in its report,
    #: which is a partial audit the caller may ship — never a silent skip.
    turn_budget: int = Field(default=0, ge=0)
    #: Parent-run storage survives the engine resetting a completed handoff scope.
    artifact_dir: str = ""

    def start(
        self, failed_digest: str = "", attempts: int = 0, feedback: str = "", turns: int = 0,
    ) -> Continue | Done | Await:
        scope = AuditScope(
            docs_path=self.docs_path, source_path=self.source_path, service=self.service,
            context_paths=self.context_paths,
            max_packets=self.max_packets, packet_max_items=self.packet_max_items,
            packet_max_chars=self.packet_max_chars,
        )
        directory = Path(self.artifact_dir) if self.artifact_dir else self.run_dir
        prompt_path = audit_nodes.AUDIT_PROMPT
        work = self.call(assess_audit, scope, str(directory), prompt_path)
        if work.outcome.status == "invalid":
            return Await(
                self.run_dir / "behavior-audit-context.md", work.outcome.error, self.start,
            ).because("evidence unreadable: operator input required")
        if not work.pending:
            return Done(work.outcome).because("selected packets assessed; limits in report")
        packet = work.pending[0]
        contract = work.outcome.review_contract
        assert contract is not None
        if packet.digest != failed_digest:
            attempts, feedback = 0, ""
        try:
            if not packet.candidates and not packet.claims:
                verdicts = AuditVerdicts(claims=(), candidates=())
            elif self.turn_budget and turns >= self.turn_budget:
                stopped = self.call(record_audit_budget_stop, work.outcome, turns, self.turn_budget)
                return Done(stopped).because("turn budget spent: unaudited packets listed in report")
            else:
                turns += 1
                verdicts = self.agent(
                    "audit/prompts/behavior-audit.md", returns=AuditVerdicts,
                    # No reframe and three provider retries: a 5xx storm ends here as a
                    # recorded failure and an operator gate, not a day of backoff.
                    power="medium", retries=0, invoke_retries=3, timeout=300,
                    cwd=directory / "behavior-audit" / packet.digest,
                    args={"packet": packet.model_dump_json(indent=2), "feedback": feedback,
                          "result_schema": work.result_schema},
                )
            self.call(record_audit_verdicts, packet, verdicts, str(directory), contract, prompt_path, scope)
        except ReviewContractChanged as exc:
            self.call(record_audit_error, work.outcome, packet.digest, str(exc))
            return Await(
                self.run_dir / "behavior-audit-context.md", str(exc), self.start,
            ).because("review contract changed: operator gate")
        except (ValueError, WorkflowFailed, AgentTimeout) as exc:
            self.call(record_audit_error, work.outcome, packet.digest, str(exc))
            if attempts >= 1:
                return Await(
                    self.run_dir / "behavior-audit-context.md",
                    f"Reviewer failed twice on packet {packet.digest}: {exc}. "
                    f"Report: {work.outcome.report_path}. No completion is authorized.", self.start,
                ).because("invalid verdict budget exhausted: operator gate")
            return Continue(
                None, self.start, failed_digest=packet.digest, attempts=attempts + 1, feedback=str(exc),
                turns=turns,
            ).because("invalid receipt: retry with validator findings")
        return Continue(None, self.start, turns=turns).because("receipt saved: rebuild scope before next packet")
