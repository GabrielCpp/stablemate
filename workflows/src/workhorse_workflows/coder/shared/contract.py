"""What makes a service real to the planner — one assertion, two callers."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

def service_problems(service_abs: Path, markers: Sequence[str], label: str) -> list[str]:
    """Every reason `service_abs` is not a service the planner can target, or `[]`."""
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
