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
from ostler.behavior_memo import (
    MemoRecall, VerdictMemo, merge_verdicts, reduce_packet, salvage_verdicts,
)
from ostler.index import IndexStore
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


class IncompleteVerdicts(ValueError):
    """The reply answered for some of the packet and left the rest owing.

    Carries what can be salvaged, so the caller can ask for the gap instead of
    re-asking the packet — which is the failure mode this exists for: a reviewer that
    drops one id out of nineteen drops it again when handed the same nineteen.
    """

    def __init__(self, packet: AuditPacket, recall: MemoRecall, owing: tuple[str, ...],
                 cause: Exception) -> None:
        super().__init__(f"{len(owing)} item(s) unanswered: {', '.join(owing)} ({cause})")
        self.packet = packet
        self.recall = recall
        self.owing = owing


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
    memo_hits: int = Field(default=0, description="Packets whose every verdict the index remembered: no turn spent")
    memo_partial: int = Field(
        default=0, description="Packets reduced to the items the index did not remember before dispatch")
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


def verdict_memo(scope: AuditScope, contract: ReviewContract) -> VerdictMemo:
    """The per-item verdict memo for this book, in ostler's index under this contract."""
    return VerdictMemo(IndexStore(paths.docs_root(scope.docs_path)), contract.digest)


def write_receipt(packet_dir: Path, report: AuditReport, contract: ReviewContract) -> None:
    """Bind *report* to its packet dir: verdicts, report, and the contract they answer."""
    raw = report.verdicts.model_dump_json(indent=2)
    policy_path = packet_dir / "review-contract.json"
    # Remove the old binding first: an interrupted write must never bless a new reply.
    policy_path.unlink(missing_ok=True)
    (packet_dir / "verdicts.json").write_text(raw, encoding="utf-8")
    (packet_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    policy = ReceiptPolicy(contract=contract, verdicts_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest())
    policy_path.write_text(policy.model_dump_json(indent=2), encoding="utf-8")


def read_receipt(packet_dir: Path, packet: AuditPacket, contract: ReviewContract) -> AuditReport | None:
    """The report a current receipt in *packet_dir* proves, or ``None`` when there is none."""
    receipt = packet_dir / "verdicts.json"
    policy_path = packet_dir / "review-contract.json"
    if not receipt.exists() or not policy_path.exists():
        return None
    try:
        policy = ReceiptPolicy.model_validate_json(policy_path.read_bytes())
        raw = receipt.read_bytes()
        if policy.contract != contract or policy.verdicts_digest != hashlib.sha256(raw).hexdigest():
            return None
        return validate_verdicts(packet, json.loads(raw))
    except ValueError:
        return None


def recall_report(
    artifacts: Path, packet: AuditPacket, memo: VerdictMemo, contract: ReviewContract,
) -> AuditReport | AuditPacket:
    """What the memo already settles about *packet*: a whole report, or the packet still owed.

    A whole hit becomes a receipt in the packet's own dir, indistinguishable from one a
    reviewer wrote, so the next assessment never asks the memo again. A partial hit
    returns the reduced packet and leaves the full one beside it as ``parent.json``, for
    the record node to merge the reduced reply into. A memo that does not validate against
    the packet is a miss.
    """
    recall = memo.recall(packet)
    reduced = reduce_packet(packet, recall)
    if reduced is None:
        try:
            report = merge_verdicts(packet, recall, None)
        except ValueError:
            return packet
        write_receipt(artifacts / packet.digest, report, contract)
        return report
    if reduced is packet:
        return packet
    reduced_dir = artifacts / reduced.digest
    reduced_dir.mkdir(exist_ok=True)
    (reduced_dir / "packet.json").write_text(reduced.model_dump_json(indent=2), encoding="utf-8")
    (reduced_dir / "parent.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    return reduced


def preparation(scope: AuditScope) -> AuditPreparation:
    """Read a scoped book without formatting, indexing, or importing source."""
    root = paths.docs_root(scope.docs_path)
    source = Path(scope.source_path)
    if source.is_absolute():
        source = source.resolve().relative_to(root.resolve())
    if not scope.source_path:
        raise ValueError("source_path is required: choose an explicit source file or directory")
    graph = load(root)
    # The scope goes *into* the read, not onto its result. `extract_book` re-reads every node
    # it visits off disk and raises when the section has moved under the graph, so filtering
    # afterwards still opens and validates the whole book — which makes this run fail on a
    # sibling service's documents while that service's own run is authoring them. Scoping the
    # read also keeps a duplicate-heading skip elsewhere out of this service's limitations.
    claims = extract_book(graph, scope=paths.book_scope(root, scope.service))
    evidence = extract_evidence(root, [source.as_posix()], context_paths=scope.context_paths)
    failures = [f"{file.path}: {file.status}: {file.message}"
                for file in evidence.context_files if file.status != "parsed"]
    if failures:
        raise ValueError("Support context unavailable: " + "; ".join(failures))
    return build_audit_packets(
        evidence, claims,
        max_items=scope.packet_max_items, max_chars=scope.packet_max_chars, root=root,
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
    memo = verdict_memo(scope, contract)
    memo_hits = memo_partial = 0
    for packet in selected:
        packet_dir = artifacts / packet.digest
        packet_dir.mkdir(exist_ok=True)
        (packet_dir / "packet.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
        report = read_receipt(packet_dir, packet, contract)
        if report is None:
            recalled = recall_report(artifacts, packet, memo, contract)
            if isinstance(recalled, AuditPacket):
                if recalled is not packet:
                    memo_partial += 1
                pending.append(recalled)
                continue
            memo_hits += 1
            report = recalled
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
        memo_hits=memo_hits, memo_partial=memo_partial,
        repairs=tuple(repairs),
        limitations=(*prepared.inventory.limitations,
                      "Model judgments are not semantic proofs or whole-book completeness guarantees.",
                      "Selection limits apply to packets; omitted packets are not assessed."),
    )
    report_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
    logger.info("behavior audit: %s, %d/%d packets (%d whole memo hits, %d reduced); report %s",
                outcome.status, len(reports), len(prepared.packets), memo_hits, memo_partial, report_path)
    return AuditWork(outcome=outcome, pending=tuple(pending), result_schema=result_schema)


#: Verdicts salvaged from a rejected reply, staged beside a reduced packet. They are
#: deliberately not written to the memo: the memo holds verdicts of reports that
#: validated, and these have not been merged into one yet.
REPAIR_RECALL_FILE = "recall.json"


def _staged_recall(directory: Path, recalled: MemoRecall) -> MemoRecall:
    """The memo's recall for a parent, plus whatever a repair staged beside the reduced packet.

    Both stand for the same thing — an item already judged that the reduced packet
    therefore omits — so the reviewer's reply outranks either, which ``merge_verdicts``
    handles. Where they overlap the staged verdict wins: it was salvaged from a reply to
    *this* packet, while the memo's was recalled from another pass.
    """
    path = directory / REPAIR_RECALL_FILE
    if not path.exists():
        return recalled
    staged = MemoRecall.model_validate_json(path.read_bytes())
    claims = {verdict.id: verdict for verdict in recalled.claims}
    claims.update({verdict.id: verdict for verdict in staged.claims})
    candidates = {verdict.id: verdict for verdict in recalled.candidates}
    candidates.update({verdict.id: verdict for verdict in staged.candidates})
    return MemoRecall(claims=tuple(claims.values()), candidates=tuple(candidates.values()))


@blueprint.node
def stage_repair(
    logger: logging.Logger, packet: AuditPacket, recall: MemoRecall, run_dir: str,
) -> AuditPacket | None:
    """Lay out the reduced packet a short reply left owing, or ``None`` if it salvaged nothing.

    The layout is the one ``recall_report`` already writes for a memo-reduced packet —
    ``packet.json`` beside ``parent.json`` — so the record node merges a repair reply by
    the path it already had. The third file, ``recall.json``, is what the memo cannot
    supply: verdicts this reply earned that no validated report has yet contained.

    *packet* may itself be a reduced packet, in which case its own parent and staged
    recall are carried forward, so a repair of a repair still merges against the full
    packet the receipt is owed on.
    """
    artifacts = Path(run_dir) / "behavior-audit"
    dispatched_dir = artifacts / packet.digest
    parent_path = dispatched_dir / "parent.json"
    parent = (AuditPacket.model_validate_json(parent_path.read_bytes())
              if parent_path.exists() else packet)
    carried = _staged_recall(dispatched_dir, recall)
    reduced = reduce_packet(packet, recall)
    if reduced is None or reduced is packet:
        logger.info("no repair staged for %s: the reply salvaged nothing reducible", packet.digest)
        return None
    reduced_dir = artifacts / reduced.digest
    reduced_dir.mkdir(parents=True, exist_ok=True)
    (reduced_dir / "packet.json").write_text(reduced.model_dump_json(indent=2), encoding="utf-8")
    (reduced_dir / "parent.json").write_text(parent.model_dump_json(indent=2), encoding="utf-8")
    (reduced_dir / REPAIR_RECALL_FILE).write_text(carried.model_dump_json(indent=2), encoding="utf-8")
    logger.info("staged repair packet %s for %s: %d claim(s), %d candidate(s) still owed",
                reduced.digest, packet.digest, len(reduced.claims), len(reduced.candidates))
    return reduced


@blueprint.node
def load_repair(
    logger: logging.Logger, repair_digest: str, parent_digest: str, run_dir: str,
) -> AuditPacket | None:
    """A staged repair packet, but only if it is still owed against *parent_digest*.

    ``assess_audit`` rebuilds its packets from the book on every re-entry, so a repair
    staged before an edit can outlive the packet it was owed on. The parent check is
    what makes that harmless: a repair whose parent is no longer what this pass is
    holding is ignored, and the full packet is dispatched instead.
    """
    if not repair_digest:
        return None
    directory = Path(run_dir) / "behavior-audit" / repair_digest
    packet_path = directory / "packet.json"
    parent_path = directory / "parent.json"
    if not packet_path.exists() or not parent_path.exists():
        return None
    parent = AuditPacket.model_validate_json(parent_path.read_bytes())
    if parent.digest != parent_digest:
        logger.info("discarding repair %s: its parent %s is not the pending packet %s",
                    repair_digest, parent.digest, parent_digest)
        return None
    return AuditPacket.model_validate_json(packet_path.read_bytes())


def _owed_or_original(packet: AuditPacket, verdicts: AuditVerdicts, exc: ValueError) -> ValueError:
    """``IncompleteVerdicts`` when the rejected reply names a repairable gap, else *exc*.

    Salvage decides this rather than the message text: whatever the reply failed on,
    what matters is whether some item is left without a usable verdict, because that is
    the set a reduced packet can be built from. An empty owing set means every item
    answered its own rules and the reply broke a whole-reply rule instead — nothing to
    re-ask, so the original rejection stands.
    """
    try:
        recall, owing = salvage_verdicts(packet, verdicts)
    except ValueError:
        return exc
    return IncompleteVerdicts(packet, recall, owing, exc) if owing else exc


@blueprint.node
def record_audit_verdicts(
    logger: logging.Logger, packet: AuditPacket, verdicts: AuditVerdicts, run_dir: str,
    contract: ReviewContract, prompt_path: Path, scope: AuditScope | None = None,
) -> AuditReport:
    """Persist the typed raw reply before checking its exact IDs and reciprocal links.

    A reply to a reduced packet is merged over what the memo recalled and validated
    against the full packet in ``parent.json``; the receipt is the full packet's. Every
    verdict of the resulting report is then remembered, so the next pass over the same
    bytes is a whole hit. Without a *scope* there is no memo, which is the standalone
    shape a checkpoint written before the memo existed still resumes into.
    """
    directory = Path(run_dir) / "behavior-audit" / packet.digest
    raw = verdicts.model_dump_json(indent=2)
    attempt = len(list(directory.glob("raw-*.json"))) + 1
    (directory / f"raw-{attempt}.json").write_text(raw, encoding="utf-8")
    memo = verdict_memo(scope, contract) if scope is not None else None
    parent_path = directory / "parent.json"
    try:
        report = validate_verdicts(packet, verdicts)
    except ValueError as exc:
        raise _owed_or_original(packet, verdicts, exc) from exc
    if memo is not None and parent_path.exists():
        parent = AuditPacket.model_validate_json(parent_path.read_bytes())
        report = merge_verdicts(parent, _staged_recall(directory, memo.recall(parent)), verdicts)
    else:
        parent = packet
    try:
        current = review_contract(prompt_path, verdict_schema())
    except OSError as exc:
        raise ReviewContractChanged(f"Review contract changed or became unreadable during dispatch: {exc}") from exc
    if current != contract:
        raise ReviewContractChanged("Review contract changed during dispatch; resume under a stable contract")
    parent_dir = Path(run_dir) / "behavior-audit" / parent.digest
    parent_dir.mkdir(exist_ok=True)
    write_receipt(parent_dir, report, contract)
    if memo is not None:
        remembered = memo.remember(parent, report)
        logger.info("validated audit packet %s; %d verdicts remembered", parent.digest, remembered)
    else:
        logger.info("validated audit packet %s", parent.digest)
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
