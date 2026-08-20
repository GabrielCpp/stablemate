"""What makes a service real to the planner — one assertion, two callers.

Genesis's **postcondition** is the main loop's **precondition**: the thing genesis has to
leave behind is exactly the thing `record_plan` refuses to plan without. The YAML
kept that as `scripts/service_contract.py`, imported by both `validate-genesis.py` and
`validate-plan-context.py`, with the reason written on it: without the sharing the two drift
apart and the only symptom is a confusing planner rejection several stages later.

The sharing is the whole point, so this sits in `shared/` rather than inside either
`genesis/nodes.py` or the main graph's `nodes/` — a helper private to one of them would be
one import away from being copied into the other. Two callers is exactly what `shared/`
counts.

**Genesis carries zero stack knowledge**, and this file carries none either. Which markers
prove a service is real arrives as a flow parameter and is written through verbatim; a
repo that declares none has the check skipped, not replaced by a guess. The fallback list
that used to live here — `main.go`, `package.json`, `pubspec.yaml` — was read by nothing
and could only ever have failed an unconfigured repo on a stack it never claimed to be.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

def service_problems(service_abs: Path, markers: Sequence[str], label: str) -> list[str]:
    """Every reason `service_abs` is not a service the planner can target, or `[]`.

    A falsy `markers` means "this repo has not configured any", and the marker check is
    then skipped rather than failed — deliberately. Any default this function could reach
    for would be a stack it picked on the repo's behalf.
    """
    if not service_abs.exists():
        return [f"{label}: path does not exist at {service_abs}"]
    if not service_abs.is_dir():
        return [f"{label}: path is not a directory"]
    if markers and not any((service_abs / m).exists() for m in markers):
        return [
            f"{label}: no service marker found "
            f"(expected one of {list(markers)} in {service_abs})"
        ]
    return []


__all__ = ["service_problems"]
