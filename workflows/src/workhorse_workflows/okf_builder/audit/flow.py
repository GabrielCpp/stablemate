"""Standalone read-only model assessment of explicitly selected source and book."""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from ostler.behavior import AuditPreparation, AuditVerdicts
from pydantic import BaseModel, ConfigDict, Field
from workhorse.pyflow import (
    AgentTimeout, AgentTurnFailed, Await, Continue, Done, NodeNotRunError, Workflow,
    WorkflowFailed,
)

from workhorse_workflows.okf_builder.shared import audit as audit_nodes
from workhorse_workflows.okf_builder.shared.audit import (
    AuditScope, BehaviorAuditOutcome, IncompleteVerdicts, ReviewContractChanged,
    assess_audit, load_repair, prepare_audit, record_audit_budget_stop,
    record_audit_error, record_audit_verdicts, stage_repair,
)

#: Consecutive transient CLI failures (an opencode provider blip that prevents the
#: reviewer from reading the packet at all, e.g. `https://models.dev/api.json` timing
#: out) the audit tolerates before paging the operator. Three packets in a row
#: consistently failing on the same code path is the smallest signal that the network,
#: not the packet, is broken — fewer than that and a single blip pages the operator on
#: every quiet run; more and a sustained outage lets the audit pass through packets
#: the reviewer never read.
TRANSIENT_STREAK_CAP = 3

#: Operator-gate question for a spent transient streak. Names the catalog fetch so the
#: operator can fix the network rather than re-answer and re-run the same packet.
def transient_gate_question(digest: str, error: str, report_path: str) -> str:
    """The gate message for a transient CLI streak that has spent its budget."""
    return (
        f"okf-builder could not reach the agent backend on {TRANSIENT_STREAK_CAP} "
        f"consecutive packets — last error on packet {digest}: {error}. "
        f"The opencode catalog fetch at https://models.dev/api.json is the most likely "
        f"cause; verify with `curl -sS --max-time 5 https://models.dev/api.json | head` "
        f"and `opencode run -m <model> warmup --print-logs --log-level ERROR`. The "
        f"report at {report_path} lists what was reviewed before the streak began; "
        f"set STATUS: ANSWERED to retry the same packets once the cause is cleared."
    )

#: The catalog URL opencode's CLI refreshes when a turn starts. The audit's pre-warm
#: fetches it directly to fail fast on a network outage instead of burning packets on
#: a blip that the ladder cannot distinguish from a verdict-validation failure. The
#: fetch is read-only and returns ~5 MB of JSON; this constant exists so the test can
#: patch the URL and the gate message can name it.
MODELS_DEV_CATALOG_URL = "https://models.dev/api.json"
#: Wall-clock bound for the pre-warm fetch. A 5s ceiling is below the audit's per-turn
#: timeout (300s) but well above a healthy round-trip; a fetch that takes longer than
#: this is the same outage the gate is supposed to catch.
MODELS_DEV_WARMUP_TIMEOUT_S = 5.0


def fetch_models_dev_catalog(timeout_s: float = MODELS_DEV_WARMUP_TIMEOUT_S) -> None:
    """Opencode's CLI refreshes its model catalog from `MODELS_DEV_CATALOG_URL` on every
    turn. A fetch that times out returns no result text from opencode, which the audit's
    transient-streak branch already routes to a gate — but only after a few packets of
    damage. Doing it once at setup catches a hard outage up front.

    The fetch is read-only and small; the timeout is intentionally below the audit's
    300s per-turn ceiling so a slow network reads as a fast failure here rather than
    spending a full turn on every packet before the streak gates.

    The User-Agent is set because models.dev returns 403 to the urllib default — opencode
    itself sends a real UA, which is why its CLI succeeds against the same URL.

    Raises whatever `urllib.request.urlopen` raises (`URLError` on DNS / connect /
    timeout) so the caller can record the message verbatim on the gate file.
    """
    request = urllib.request.Request(  # noqa: S310 - catalog is a public, read-only URL
        MODELS_DEV_CATALOG_URL,
        headers={"User-Agent": "okf-builder/audit-prewarm (+workhorse-workflows)"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        # Drain a small prefix so a hung connection that returns headers but stalls
        # on the body still trips the timeout.
        response.read(64)


class AuditSetup(BaseModel):
    """The audit flow's read-once setting: scope, prepared evidence, and the path it lives on.

    `outcome` is set when `setup` could not produce a usable preparation (missing
    context files, an unloadable graph). The first state reads it before calling
    `assess_audit` so a failure surfaces as the operator gate the old in-place
    exception catch produced — same message, same report file, same wait.
    """
    model_config = ConfigDict(extra="forbid")

    scope: AuditScope
    preparation: AuditPreparation | None = None
    run_dir: str
    prompt_path: Path
    outcome: BehaviorAuditOutcome | None = None


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

    def setup(self) -> AuditSetup:
        """Compute and persist the audit preparation once, up front.

        `setup` runs before the first state, before any agent turn, and is not
        re-run on resume. The work — `load(root)`, `extract_book`, `extract_evidence`,
        `build_audit_packets` — is the read-once input the iteration body used to
        repeat per packet. Doing it here means every `start` iteration reuses the
        cached `AuditPreparation` rather than re-doing the per-book, per-source
        file reads.

        Preparation failures (missing context, unreadable graph) are caught here
        and recorded as an invalid `BehaviorAuditOutcome` on disk, so the first
        state sees `setup.outcome.status == "invalid"` and gates identically to
        how `assess_audit`'s old in-place exception catch surfaced a failure.
        `setup` may not raise: the engine treats an unhandled raise as the run
        dying, which is not the contract — invalid evidence is a gate, not a death.
        """
        scope = AuditScope(
            docs_path=self.docs_path, source_path=self.source_path, service=self.service,
            context_paths=self.context_paths,
            max_packets=self.max_packets, packet_max_items=self.packet_max_items,
            packet_max_chars=self.packet_max_chars,
        )
        directory = Path(self.artifact_dir) if self.artifact_dir else self.run_dir
        prompt_path = audit_nodes.AUDIT_PROMPT
        report_path = directory / "behavior-audit.json"
        try:
            preparation = self.call(prepare_audit, scope, str(directory), prompt_path)
            return AuditSetup(
                scope=scope, preparation=preparation,
                run_dir=str(directory), prompt_path=prompt_path,
            )
        except (ValueError, OSError) as exc:
            outcome = BehaviorAuditOutcome(
                schema_version=2, status="invalid",
                report_path=str(report_path), scope_digest="", scope=scope,
                error=str(exc), unresolved=("Evidence preparation failed",),
            )
            report_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
            return AuditSetup(
                scope=scope, preparation=None,
                run_dir=str(directory), prompt_path=prompt_path,
                outcome=outcome,
            )

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
        repair_digest: str = "", transient_streak: int = 0,
    ) -> Continue | Done | Await:
        # `setup()` is supposed to run exactly once and `_ctx` is sealed from its return
        # value on every drive (fresh or resumed). A resume reads `setup()`'s return
        # annotation, validates the stored ctx against it, and seals the result — so a
        # `None` here means the prior checkpoint's `ctx` field was itself `None`. That
        # has been observed on long-lived okf-builder runs after many reloads; the
        # engine has no recovery path for it, so the audit sub-flow would otherwise
        # crash on `setup.outcome` below. `setup()` is deterministic for the same
        # inputs (the audit flow's `preparation` is content-keyed, so it is stable
        # across reloads), so re-running it is the honest recovery — once.
        setup = self.ctx
        if setup is None:
            self._ctx = self.setup()
            setup = self._ctx
        if setup.outcome is not None and setup.outcome.status == "invalid":
            return Await(
                self.run_dir / "behavior-audit-context.md", setup.outcome.error, self.start,
            ).because("evidence unreadable: operator input required")
        # Resume replays the last state with `self.ctx` restored from the checkpoint, so
        # the cached `preparation` is whatever `setup()` produced on the prior fresh
        # drive. The audit's reading of source and claims can have moved between the
        # checkpoint and the resume — an operator parks on the gate, edits a file,
        # answers — and the contract is that a resume picks the change up. The
        # `resume_pending` flag the engine sets on the resumed state's first entry
        # is the only moment "this state is being re-entered" is observable, and it
        # is reset to False *after* the body returns; reading it from inside the
        # body sees True once. On a resume, run `prepare_audit` fresh here and stash
        # the result on a private instance attribute so subsequent iterations of
        # `start` (with the engine flag already False again) keep using it rather
        # than the pre-resume preparation whose packets no longer match the
        # receipts written on the resumed iteration.
        if getattr(self._engine.env, "resume_pending", False):
            self._live_prep = self.call(
                prepare_audit, setup.scope, setup.run_dir, setup.prompt_path,
            )
        prepared = getattr(self, "_live_prep", None) or setup.preparation
        work = self.call(assess_audit, setup.scope, setup.run_dir, setup.prompt_path,
                         prepared=prepared)
        # Pre-warm the opencode catalog before the first turn, once per fresh drive.
        # The transient-streak branch catches a catalog-fetch blip mid-run, but only
        # after a few packets of damage; doing it here lets a hard outage gate before
        # the first reviewer call, with the same gate-shaped outcome the invalid-
        # evidence path already uses. The fetch is best-effort: a healthy network
        # doesn't notice, and the same URL is the most likely culprit on failure so
        # the gate message names it directly. Skipped on every resume — `resume_pending`
        # is only true on the resumed state's first entry, so this branch fires once
        # per drive rather than once per packet.
        if not getattr(self, "_warmup_done", False):
            self._warmup_done = True
            try:
                fetch_models_dev_catalog()
            except (OSError, ValueError) as exc:
                report_path = Path(setup.run_dir) / "behavior-audit.json"
                outcome = BehaviorAuditOutcome(
                    schema_version=2, status="invalid",
                    report_path=str(report_path),
                    scope_digest=work.outcome.scope_digest, scope=setup.scope,
                    error=f"opencode catalog unreachable at audit start: {exc}",
                    unresolved=(
                        "Agent backend unreachable; resume once "
                        "https://models.dev/api.json responds.",
                    ),
                )
                report_path.write_text(
                    outcome.model_dump_json(indent=2), encoding="utf-8",
                )
                return Await(
                    report_path.parent / "behavior-audit-context.md",
                    outcome.error, self.start,
                ).because("agent backend unreachable at audit start: operator gate")
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
        repair = self.call(load_repair, repair_digest, packet.digest, setup.run_dir)
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
                    cwd=Path(setup.run_dir) / "behavior-audit" / dispatched.digest,
                    args={"packet": dispatched.model_dump_json(indent=2), "feedback": feedback,
                          "result_schema": work.result_schema},
                )
            self.call(record_audit_verdicts, dispatched, verdicts, setup.run_dir, contract,
                      setup.prompt_path, setup.scope)
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
                       else self.call(stage_repair, dispatched, exc.recall, setup.run_dir))
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
        #
        # A transient CLI failure (the engine carries `BackendInvocationError.transient`
        # through as `AgentTurnFailed.transient`) is NOT a verdict-validation failure:
        # the reviewer never got to read the packet — opencode could not refresh its
        # `https://models.dev/api.json` catalog, every retry hit the same network blip,
        # and counting this against the verdict's `attempts` budget spends the packet
        # on a problem the retry cannot move. It rides its own counter, `transient_streak`,
        # reset on the next successful receipt; only `TRANSIENT_STREAK_CAP` consecutive
        # failures across packets gate, with a message that names the catalog fetch as
        # the likely cause so the operator can fix the network, not the run.
        except AgentTurnFailed as exc:
            self.call(record_audit_error, work.outcome, packet.digest, str(exc))
            if getattr(exc, "transient", False) and not getattr(exc, "overflow", False):
                streak = transient_streak + 1
                if streak >= TRANSIENT_STREAK_CAP:
                    return Await(
                        self.run_dir / "behavior-audit-context.md",
                        transient_gate_question(packet.digest, str(exc), work.outcome.report_path),
                        self.start,
                    ).because("transient CLI streak exhausted: operator gate")
                return Continue(
                    None, self.start, failed_digest=packet.digest, attempts=attempts,
                    transient_streak=streak, feedback=str(exc), turns=turns,
                ).because("transient CLI blip: same packet, separate budget")
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
        return Continue(None, self.start, turns=turns, transient_streak=0).because("receipt saved: rebuild scope before next packet")
