"""Run-owned semantic review receipts, rebuilt against current source and claims."""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Literal

from ostler.behavior import (
    AuditPacket, AuditPreparation, AuditReport, AuditVerdicts,
    build_audit_packets, extract_book, extract_evidence, validate_verdicts,
)
from ostler.model import load
from pydantic import BaseModel, ConfigDict, Field

from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint


AUDIT_PROMPT = Path(__file__).resolve().parents[1] / "audit/prompts/behavior-audit.md"


class ReviewContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    prompt_digest: str
    schema_digest: str

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReceiptPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: ReviewContract
    verdicts_digest: str


class ReviewContractChanged(ValueError):
    """The reply cannot be attributed to a stable dispatch contract."""


def review_contract(prompt_path: Path, result_schema: str) -> ReviewContract:
    return ReviewContract(
        prompt_digest=hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        schema_digest=hashlib.sha256(result_schema.encode("utf-8")).hexdigest(),
    )


def verdict_schema() -> str:
    return json.dumps(AuditVerdicts.model_json_schema(), sort_keys=True, separators=(",", ":"))


class AuditScope(BaseModel):
    docs_path: str
    source_path: str
    context_paths: tuple[str, ...] = ()
    service: str = ""
    max_packets: int | None = Field(default=None, gt=0)
    packet_max_items: int = Field(default=80, ge=2)
    packet_max_chars: int = Field(default=60000, gt=0)


class AuditRepair(BaseModel):
    target: str
    context: str


class BehaviorAuditOutcome(BaseModel):
    # Unversioned historical reports have no observed review contract.
    schema_version: Literal[1, 2] = 1
    review_contract: ReviewContract | None = None
    policy_digest: str = ""
    status: Literal["assessed", "partial", "invalid"]
    report_path: str
    scope_digest: str
    scope: AuditScope
    scope_clear: bool = False
    total_packets: int = 0
    assessed_packets: int = 0
    empty_packets: int = Field(default=0, description="Empty packets validated without a model call")
    omitted_packets: int = 0
    selected_candidates: int = 0
    selected_claims: int = 0
    reports: tuple[AuditReport, ...] = ()
    repairs: tuple[AuditRepair, ...] = ()
    unresolved: tuple[str, ...] = ()
    undocumented_files: tuple[str, ...] = Field(
        default=(), description="Source files with exported symbols that no claim cites; queued as repairs")
    unaudited_packets: tuple[str, ...] = Field(
        default=(), description="Packets with no current receipt, as `<digest> <paths>`; a budget stop ships them")
    limitations: tuple[str, ...] = ()
    error: str = ""

    @property
    def clear_except_unaudited(self) -> bool:
        """Nothing blocks a commit but packets no reviewer has read yet.

        This is the shape a turn budget leaves behind: no repair, no unresolved verdict,
        no omitted packet, only receipts still owed. The pass cap in the main flow decides
        whether that ships; the outcome only says that it *could*.
        """
        return (self.status == "partial" and bool(self.unaudited_packets)
                and not self.repairs and not self.unresolved and not self.omitted_packets)


def packet_label(packet: AuditPacket) -> str:
    """A digest a receipt dir is named by, plus the paths a reader can find it under."""
    paths_seen = sorted({candidate.path for candidate in packet.candidates} | {claim.path for claim in packet.claims})
    return f"{packet.digest} {' '.join(paths_seen)}".rstrip()


class AuditWork(BaseModel):
    outcome: BehaviorAuditOutcome
    pending: tuple[AuditPacket, ...] = ()
    result_schema: str = ""


def preparation(scope: AuditScope) -> AuditPreparation:
    """Read a scoped book without formatting, indexing, or importing source."""
    root = paths.docs_root(scope.docs_path)
    source = Path(scope.source_path)
    if source.is_absolute():
        source = source.resolve().relative_to(root.resolve())
    if not scope.source_path:
        raise ValueError("source_path is required: choose an explicit source file or directory")
    graph = load(root)
    prefix = paths.book_scope(root, scope.service)
    book = extract_book(graph)
    claims = book.model_copy(update={"claims": tuple(claim for claim in book.claims if claim.path.startswith(prefix))})
    evidence = extract_evidence(root, [source.as_posix()], context_paths=scope.context_paths)
    failures = [f"{file.path}: {file.status}: {file.message}"
                for file in evidence.context_files if file.status != "parsed"]
    if failures:
        raise ValueError("Support context unavailable: " + "; ".join(failures))
    return build_audit_packets(
        evidence, claims,
        max_items=scope.packet_max_items, max_chars=scope.packet_max_chars,
    )


@blueprint.node(stub=lambda logger, scope, run_dir, prompt_path=AUDIT_PROMPT: AuditWork(outcome=BehaviorAuditOutcome(
    schema_version=2,
    status="assessed", report_path=str(Path(run_dir) / "behavior-audit.json"),
    scope_digest="dry-run", scope=scope, scope_clear=True,
    limitations=("Dry-run stand-in: no source or claims were reviewed.",),
)))
def assess_audit(
    logger: logging.Logger, scope: AuditScope, run_dir: str, prompt_path: Path = AUDIT_PROMPT,
) -> AuditWork:
    """Rebuild packets and reuse only receipts bound to the evidence and review contract."""
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "behavior-audit.json"
    try:
        result_schema = verdict_schema()
        contract = review_contract(prompt_path, result_schema)
        prepared = preparation(scope)
    except (ValueError, OSError) as exc:
        outcome = BehaviorAuditOutcome(
            schema_version=2,
            status="invalid", report_path=str(report_path), scope_digest="", scope=scope,
            error=str(exc), unresolved=("Evidence preparation failed",),
        )
        report_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
        return AuditWork(outcome=outcome)
    digest = hashlib.sha256(prepared.model_dump_json().encode()).hexdigest()
    artifacts = directory / "behavior-audit"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "preparation.json").write_text(prepared.model_dump_json(indent=2), encoding="utf-8")
    selected = prepared.packets[:scope.max_packets]
    pending: list[AuditPacket] = []
    reports: list[AuditReport] = []
    unresolved = [f"{file.path}: {file.status}: {file.message}"
                  for file in prepared.inventory.files if file.status != "parsed"]
    if not prepared.inventory.files or not prepared.selected_candidates:
        unresolved.append("No extractable behavior candidates in the selected source scope")
    grouped: dict[str, list[str]] = defaultdict(list)
    for packet in selected:
        packet_dir = artifacts / packet.digest
        packet_dir.mkdir(exist_ok=True)
        (packet_dir / "packet.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
        receipt = packet_dir / "verdicts.json"
        policy_path = packet_dir / "review-contract.json"
        if not receipt.exists() or not policy_path.exists():
            pending.append(packet)
            continue
        try:
            policy = ReceiptPolicy.model_validate_json(policy_path.read_bytes())
            raw = receipt.read_bytes()
            if policy.contract != contract or policy.verdicts_digest != hashlib.sha256(raw).hexdigest():
                pending.append(packet)
                continue
            report = validate_verdicts(packet, json.loads(raw))
        except ValueError:
            pending.append(packet)
            continue
        reports.append(report)
        (packet_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        candidates = {candidate.id: candidate for candidate in packet.candidates}
        claims = {claim.id: claim for claim in packet.claims}
        for candidate in report.verdicts.candidates:
            if candidate.status == "unresolved":
                unresolved.append(f"{candidate.id}: {candidate.explanation}")
            elif candidate.status == "missing":
                evidence = candidates[candidate.id]
                grouped[evidence.path].append(
                    f"Missing behavior {candidate.id}: {candidate.explanation}\n"
                    f"Source {evidence.path}:{evidence.start_line}\n{evidence.snippet}"
                )
        for claim in report.verdicts.claims:
            if claim.status == "unresolved":
                unresolved.append(f"{claim.id}: {claim.explanation}")
            elif claim.status in {"partial", "contradicted"}:
                evidence_text = "\n".join(candidates[key].snippet for key in claim.candidate_ids)
                grouped[claims[claim.id].path].append(
                    f"{claim.status}: {claim.id}: {claim.explanation}\n"
                    f"Node {claims[claim.id].node}: {claims[claim.id].text}\n{evidence_text}"
                )
    for file in prepared.undocumented:
        symbols = ", ".join(f"{symbol} (line {line})" for symbol, line
                            in zip(file.exported_symbols, file.first_lines, strict=False))
        grouped[file.path].append(
            f"Undocumented file {file.path}: {file.candidate_count} behavior candidates and no claim "
            f"in the book cites this file.\nExported symbols: {symbols}\n"
            "Document the behavior these symbols carry under the node that owns them, with a "
            "`code:` citation into this file, or exclude the file from the source scope when it "
            "is not product behavior."
        )
    repairs: list[AuditRepair] = []
    for target, findings in sorted(grouped.items()):
        batches: list[str] = []
        batch: list[str] = []
        for finding in findings:
            if len(finding) > scope.packet_max_chars:
                unresolved.append(f"{target}: a repair finding exceeds the context budget; inspect the packet report")
                continue
            if batch and (len(batch) >= 20 or len("\n\n".join([*batch, finding])) > scope.packet_max_chars):
                batches.append("\n\n".join(batch))
                batch = []
            batch.append(finding)
        if batch:
            batches.append("\n\n".join(batch))
        repairs.extend(AuditRepair(
            target=target if len(batches) == 1 else f"{target}#behavior-{number}", context=context,
        ) for number, context in enumerate(batches, 1))
    omitted = len(prepared.packets) - len(selected)
    partial = bool(pending or omitted or unresolved)
    outcome = BehaviorAuditOutcome(
        schema_version=2, review_contract=contract, policy_digest=contract.digest,
        status="partial" if partial else "assessed", report_path=str(report_path),
        scope_digest=digest, scope=scope, scope_clear=not partial and not grouped,
        total_packets=len(prepared.packets), assessed_packets=len(reports), omitted_packets=omitted,
        empty_packets=sum(not report.verdicts.candidates and not report.verdicts.claims for report in reports),
        selected_candidates=prepared.selected_candidates, selected_claims=prepared.selected_claims,
        reports=tuple(reports), unresolved=tuple(unresolved),
        undocumented_files=tuple(file.path for file in prepared.undocumented),
        unaudited_packets=tuple(packet_label(packet) for packet in pending),
        repairs=tuple(repairs),
        limitations=(*prepared.inventory.limitations,
                      "Model judgments are not semantic proofs or whole-book completeness guarantees.",
                      "Selection limits apply to packets; omitted packets are not assessed."),
    )
    report_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
    logger.info("behavior audit: %s, %d/%d packets; report %s",
                outcome.status, len(reports), len(prepared.packets), report_path)
    return AuditWork(outcome=outcome, pending=tuple(pending), result_schema=result_schema)


@blueprint.node
def record_audit_verdicts(
    logger: logging.Logger, packet: AuditPacket, verdicts: AuditVerdicts, run_dir: str,
    contract: ReviewContract, prompt_path: Path,
) -> AuditReport:
    """Persist the typed raw reply before checking its exact IDs and reciprocal links."""
    directory = Path(run_dir) / "behavior-audit" / packet.digest
    raw = verdicts.model_dump_json(indent=2)
    attempt = len(list(directory.glob("raw-*.json"))) + 1
    (directory / f"raw-{attempt}.json").write_text(raw, encoding="utf-8")
    report = validate_verdicts(packet, verdicts)
    try:
        current = review_contract(prompt_path, verdict_schema())
    except OSError as exc:
        raise ReviewContractChanged(f"Review contract changed or became unreadable during dispatch: {exc}") from exc
    if current != contract:
        raise ReviewContractChanged("Review contract changed during dispatch; resume under a stable contract")
    policy_path = directory / "review-contract.json"
    # Remove the old binding first: an interrupted write must never bless a new reply.
    policy_path.unlink(missing_ok=True)
    (directory / "verdicts.json").write_text(raw, encoding="utf-8")
    (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    policy = ReceiptPolicy(contract=contract, verdicts_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest())
    policy_path.write_text(policy.model_dump_json(indent=2), encoding="utf-8")
    logger.info("validated audit packet %s", packet.digest)
    return report


@blueprint.node(stub=lambda logger, run_dir, advance: 1)
def audit_pass(logger: logging.Logger, run_dir: str, advance: bool) -> int:
    """How many audit passes this run has opened; `advance` opens one more.

    The count lives beside the receipts rather than in a state kwarg because the drain
    between passes threads its own counters through a dozen signatures, and a reload
    re-enters from a checkpoint that predates any kwarg added after it was written.
    """
    path = Path(run_dir) / "behavior-audit" / "passes"
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(path.read_text(encoding="utf-8") or 0) if path.exists() else 0
    if advance:
        count += 1
        path.write_text(str(count), encoding="utf-8")
        logger.info("behavior audit: pass %d opened", count)
    return count


@blueprint.node
def record_audit_budget_stop(
    logger: logging.Logger, outcome: BehaviorAuditOutcome, turns: int, budget: int,
) -> BehaviorAuditOutcome:
    """Write the partial report a spent turn budget leaves: what was read, what was not."""
    stopped = outcome.model_copy(update={
        "status": "partial", "scope_clear": False,
        "limitations": (*outcome.limitations,
                        f"Turn budget spent: {turns} of {budget} reviewer turns; "
                        f"{len(outcome.unaudited_packets)} packets have no receipt."),
    })
    Path(outcome.report_path).write_text(stopped.model_dump_json(indent=2), encoding="utf-8")
    logger.info("behavior audit: turn budget %d spent, %d packets unaudited", budget, len(outcome.unaudited_packets))
    return stopped


@blueprint.node
def record_audit_error(
    logger: logging.Logger, outcome: BehaviorAuditOutcome, packet_digest: str, error: str,
) -> BehaviorAuditOutcome:
    """Keep invalid verdicts visible in the final report as well as the operator gate."""
    failed = outcome.model_copy(update={"status": "invalid", "scope_clear": False, "error": error})
    path = Path(outcome.report_path)
    path.write_text(failed.model_dump_json(indent=2), encoding="utf-8")
    (path.parent / "behavior-audit" / packet_digest / "validation-error.txt").write_text(error, encoding="utf-8")
    logger.warning("audit packet %s rejected: %s", packet_digest, error)
    return failed
