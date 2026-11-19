"""What the parity survey validates: its agent replies, and its node returns."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult
from workhorse.pyflow import dry_run


class Expansion(AuthorResult):
    """`expand_parity_inventory` — the materialized (or already-frozen) unit list."""

    expand_ok: bool = False
    expand_errors: str = ""
    unit_count: int = 0
    inventory_note: str = ""


class UnitPick(AuthorResult):
    """`select_next_unit` — the next pending unit, or that none is left."""

    has_unit: bool = False
    unit_id: str = ""
    unit_path: str = ""
    unit_kind: str = ""
    record_path: str = ""
    reason: str = ""
    progress: str = ""
    kinds: str = ""


class MarkResult(AuthorResult):
    """`mark_unit` — the inventory entry stamped with its record's status."""

    marked: bool = False
    unit_status: str = ""
    mark_note: str = ""


class RecordCheck(AuthorResult):
    """`validate_record` — one finding record, checked hard and deterministically."""

    record_ok: bool = False
    record_errors: str = ""


class VerifyResult(AuthorResult):
    """`verify_records` — the survey's coverage claim, made auditable."""

    holds: bool = False
    nothing_surveyed: bool = False
    verify_errors: str = ""
    verify_report: str = ""


class EmitResult(AuthorResult):
    """`emit_parity_records` — the records filed."""

    emit_ok: bool = False
    emit_errors: str = ""
    bullet_count: int = 0
    emit_note: str = ""


@dry_run(status="assessed")
class UnitAssessment(AuthorResult):
    """`parity_surveyor/prompts/assess-parity-unit.md` — one unit assessed."""

    status: str = ""
    notes: str = ""


@dry_run(decision="answered")
class OperatorResolution(AuthorResult):
    """`finalize/prompts/resolve-integrity.md` — the diagnostic investigator's report."""

    decision: str = ""
    notes: str = ""

    tried: list[str] = []


__all__ = [
    "EmitResult",
    "Expansion",
    "MarkResult",
    "OperatorResolution",
    "RecordCheck",
    "UnitAssessment",
    "UnitPick",
    "VerifyResult",
]
