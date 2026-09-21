"""What the surveyor sub-flow validates: its agent replies, and its node returns."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult



class SurveyConfig(AuthorResult):
    """`load_survey_config` — the surveyor's paths, decided once at the top of the run."""

    repo_root: str = ""
    rubric: str = ""
    survey_dir: str = ""
    rules: str = ""
    inventory: str = ""
    findings_dir: str = ""
    partition: str = ""
    backlog: str = ""
    unit_manifest: str = ""
    context: str = ""


class InventoryCheck(AuthorResult):
    """`check_inventory` — does the granularity planner need to run at all?"""

    needs_plan: bool = False
    check_note: str = ""


class Expansion(AuthorResult):
    """`expand_inventory` — the materialized (or already-frozen) unit list."""

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


class SplitResult(AuthorResult):
    """`split_unit` — a too-big folder unit replaced by its immediate children."""

    split_ok: bool = False
    children_count: int = 0
    split_errors: str = ""


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


class PartitionCheck(AuthorResult):
    """`validate_partition` — the cluster file, checked against the findings it claims."""

    partition_ok: bool = False
    partition_errors: str = ""


class EmitResult(AuthorResult):
    """`emit_artifacts` — author backlog bullets plus survey-owned traceability."""

    emit_ok: bool = False
    emit_errors: str = ""
    bullet_count: int = 0
    emit_note: str = ""




class PlanResult(AuthorResult):
    """`surveyor/prompts/plan-units.md` — the enumeration rules the planner wrote."""

    status: str = ""
    notes: str = ""


class UnitAssessment(AuthorResult):
    """`surveyor/prompts/assess-unit.md` — one unit assessed, or found too big."""

    status: str = ""
    notes: str = ""


class RecordFix(AuthorResult):
    """`surveyor/prompts/fix-record.md` — one bounded repair of an invalid record."""

    status: str = ""
    notes: str = ""


class PartitionProposal(AuthorResult):
    """`surveyor/prompts/partition-findings.md` — findings clustered into work items."""

    status: str = ""
    notes: str = ""


class OperatorResolution(AuthorResult):
    """`surveyor/prompts/resolve-operator.md` — the diagnostic investigator's report."""

    decision: str = ""
    notes: str = ""

    tried: list[str] = []


__all__ = [
    "EmitResult",
    "Expansion",
    "InventoryCheck",
    "MarkResult",
    "OperatorResolution",
    "PartitionCheck",
    "PartitionProposal",
    "PlanResult",
    "RecordCheck",
    "RecordFix",
    "SplitResult",
    "SurveyConfig",
    "UnitAssessment",
    "UnitPick",
    "VerifyResult",
]
