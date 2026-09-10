"""Standalone read-only model assessment of explicitly selected source and book."""
from __future__ import annotations

from pathlib import Path

from ostler.behavior import AuditVerdicts
from pydantic import Field
from workhorse.pyflow import (
    AgentTimeout, AgentTurnFailed, Await, Continue, Done, NodeNotRunError, Workflow,
    WorkflowFailed,
)

from workhorse_workflows.okf_builder.shared import audit as audit_nodes
from workhorse_workflows.okf_builder.shared.audit import (
    AuditScope, IncompleteVerdicts, ReviewContractChanged, assess_audit, load_repair,
    record_audit_budget_stop, record_audit_error, record_audit_verdicts, stage_repair,
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

    def labels(self) -> dict[str, str]:
        """Which packet the audit is reviewing — the dimension churn keys on.

        The audit's `start` self-loops via `Continue(None, self.start, ...)`, so the
        same node spans (`assess_audit`, `behavior-audit`) close once per packet. The
        rule at `groom/groom/alerts.py::ingest_spans` keys CHURN on `(node, signature)`
        where `signature` is the workflow-declared label set; with no `labels()` here,
        every iteration's signature is `()` and CHURN fires at packet five. The
        per-packet digest is the only forward-progress signal the loop emits, and
        `assess_audit`'s recorded output carries it on `pending[0]`.

        Before the first `assess_audit` runs there is nothing to read; the empty
        signature then is the same one every fresh workflow produces, which CHURN
        guards against by node (not by run), so a one-shot empty at start is safe.
        """
        try:
            work = self.output(assess_audit)
        except NodeNotRunError:
            return {}
        if not work.pending:
            return {}
        return {"packet_digest": work.pending[0].digest}

    def start(
        self, failed_digest: str = "", attempts: int = 0, feedback: str = "", turns: int = 0,
        repair_digest: str = "",
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
            attempts, feedback, repair_digest = 0, "", ""
        # A repair carries the reduced packet the last reply left owing. It is dispatched
        # in place of the full one only while it is still owed against it; `load_repair`
        # makes that check, because the book may have moved underneath a staged repair.
        repair = self.call(load_repair, repair_digest, packet.digest, str(directory))
        dispatched = repair if repair is not None else packet
        try:
            if not dispatched.candidates and not dispatched.claims:
                verdicts = AuditVerdicts(claims=(), candidates=())
            elif self.turn_budget and turns >= self.turn_budget:
                stopped = self.call(record_audit_budget_stop, work.outcome, turns, self.turn_budget)
                return Done(stopped).because("turn budget spent: unaudited packets listed in report")
            else:
                turns += 1
                verdicts = self.agent(
                    "audit/prompts/behavior-audit.md", returns=AuditVerdicts,
                    # Three provider retries and one reframe: a 5xx storm ends here as a
                    # recorded failure and an operator gate, not a day of backoff. The
                    # reframe earns its rung against a packet this reviewer cannot answer
                    # inside its output budget — the empties measured here were the model
                    # spending all 32k generation tokens reasoning about a 35-40k prompt
                    # and having none left to answer with, which is a property of the
                    # prompt, not of the session, so a fresh session alone does not clear
                    # it. Compaction is the ladder's own answer to that (see
                    # runner/failure.py); the reframe is what remains when it is not.
                    power="medium", retries=1, invoke_retries=3, timeout=300,
                    cwd=directory / "behavior-audit" / dispatched.digest,
                    args={"packet": dispatched.model_dump_json(indent=2), "feedback": feedback,
                          "result_schema": work.result_schema},
                )
            self.call(record_audit_verdicts, dispatched, verdicts, str(directory), contract, prompt_path, scope)
        except ReviewContractChanged as exc:
            self.call(record_audit_error, work.outcome, packet.digest, str(exc))
            return Await(
                self.run_dir / "behavior-audit-context.md", str(exc), self.start,
            ).because("review contract changed: operator gate")
        # A reply that answered for part of the packet is not a worthless reply. Re-asking
        # the whole packet is what dropped the same id twice on the run this rung exists
        # for, so the owing items are reduced into their own packet and asked once, on
        # their own. One repair per packet: a repair that also comes back short falls
        # through to the retry below, and then to the gate, which is the budget the
        # reviewer already had.
        except IncompleteVerdicts as exc:
            reduced = (None if repair_digest
                       else self.call(stage_repair, dispatched, exc.recall, str(directory)))
            if reduced is None:
                self.call(record_audit_error, work.outcome, packet.digest, str(exc))
                if attempts >= 1:
                    return Await(
                        self.run_dir / "behavior-audit-context.md",
                        f"Reviewer failed twice on packet {packet.digest}: {exc}. "
                        f"Report: {work.outcome.report_path}. No completion is authorized.", self.start,
                    ).because("invalid verdict budget exhausted: operator gate")
                return Continue(
                    None, self.start, failed_digest=packet.digest, attempts=attempts + 1,
                    feedback=str(exc), turns=turns,
                ).because("incomplete receipt, nothing salvageable: retry the whole packet")
            return Continue(
                None, self.start, failed_digest=packet.digest, attempts=attempts,
                repair_digest=reduced.digest, turns=turns,
                # The reduced packet still shows every candidate an owed claim might link
                # to (see ``reduce_packet``), so the feedback must not call it "only
                # those items": told that, a reviewer answers the owed ids alone, and a
                # validator holding it to the reduced packet gates it. The record node
                # holds the reply to the parent instead, so what is said here is true.
                feedback=f"A previous reply left these items unanswered: {', '.join(exc.owing)}. "
                         f"Answer for every one of them. Any other item shown in this packet "
                         f"was already judged and is here only as context for links; you may "
                         f"leave it unanswered or judge it again.",
            ).because("incomplete receipt: ask again for the items still owed")
        # `AgentTurnFailed` is the ladder's verdict on a turn that produced nothing.
        # It belongs with the others: the packet is recorded, one packet is retried,
        # and a second failure gates. Without it the run simply died here, on a
        # provider outage, past the gate this branch exists to open.
        except (ValueError, WorkflowFailed, AgentTimeout, AgentTurnFailed) as exc:
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
