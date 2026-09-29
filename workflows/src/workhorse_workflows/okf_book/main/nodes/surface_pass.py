"""The services one pass of the run routes: every one on the first pass, and those the operator's answer sends back after."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

PASS_NAME = "pass.json"
_SERVICES = TypeAdapter(tuple[str, ...])


def write_pass(run_dir: Path, services: tuple[str, ...]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / PASS_NAME).write_text(_SERVICES.dump_json(services).decode(), encoding="utf-8")


def read_pass(run_dir: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """The services of *services* the current pass routes. A run that has written no pass routes every one."""
    path = run_dir / PASS_NAME
    if not path.is_file():
        return services
    routed = set(_SERVICES.validate_json(path.read_text(encoding="utf-8")))
    return tuple(service for service in services if service in routed)
