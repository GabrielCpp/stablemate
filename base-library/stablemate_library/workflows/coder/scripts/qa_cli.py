"""Shared JSON normalization for the coder workflow's thin Ostler QA adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse import scriptutil


def run_ostler(
    args: list[str], *, cwd: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """Run Ostler without raising and parse its JSON object when possible."""
    try:
        result = scriptutil.run_tool(["ostler", *args], cwd=cwd)
    except OSError as exc:
        return 127, {}, str(exc)

    payload: dict[str, Any] = {}
    stdout = result.stdout.strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            pass
    return result.returncode, payload, result.stderr.strip()


def notes_for(payload: dict[str, Any], stderr: str, fallback: str) -> str:
    """Extract concise routing notes while retaining deterministic diagnostics."""
    for key in ("notes", "message", "problems", "errors", "healthFindings"):
        value = payload.get(key)
        if value:
            if isinstance(value, str):
                return value
            return json.dumps(value, sort_keys=True)
    return stderr or fallback


def emit(key: str, status: str, notes: str, payload: dict[str, Any]) -> None:
    print(json.dumps({key: {"status": status, "notes": notes, "ostler": payload}}))
