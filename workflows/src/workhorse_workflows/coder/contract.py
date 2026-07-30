"""What makes a service real to the planner — one assertion, two callers.

Genesis's **postcondition** is the main loop's **precondition**: the thing genesis has to
leave behind is exactly the thing `validate_plan_context` refuses to plan without. The YAML
kept that as `scripts/service_contract.py`, imported by both `validate-genesis.py` and
`validate-plan-context.py`, with the reason written on it: without the sharing the two drift
apart and the only symptom is a confusing planner rejection several stages later.

The sharing is the whole point, so this sits at package level rather than inside either
`nodes/genesis.py` or the main graph's nodes module — a helper private to one of them would
be one import away from being copied into the other.

**Genesis carries zero stack knowledge**, and `DEFAULT_MARKERS` is the edge of that rule: it
is a fallback list of filenames, not a mapping from a stack to its marker. Which markers a
repo actually declares arrives as a flow parameter and is written through verbatim, because
`scripts/check_public.py` asserts no base workflow may depend on the private overlay and the
stack packs live there.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

#: The fallback marker set, used when a repo declares none of its own. Deliberately a flat
#: list rather than a stack→marker table: this file may not know that `go.mod` means Go.
DEFAULT_MARKERS: tuple[str, ...] = ("main.go", "go.mod", "package.json", "pubspec.yaml", "main.tf")


def service_problems(service_abs: Path, markers: Sequence[str], label: str) -> list[str]:
    """Every reason `service_abs` is not a service the planner can target, or `[]`.

    A falsy `markers` means "this repo has not configured any", and the marker check is
    then skipped rather than failed — deliberately. The alternative, falling back to
    `DEFAULT_MARKERS` here, would make an unconfigured repo fail on a stack it never
    claimed to be.
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


__all__ = ["DEFAULT_MARKERS", "service_problems"]
