"""The one definition of "this service directory is real", shared by two callers.

``validate-plan-context.py`` enforces it as a **precondition** of the main loop: the planner
may not declare a service the workspace does not actually have. ``validate-genesis.py``
enforces the same thing as a **postcondition** of the ``genesis`` flow: whatever genesis just
created must be something the main loop will accept.

They are the same assertion viewed from two sides, so they share one implementation — if the
contract ever changes, genesis cannot drift into producing a repo the planner then rejects.
That drift is silent and only shows up as a confusing planner rejection several stages later.
"""
from __future__ import annotations

from pathlib import Path

# A scaffold seeds a folder and a .gitignore; only native init tooling (`go mod init`,
# `npm create react-router`, `flutter create`) produces these. Their presence is what
# distinguishes "a directory someone made" from "a service that exists".
DEFAULT_MARKERS = ("main.go", "go.mod", "package.json", "pubspec.yaml", "main.tf")


def service_problems(service_abs: Path, markers: list[str] | tuple[str, ...] | None,
                     label: str) -> list[str]:
    """Problems with ``service_abs`` as a service root — empty list when it is valid.

    ``markers`` is the repo's configured ``service_markers``; falsy means "not configured",
    in which case the marker check is skipped rather than guessed at (the main loop's
    long-standing behaviour, preserved here deliberately).
    """
    if not service_abs.exists():
        return [f"{label}: path does not exist at {service_abs}"]
    if not service_abs.is_dir():
        return [f"{label}: path is not a directory"]
    if markers and not any((service_abs / m).exists() for m in markers):
        return [f"{label}: no service marker found "
                f"(expected one of {list(markers)} in {service_abs})"]
    return []
