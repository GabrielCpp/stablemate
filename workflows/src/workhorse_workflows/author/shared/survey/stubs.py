"""What the survey sub-flows' gates return under `--dry-run`.

Same reason as `nodes/_stubs.py`, and the same shape: every one of these gates branches
on a `*_ok` boolean whose blank stand-in is `False`, which is the failing arm. In the
plan stage that arm loops back to the planner and then to the operator resolver — and
because the registry stubs `resolve-operator` as `answered`, it loops until the
transition budget is spent rather than blocking. In the emit stage it raises. Neither is
a finding about the workflow, only about what a blank means.
"""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas.survey import (
    EmitResult,
    Expansion,
    PartitionCheck,
    RecordCheck,
    SplitResult,
    VerifyResult,
)


def expanded(*_args: object, **_kwargs: object) -> Expansion:
    """`expand_inventory`, `expand_parity_inventory` — the rules yielded units."""
    return Expansion(expand_ok=True)


def split(*_args: object, **_kwargs: object) -> SplitResult:
    """`split_unit` — the unit divided into the parts the assessor asked for."""
    return SplitResult(split_ok=True)


def recorded(*_args: object, **_kwargs: object) -> RecordCheck:
    """`validate_record` — the finding record is well-formed."""
    return RecordCheck(record_ok=True)


def verified(*_args: object, **_kwargs: object) -> VerifyResult:
    """`verify_records` — the survey's coverage claim holds."""
    return VerifyResult(holds=True)


def partitioned(*_args: object, **_kwargs: object) -> PartitionCheck:
    """`validate_partition` — the clusters account for the findings."""
    return PartitionCheck(partition_ok=True)


def emitted(*_args: object, **_kwargs: object) -> EmitResult:
    """`emit_artifacts`, `emit_parity_backlog` — the backlog and manifest were written."""
    return EmitResult(emit_ok=True)


__all__ = ["emitted", "expanded", "partitioned", "recorded", "split", "verified"]
