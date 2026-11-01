"""Per-surface completeness: every owed obligation accounted for exactly once.

Assessment is read-only: it builds a whole-book context for the selected directory,
compiles it with the real compiler, puts the declared checks to synthetic sensitivity
trials, and optionally reads an existing run's evidence. It never starts the product,
never runs a scenario, and never adds a required network dependency.
"""

from __future__ import annotations

import hashlib
import json
import resource
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import model
from ostler.qa import sensitivity as sensitivity_mod
from ostler.qa.assess_evidence import EvidenceSnapshot, snapshot_evidence
from ostler.qa.compile import compile_plan_gaps
from ostler.qa.context import book_context
from ostler.qa.gap_owner import gap_owner
from ostler.qa.outcome import QaOutcome
from ostler.qa.plan_source import Gap
from ostler.qa.readiness import is_defect

ASSESSMENT_SCHEMA_VERSION = 1
ASSESSMENT_TOOL = "ostler-qa-assess"

# The behavior-relevant fields the content fingerprint binds: a claim edit with its
# id kept must move the fingerprint, which the id-set digest alone cannot see.
_FINGERPRINT_FIELDS = (
    "id", "required", "kind", "node", "nodeType", "source", "surface", "requirement",
    "checksDeclared", "checksUnparsed", "actsDeclared", "actsUnparsed", "fixturesDeclared",
    "fixturesUnparsed", "capturesDeclared", "capturesUnparsed", "arrangesNothing", "steps",
    "locators", "conditionsDeclared", "intercepts", "observationsDeclared",
    "observationsUnparsed", "claimCombiner", "extendsUnresolved", "evidenceRequired",
)

_NO_LIVE_EVIDENCE_TYPES = frozenset({"concept", "method"})


@dataclass(frozen=True)
class AssessmentGap:
    """One unmet requirement: its code, its owner, where the fix lands, and the remedy."""

    code: str
    owner: str
    path: str
    line: int
    obligation_id: str
    remedy: str
    blocking: bool


@dataclass(frozen=True)
class ObligationRow:
    """One obligation's independent dimensions: capability, sensitivity, evidence."""

    id: str
    node: str
    source: str
    kind: str
    requirement: str
    required: bool
    declares_checks: bool
    excluded_reason: str
    capability: str
    sensitivity: str
    evidence: str
    evidence_note: str
    gaps: tuple[AssessmentGap, ...]


@dataclass(frozen=True)
class Assessment:
    """The verdict for one selected scope against one contract and evidence snapshot."""

    scope: str
    fingerprint: str
    rows: tuple[ObligationRow, ...]
    capabilities_complete: bool
    sensitivity_complete: bool
    evidence_complete: bool
    complete: bool
    unclassified_gap_kinds: tuple[str, ...]
    evidence: EvidenceSnapshot | None
    seconds: float
    peak_memory_kb: int

    @property
    def required_rows(self) -> list[ObligationRow]:
        """The rows owed live evidence — the verdict's denominator."""
        return [row for row in self.rows if row.required]

    @property
    def excluded_rows(self) -> list[ObligationRow]:
        """The in-scope obligations explicitly not owed evidence, each with its reason."""
        return [row for row in self.rows if not row.required]


def contract_fingerprint(context: dict[str, Any]) -> str:
    """The versioned content fingerprint of the assessed contract.

    Hashes canonical obligations, checks, arrangements and target bindings — never
    credentials — together with the assessment schema and tool version.
    """
    rows = sorted(
        ({field: row.get(field) for field in _FINGERPRINT_FIELDS if field in row}
         for row in context.get("obligations", []) or []),
        key=lambda row: str(row.get("id", "")),
    )
    material = json.dumps(
        {"schema": ASSESSMENT_SCHEMA_VERSION, "tool": ASSESSMENT_TOOL, "obligations": rows},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _exclusion_reason(row: dict[str, Any]) -> str:
    """Why an in-scope obligation owes no live evidence."""
    node_type = str(row.get("nodeType", ""))
    if node_type in _NO_LIVE_EVIDENCE_TYPES:
        return f"a {node_type} node is a definition or internal callable the user never drives, so it owes no live evidence of its own"
    if str(row.get("evidenceRequired", "")) == "context":
        return "not owed live evidence by the selected scope"
    return "not required"


def _sensitivity_status(claim: sensitivity_mod.ClaimReport | None) -> str:
    """The claim's measured status: `undeclared` with no checks, `unknown` when the join missed."""
    if claim is None:
        return "unknown"
    if not claim.trials:
        return "undeclared"
    return claim.status


def _claim_of(row: dict[str, Any], claims: dict[str, sensitivity_mod.ClaimReport]) -> sensitivity_mod.ClaimReport | None:
    """The sensitivity report row one obligation joins to: its own claim, or its node's contract for a journey."""
    claim = claims.get(str(row.get("id", "")).removeprefix("okf:"))
    if claim is None and row.get("kind") == "journey":
        claim = claims.get(f"{row.get('node', '')}:contract")
    return claim


def _rows(
    context: dict[str, Any], gaps: list[Gap],
    claims: dict[str, sensitivity_mod.ClaimReport],
    evidence: EvidenceSnapshot | None,
) -> tuple[ObligationRow, ...]:
    """One assessment row per in-scope obligation, required and excluded alike."""
    by_id: dict[str, list[Gap]] = {}
    for gap in gaps:
        by_id.setdefault(gap.obligation_id, []).append(gap)
    rows: list[ObligationRow] = []
    for raw in context.get("obligations", []) or []:
        oid = str(raw.get("id", ""))
        required = bool(raw.get("required", True))
        declares_checks = bool(raw.get("checksDeclared"))
        position = raw.get("docPosition") or [0, 0]
        line = int(position[0]) if isinstance(position, list) and position else 0
        source = str(raw.get("source", ""))
        owed_gaps = by_id.get(oid, [])
        assessed = tuple(
            AssessmentGap(
                code=gap.kind,
                owner=gap_owner(gap.kind) or "",
                path=gap.owner.partition("#")[0] or source,
                line=line,
                obligation_id=oid,
                remedy=gap.detail,
                blocking=is_defect(gap),
            )
            for gap in owed_gaps
        )
        status, note = (("not-run", "") if evidence is None else evidence.status_of(oid))
        rows.append(ObligationRow(
            id=oid,
            node=str(raw.get("node", "")),
            source=source,
            kind=str(raw.get("kind", "")),
            requirement=str(raw.get("requirement", "")),
            required=required,
            declares_checks=declares_checks,
            excluded_reason="" if required else _exclusion_reason(raw),
            capability="incomplete" if required and any(gap.blocking for gap in assessed) else "complete",
            sensitivity=_sensitivity_status(_claim_of(raw, claims)) if required and declares_checks else "not-declared",
            evidence=status if required and declares_checks else "not-declared",
            evidence_note=note,
            gaps=assessed,
        ))
    return tuple(sorted(rows, key=lambda row: row.id))


def _verdict(rows: tuple[ObligationRow, ...], unclassified: tuple[str, ...]) -> tuple[bool, bool, bool, bool]:
    """The pure completeness predicate over the fixed required rows.

    Only rows that declare checks owe sensitivity and execution evidence; a
    discharged contract row claims nothing, so it cannot be counted as passed.
    """
    required = [row for row in rows if row.required]
    owing = [row for row in required if row.declares_checks]
    capabilities = all(row.capability == "complete" for row in required)
    sensitivity = all(row.sensitivity == "sensitive" for row in owing)
    evidence = all(row.evidence == "complete" for row in owing)
    complete = capabilities and sensitivity and evidence and not unclassified
    return capabilities, sensitivity, evidence, complete


def assess(root: Path, *, book: str, spec_dir: Path | None = None) -> Assessment:
    """Assess one selected book directory against its contract and any recorded evidence."""
    started = time.perf_counter()
    scope = book.strip().strip("/")
    context = book_context(root, books=[scope])
    fingerprint = contract_fingerprint(context)
    compilation = compile_plan_gaps(context, story="surface-assessment")
    claims = {row.claim: row for row in sensitivity_mod.report(model.load(cwd=root))}
    snapshot = (snapshot_evidence(spec_dir, fingerprint, schema_version=ASSESSMENT_SCHEMA_VERSION)
                if spec_dir is not None else None)
    rows = _rows(context, list(compilation.gaps), claims, snapshot)
    unclassified = tuple(sorted({gap.code for row in rows for gap in row.gaps if not gap.owner}))
    capabilities, sensitivity, evidence, complete = _verdict(rows, unclassified)
    return Assessment(
        scope=scope,
        fingerprint=fingerprint,
        rows=rows,
        capabilities_complete=capabilities,
        sensitivity_complete=sensitivity,
        evidence_complete=evidence,
        complete=complete,
        unclassified_gap_kinds=unclassified,
        evidence=snapshot,
        seconds=round(time.perf_counter() - started, 3),
        peak_memory_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )


def _scope_problems(root: Path, book: str) -> list[str]:
    """Why *book* is not an assessable scope, or an empty list."""
    scope = book.strip().strip("/")
    if not scope:
        return ["--book names an empty scope"]
    target = root / scope
    if not target.is_dir():
        return [f"--book {scope!r} is not a directory under {root}"]
    if not any(target.rglob("*.md")):
        return [f"--book {scope!r} holds no markdown pages"]
    return []


def cmd_assess(root: Path, *, book: str, spec_dir: Path | None = None) -> QaOutcome:
    """The `ostler qa assess` verdict for one book directory; exit meaning via ok/status."""
    problems = _scope_problems(root, book)
    if problems:
        return QaOutcome(ok=False, status="invalid", message="error: " + "; ".join(problems),
                         data={"status": "invalid", "problems": problems})
    try:
        assessment = assess(root, book=book, spec_dir=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return QaOutcome(ok=False, status="invalid", message=f"error: {exc}",
                         data={"status": "invalid", "problems": [str(exc)]})
    return QaOutcome(ok=assessment.complete, status="complete" if assessment.complete else "incomplete",
                     message=render(assessment), data=to_json(assessment))


def to_json(assessment: Assessment) -> dict[str, Any]:
    """The machine-readable verdict: the same rows the human view renders."""
    required = assessment.required_rows
    return {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "scope": assessment.scope,
        "contract_fingerprint": assessment.fingerprint,
        "required_count": len(required),
        "excluded_count": len(assessment.excluded_rows),
        "capabilities_complete": assessment.capabilities_complete,
        "sensitivity_complete": assessment.sensitivity_complete,
        "evidence_complete": assessment.evidence_complete,
        "complete": assessment.complete,
        "unclassified_gap_kinds": list(assessment.unclassified_gap_kinds),
        "evidence": None if assessment.evidence is None else {
            "applicability": assessment.evidence.applicability,
            "recorded_fingerprint": assessment.evidence.recorded_fingerprint,
            "reasons": list(assessment.evidence.reasons),
        },
        "measurements": {"seconds": assessment.seconds, "peakMemoryKb": assessment.peak_memory_kb},
        "obligations": [
            {
                "id": row.id, "node": row.node, "source": row.source, "kind": row.kind,
                "required": row.required, "declares_checks": row.declares_checks,
                "excluded_reason": row.excluded_reason,
                "capability": row.capability, "sensitivity": row.sensitivity,
                "evidence": row.evidence, "evidence_note": row.evidence_note,
                "gaps": [gap.__dict__ for gap in row.gaps],
            }
            for row in assessment.rows
        ],
    }


def render(assessment: Assessment) -> str:
    """The human verdict: the same obligation set the JSON view describes."""
    lines = [
        f"surface assessment: {assessment.scope}",
        f"  contract: {assessment.fingerprint}",
        f"  required: {len(assessment.required_rows)}, excluded: {len(assessment.excluded_rows)}",
        f"  capabilities: {'complete' if assessment.capabilities_complete else 'INCOMPLETE'}",
        f"  sensitivity: {'complete' if assessment.sensitivity_complete else 'INCOMPLETE'}",
        f"  evidence: {'complete' if assessment.evidence_complete else 'not-run'}",
        f"  verdict: {'COMPLETE' if assessment.complete else 'INCOMPLETE'}"
        f" ({assessment.seconds}s, peak {assessment.peak_memory_kb} KB)",
    ]
    for row in assessment.rows:
        mark = "required" if row.required else f"excluded: {row.excluded_reason}"
        note = f" — {row.evidence_note}" if row.evidence_note else ""
        lines.append(f"  {row.id}  [{mark}] capability={row.capability}"
                     f" sensitivity={row.sensitivity} evidence={row.evidence}{note}")
        for gap in row.gaps:
            owner = gap.owner or "UNCLASSIFIED"
            discharged = "" if gap.blocking else " (discharged)"
            lines.append(f"    [{owner}] {gap.code}{discharged}: {gap.remedy}")
    for kind in assessment.unclassified_gap_kinds:
        lines.append(f"  UNCLASSIFIED gap kind: {kind} — the assessment cannot place its ownership")
    return "\n".join(lines)
