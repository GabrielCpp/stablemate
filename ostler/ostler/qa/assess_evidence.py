"""Reading one run's recorded evidence for a surface assessment.

The assessment is strict about identity: evidence produced by the normal run is
applicable only when it recorded the versioned contract fingerprint the run actually
executed against, and that fingerprint matches the contract being assessed. A legacy
run, an interrupted one, a diff-selected subset or a malformed artifact proves nothing
about the current surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler.qa.evidence_map import EvidenceMapError, build_evidence_map

EVIDENCE_FILE = "qa-evidence.json"

# The run observed the product for an obligation and every declared check passed.
_EXECUTED = frozenset({"covered", "insensitive"})


@dataclass(frozen=True)
class EvidenceSnapshot:
    """What one spec directory's run can and cannot prove for one assessed contract.

    *applicability* is `applicable` (join per obligation), `absent` (no completed run
    recorded), `stale` (the recorded contract differs from the assessed one) or
    `unusable` (recorded evidence carries no adequate identity, or is malformed).
    """

    applicability: str
    reasons: tuple[str, ...]
    recorded_fingerprint: str
    rows: dict[str, tuple[str, str]]

    def status_of(self, obligation_id: str) -> tuple[str, str]:
        """The execution-evidence status for one obligation, `(status, why)`."""
        if self.applicability == "absent":
            return "not-run", self.reasons[0] if self.reasons else "no completed run recorded"
        if self.applicability == "stale":
            return "stale", (self.reasons[0] if self.reasons else
                             "the recorded contract fingerprint differs from the assessed contract")
        if self.applicability == "unusable":
            return "unavailable", self.reasons[0] if self.reasons else "the recorded evidence carries no adequate identity"
        return self.rows.get(obligation_id, (
            "unavailable",
            "no evidence row binds this obligation — the recorded run's contract did not owe it, "
            "or nothing observed it",
        ))


def _duplicate_ids(rows: Any) -> list[str]:
    """Every obligation id recorded twice — a malformed artifact, not a contract."""
    seen: set[str] = set()
    duplicated: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict) and row.get("id"):
            oid = str(row["id"])
            (duplicated if oid in seen else seen).add(oid)
    return sorted(duplicated)


def snapshot_evidence(spec_dir: Path, current_fingerprint: str, *, schema_version: int) -> EvidenceSnapshot:
    """What the run recorded under *spec_dir* can prove about the assessed contract."""
    evidence_path = spec_dir / EVIDENCE_FILE
    if not evidence_path.is_file():
        return EvidenceSnapshot("absent", (f"{EVIDENCE_FILE} is not recorded under {spec_dir} — "
                                           "the run never completed here",), "", {})
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return EvidenceSnapshot("unusable", (f"{EVIDENCE_FILE} is unreadable: {exc}",), "", {})
    if not isinstance(data, dict):
        return EvidenceSnapshot("unusable", (f"{EVIDENCE_FILE} does not hold an evidence object",), "", {})
    duplicated = _duplicate_ids(data.get("obligations"))
    if duplicated:
        return EvidenceSnapshot("unusable", (
            f"{EVIDENCE_FILE} records duplicate obligation ids {duplicated} — malformed",), "", {})
    recorded = str(data.get("contractFingerprint") or "")
    version = data.get("fingerprintVersion")
    if not recorded or version != schema_version:
        return EvidenceSnapshot("unusable", (
            f"{EVIDENCE_FILE} records no versioned contract fingerprint — evidence produced "
            "before identity was recorded cannot prove the current contract",), recorded, {})
    if recorded != current_fingerprint:
        return EvidenceSnapshot("stale", (
            f"the recorded run's contract fingerprint {recorded[:12]}… differs from the "
            f"assessed contract {current_fingerprint[:12]}… — the contract moved after the run",
        ), recorded, {})
    try:
        evidence_map = build_evidence_map(spec_dir)
    except EvidenceMapError as exc:
        return EvidenceSnapshot("unusable", (f"the recorded run cannot be read: {exc}",), recorded, {})
    rows = {
        str(row["id"]): (
            "complete" if row.get("status") in _EXECUTED else "unavailable",
            str(row.get("why", "")),
        )
        for row in evidence_map.get("obligations", [])
    }
    return EvidenceSnapshot("applicable", (), recorded, rows)
