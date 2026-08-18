"""What the surveyor sub-flow validates: its agent replies, and its node returns.

Mirrors the survey node modules one for one. One difference from the YAML worth naming:
every `*_ok` / `needs_*` / `has_*` output was a `"yes"`/`"no"` **string**, because a YAML
`branch` node compares rendered text. A Python state branches with `if`, so these are
`bool`. The strings were an artifact of the engine, not of the survey — nothing on disk
carried them — so the workflow's artifacts are unchanged by the switch.
"""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult

# ── node returns ────────────────────────────────────────────────────────────


class SurveyConfig(AuthorResult):
    """`load_survey_config` — the surveyor's paths, decided once at the top of the run.

    Every path but `repo_root` is **repo-relative**, exactly as the script emitted it:
    the nodes join it onto a freshly resolved root, so a `cfg` checkpointed on one
    machine still resolves on another.
    """

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
    """`select_next_unit` — the next pending unit, or that none is left.

    `has_unit` false is not a failure: the empty pending set **is** the coverage proof,
    and the flow moves to the coverage gate.
    """

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
    """`verify_records` — the survey's coverage claim, made auditable.

    The script's `verify_ok` was tri-state (`yes`/`no`/`skip`), and the third value is
    not a spelling of the first two: `skip` means *nothing was surveyed*, which the flow
    lets through the same way it lets `yes` through, while the report says which happened.
    So the tri-state is kept as two booleans rather than collapsed: `holds` is what the
    gate branches on, and `nothing_surveyed` is why it holds when it does.
    """

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


# ── agent replies ───────────────────────────────────────────────────────────


class PlanResult(AuthorResult):
    """`surveyor/prompts/plan-units.md` — the enumeration rules the planner wrote.

    `status` is `complete` or `blocked`; blocked routes to the operator gate.
    """

    status: str = ""
    notes: str = ""


class UnitAssessment(AuthorResult):
    """`surveyor/prompts/assess-unit.md` — one unit assessed, or found too big.

    `status` is `assessed`, `clean`, `blocked` or `split`; only `split` is routed on
    here, and it is what makes granularity self-healing.
    """

    status: str = ""
    notes: str = ""


class RecordFix(AuthorResult):
    """`surveyor/prompts/fix-record.md` — one bounded repair of an invalid record.

    `status` is `fixed` or `blocked`; the loop re-validates either way, so the reply is
    advisory and `validate_record` is what decides.
    """

    status: str = ""
    notes: str = ""


class PartitionProposal(AuthorResult):
    """`surveyor/prompts/partition-findings.md` — findings clustered into work items.

    `status` is `complete` or `blocked`; blocked routes to the operator gate.
    """

    status: str = ""
    notes: str = ""


class OperatorResolution(AuthorResult):
    """`surveyor/prompts/resolve-operator.md` — the diagnostic investigator's report.

    The resolver never decides on the operator's behalf; it only investigates a block
    and writes findings into the context file, so the flow always parks with `Await`
    after this returns. `decision` is a relic of the old auto-resolve contract kept for
    the field's shape rather than read; the two live fields are `notes` and `tried`.
    Note the field is `notes` here and `summary` in `coder`'s copy of this model: the
    two prompts genuinely ask for different key names, and the port follows each prompt
    rather than unifying a name the model would then not emit.
    """

    decision: str = ""
    notes: str = ""

    #: What the resolver attempted and ruled out before it escalated, one line each. It
    #: is the diagnosis so far, and without it the human who arrives at the gate re-runs
    #: every dead end the resolver already paid for. Defaulted and never required: an
    #: older transcript parses with it absent.
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
