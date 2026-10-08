"""What the lead named for each group of a lap's failed checks, kept across laps, and the lap as the lead attributed it."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Literal

from ostler.qa.attribution import Cause, Signature
from pydantic import BaseModel, ConfigDict, field_validator
from workhorse.pyflow import dry_run

from workhorse_workflows.okf_book.main.nodes.gate import SIDE_BY_ESCALATED_CAUSE, escalation_reason
from workhorse_workflows.okf_book.shared.blockers import Side
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary

FINDINGS_NAME = "lead-findings.json"
LINES_SHOWN = 200
WRITER_CAUSES = frozenset({Cause.BOOK, Cause.ARRANGEMENT})
CAUSE_BY_OTHER_SIDE = {
    Side.APP: Cause.APP,
    Side.ENVIRONMENT: Cause.ENVIRONMENT,
    Side.OSTLER: Cause.UNATTRIBUTED,
    Side.UNATTRIBUTED: Cause.UNATTRIBUTED,
}
LEAD_SIDES = frozenset({Side.BOOK, *CAUSE_BY_OTHER_SIDE})

type Escalation = tuple[Signature, Side, str]
type Measured = Literal["run", "check"]


class GroupVerdict(BaseModel):
    """What the lead says of one numbered group: the side that must change, what it read that shows it, and what a page repair must do when the side is the book. A verdict that names nodes judges only those of the group, and one that names none judges the rest."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    group: int
    side: Side
    evidence: str
    instruction: str = ""
    nodes: tuple[str, ...] = ()

    @field_validator("side")
    @classmethod
    def _a_side_the_lead_names(cls, side: Side) -> Side:
        if side not in LEAD_SIDES:
            raise ValueError(f"side is one of {', '.join(sorted(LEAD_SIDES))}")
        return side


@dry_run(findings=())
class LeadVerdict(BaseModel):
    """The lead's reply: one verdict per group it judged."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    findings: tuple[GroupVerdict, ...] = ()


@dry_run(run=(), check=())
class OwnerReply(BaseModel):
    """The book owner's reply: the side of each numbered group of the run and of the check it was shown at the start of its turn."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    run: tuple[GroupVerdict, ...] = ()
    check: tuple[GroupVerdict, ...] = ()


class LeadFinding(BaseModel):
    """One group of one lap as the lead named it, with the signature the run gave it, its count and its pages.

    A group of a page check is measured by the check: its signature is the code of the rule that
    raised its problems, and the nodes it names are the only ones of the group it judges.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    lap: int
    signature: str
    count: int
    side: Side
    evidence: str
    instruction: str = ""
    pages: tuple[str, ...] = ()
    measured: Measured = "run"
    nodes: tuple[str, ...] = ()


class _Ledger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: tuple[LeadFinding, ...] = ()


def lead_groups(exercised: ExerciseResult) -> tuple[Signature, ...]:
    """The groups the lead judges: every signature of the run but a gapped one, which only a person can supply."""
    signatures = exercised.summary.signatures if exercised.summary is not None else ()
    return tuple(signature for signature in signatures if not signature.gap)


def lead_findings(service: str, lap: int, exercised: ExerciseResult, verdict: LeadVerdict) -> tuple[LeadFinding, ...]:
    """Each verdict that names a group of the run, as a finding. A verdict on a number the run has no group for is dropped, and a group judged twice keeps its last verdict."""
    groups = lead_groups(exercised)
    summary = exercised.summary
    by_group = {judged.group: judged for judged in verdict.findings if 1 <= judged.group <= len(groups)}
    return tuple(
        LeadFinding(service=service, lap=lap, signature=groups[number - 1].text(), count=groups[number - 1].count, side=judged.side,
                    evidence=judged.evidence, instruction=judged.instruction if judged.side is Side.BOOK else "",
                    pages=summary.signature_pages(groups[number - 1]) if summary is not None else ())
        for number, judged in sorted(by_group.items())
    )


def read_findings(records_dir: Path) -> tuple[LeadFinding, ...]:
    """Every finding the run's leads recorded, in the order they were named."""
    path = records_dir / FINDINGS_NAME
    return _Ledger.model_validate_json(path.read_text(encoding="utf-8")).findings if path.is_file() else ()


def record_findings(records_dir: Path, findings: Iterable[LeadFinding]) -> None:
    """Add *findings* to the ledger."""
    kept = (*read_findings(records_dir), *findings)
    _ = (records_dir / FINDINGS_NAME).write_text(_Ledger(findings=kept).model_dump_json(indent=2), encoding="utf-8")


def service_findings(findings: Iterable[LeadFinding], service: str, measured: Measured = "run") -> tuple[LeadFinding, ...]:
    return tuple(finding for finding in findings if finding.service == service and finding.measured == measured)


def _key(cause: Cause, precondition: str, status: str, shape: str, gap: str) -> tuple[Cause, str, str, str, str]:
    return (cause, precondition, status, shape, gap)


def _named_cause(signature: Signature, side: Side) -> Cause:
    if side is Side.BOOK:
        return signature.cause if signature.cause in WRITER_CAUSES else Cause.BOOK
    return CAUSE_BY_OTHER_SIDE[side]


def _with_cause(check: FailedCheck, causes: Mapping[tuple[Cause, str, str, str, str], Cause]) -> FailedCheck:
    named = causes.get(_key(check.cause, check.precondition, check.status, check.shape, check.gap))
    return check if named is None or named is check.cause else check.model_copy(update={"cause": named})


def _attributed_summary(summary: RunSummary, sides: Mapping[str, Side]) -> RunSummary:
    causes = {
        _key(signature.cause, signature.precondition, signature.status, signature.shape, signature.gap): _named_cause(signature, sides[signature.text()])
        for signature in summary.signatures
        if not signature.gap and signature.text() in sides
    }
    scenarios = {
        name: outcome.model_copy(update={"failed_checks": tuple(_with_cause(check, causes) for check in outcome.failed_checks)})
        for name, outcome in summary.scenarios.items()
    }
    signatures = tuple(
        replace(signature, cause=causes.get(_key(signature.cause, signature.precondition, signature.status, signature.shape, signature.gap),
                                           signature.cause))
        for signature in summary.signatures
    )
    return summary.model_copy(update={"scenarios": scenarios, "signatures": signatures})


def attributed(exercised: ExerciseResult, findings: Iterable[LeadFinding]) -> ExerciseResult:
    """The run with each group the lead named moved to the cause of its side, its signatures in their order. A group the lead left out keeps the cause the run gave it."""
    sides = {finding.signature: finding.side for finding in findings}
    if exercised.summary is None or not sides:
        return exercised
    return exercised.model_copy(update={"summary": _attributed_summary(exercised.summary, sides)})


def run_escalations(exercised: ExerciseResult) -> tuple[Escalation, ...]:
    """Each signature of the run another party must fix, with the side its cause sits on and why it is escalated."""
    signatures = exercised.summary.signatures if exercised.summary is not None else ()
    return tuple(
        (signature, SIDE_BY_ESCALATED_CAUSE[signature.cause], escalation_reason(signature))
        for signature in signatures
        if signature.cause in SIDE_BY_ESCALATED_CAUSE
    )


def led_escalations(exercised: ExerciseResult, led: ExerciseResult, findings: Iterable[LeadFinding]) -> tuple[Escalation, ...]:
    """Each signature of *led*, the run as the lead attributed it, that another party must fix. One the lead named is on the side it named, with what it read and on which lap, since a later lap's group of the same signature may fail for another reason."""
    if exercised.summary is None or led.summary is None:
        return ()
    named = {finding.signature: finding for finding in findings}
    escalations: list[Escalation] = []
    for ran, signature in zip(exercised.summary.signatures, led.summary.signatures, strict=True):
        if signature.cause not in SIDE_BY_ESCALATED_CAUSE:
            continue
        finding = named.get(ran.text())
        if finding is None or finding.side is Side.BOOK:
            escalations.append((signature, SIDE_BY_ESCALATED_CAUSE[signature.cause], escalation_reason(signature)))
        else:
            escalations.append((signature, finding.side, f"{escalation_reason(signature)}\nthe lead read the whole of lap {finding.lap}, "
                                + f"when {finding.count} checks failed this way: {finding.evidence}"))
    return tuple(escalations)


def with_instructions(failures: Mapping[str, tuple[PageProblem, ...]], findings: Iterable[LeadFinding]) -> dict[str, tuple[PageProblem, ...]]:
    """*failures* with what the lead said to do first on each failing page of a group it named the book's."""
    told: dict[str, list[PageProblem]] = {}
    for finding in findings:
        if finding.side is not Side.BOOK or not finding.instruction:
            continue
        for page in finding.pages:
            if page in failures:
                told.setdefault(page, []).append(PageProblem(page, f"the lead read the whole lap, and says of {finding.signature}: {finding.instruction}"))
    return {page: (*told.get(page, ()), *problems) for page, problems in failures.items()}
