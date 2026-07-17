"""Shared adapters between the coder workflow's QA nodes and the in-process
``ostler`` QA API.

Each ``qa_*`` helper drives one ``ostler qa …`` operation through the ``Ostler``
Python API and normalizes it back to the ``(returncode, payload, stderr)`` shape the
routing scripts already branch on — so a node keeps its exact pass/invalid/blocked
logic while no longer shelling out. ``notes_for`` / ``emit`` render the workflow JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler import Ostler


def _okf(docs_root: Path | None = None) -> Ostler:
    return Ostler(docs_root) if docs_root is not None else Ostler()


def _parse_source_roots(source_roots: list[str]) -> dict[str, list[str]]:
    """``["SURFACE=PATH", …]`` → ``{surface: [path, …]}`` (the CLI's ``--source-root``)."""
    parsed: dict[str, list[str]] = {}
    for raw in source_roots:
        if isinstance(raw, str) and "=" in raw:
            surface, path = raw.split("=", 1)
            parsed.setdefault(surface.strip(), []).append(path.strip())
    return parsed


def qa_context(
    spec_dir: str,
    *,
    base: str,
    head: str,
    features_root: str,
    story_file: str,
    source_roots: list[str],
    docs_root: Path | None = None,
) -> tuple[int, dict[str, Any], str]:
    """``ostler qa context`` → the obligation packet; rc=1 on an error-level finding."""
    try:
        packet = _okf(docs_root).qa_context(
            base=base, head=head, spec=spec_dir,
            source_roots=_parse_source_roots(source_roots),
            features_root=features_root or "docs/features",
            story_file=story_file or None,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return 1, {}, str(exc)
    has_error = any(f.get("severity") == "error" for f in packet.get("healthFindings", []))
    return (1 if has_error else 0), packet, ""


def qa_context_validate(spec_dir: str, *, docs_root: Path | None = None) -> tuple[int, dict[str, Any], str]:
    """``ostler qa context-validate`` → ``{status, problems}``; rc=1 when problems exist."""
    try:
        problems = _okf(docs_root).qa_context_validate(spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid", "problems": [str(exc)]}, str(exc)
    payload = {"status": "passed" if not problems else "invalid", "problems": problems}
    return (0 if not problems else 1), payload, ""


def qa_validate(plan: str, spec_dir: str, *, docs_root: Path | None = None) -> tuple[int, dict[str, Any], str]:
    """``ostler qa validate`` → the outcome data; rc=0 iff the plan is valid."""
    try:
        outcome = _okf(docs_root).qa_validate(plan, spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid"}, str(exc)
    return (0 if outcome.ok else 1), outcome.data, "" if outcome.ok else outcome.message


def qa_run(plan: str, spec_dir: str, *, docs_root: Path | None = None) -> tuple[int, dict[str, Any], str]:
    """``ostler qa run`` → the four-state outcome data; rc=0 iff the run passed."""
    try:
        outcome = _okf(docs_root).qa_run(plan, spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid"}, str(exc)
    return (0 if outcome.ok else 1), outcome.data, "" if outcome.ok else outcome.message


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
