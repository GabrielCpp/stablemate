"""What the parity survey's gates return under `--dry-run`."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas.survey import (
    EmitResult,
    Expansion,
    RecordCheck,
    VerifyResult,
)


def expanded(*_args: object, **_kwargs: object) -> Expansion:
    """`expand_parity_inventory` — the baseline yielded units."""
    return Expansion(expand_ok=True)


def recorded(*_args: object, **_kwargs: object) -> RecordCheck:
    """`validate_record` — the finding record is well-formed."""
    return RecordCheck(record_ok=True)


def verified(*_args: object, **_kwargs: object) -> VerifyResult:
    """`verify_records` — the survey's coverage claim holds."""
    return VerifyResult(holds=True)


def emitted(*_args: object, **_kwargs: object) -> EmitResult:
    """`emit_parity_records` — the records were filed."""
    return EmitResult(emit_ok=True)


__all__ = ["emitted", "expanded", "recorded", "verified"]
