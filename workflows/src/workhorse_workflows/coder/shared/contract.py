"""What makes a service real to the planner — one assertion, two callers."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path


def normalize_service_path(path: object) -> str:
    """A service's repo-relative path in one spelling: no slashes at the ends, `.` for the root."""
    text = str(path or "").strip().strip("/")
    return text or "."


def declared_service_paths(services: object) -> list[str]:
    """The paths a repo's `services:` block declares, or `[]` while no entry declares a `path`; an entry with no `path` is at the root."""
    if not isinstance(services, Mapping):
        return []
    if not any(isinstance(entry, Mapping) and "path" in entry for entry in services.values()):
        return []
    return [
        normalize_service_path(entry.get("path") if isinstance(entry, Mapping) else "")
        for entry in services.values()
    ]


def service_problems(
    service_abs: Path, label: str, path: str = "", declared: Iterable[str] = ()
) -> list[str]:
    """Every reason `service_abs` is not a service the planner can target, or `[]`."""
    if not service_abs.exists():
        return [f"{label}: path does not exist at {service_abs}"]
    if not service_abs.is_dir():
        return [f"{label}: path is not a directory"]
    paths = list(declared)
    if paths and normalize_service_path(path) not in paths:
        return [
            f"{label}: path is not declared under `services:` in agents.yml "
            f"(declared: {sorted(set(paths))})"
        ]
    return []


__all__ = ["declared_service_paths", "normalize_service_path", "service_problems"]
