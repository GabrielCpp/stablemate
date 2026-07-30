"""The coder's adapter onto ostler's QA API — the port of `scripts/qa_cli.py`.

Each helper drives one `ostler qa …` operation through the `Ostler` Python API and
normalizes it to the `(returncode, payload, stderr)` triple the calling nodes branch on.
The triple is kept rather than typed away: it is what an API reporting *ok / data / message*
actually yields, and the four callers each turn it into a different status by a different
rule. Typing it here would mean picking one of those rules and pushing the other three into
`if`s anyway.

Two things the script did are gone. `emit()` printed the workflow's JSON envelope, which a
node returns as a model instead; and `fresh_import("qa_cli", also_purge=("ostler",))` — the
YAML engine's way of getting a fresh `ostler` into a subprocess per node — is a plain import
now, because nodes run in the engine's process and there is nothing to purge.

Library code, not nodes: `qa_context` and `qa_context_validate` back `nodes/okf.py`, which
`docs` and `qa` share.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler import Ostler


def okf(docs_root: Path | None = None) -> Ostler:
    """An `Ostler` rooted at `docs_root`, or one that discovers its own root."""
    return Ostler(docs_root) if docs_root is not None else Ostler()


def parse_source_roots(source_roots: list[str]) -> dict[str, list[str]]:
    """`["SURFACE=PATH", …]` → `{surface: [path, …]}` (the CLI's `--source-root`)."""
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
    """`ostler qa context` → the obligation packet; rc=1 on an error-level finding."""
    try:
        packet = okf(docs_root).qa_context(
            base=base,
            head=head,
            spec=spec_dir,
            source_roots=parse_source_roots(source_roots),
            features_root=features_root or "docs/features",
            story_file=story_file or None,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return 1, {}, str(exc)
    has_error = any(f.get("severity") == "error" for f in packet.get("healthFindings", []))
    return (1 if has_error else 0), packet, ""


def qa_context_validate(
    spec_dir: str, *, docs_root: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa context-validate` → `{status, problems}`; rc=1 when problems exist."""
    try:
        problems = okf(docs_root).qa_context_validate(spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid", "problems": [str(exc)]}, str(exc)
    payload = {"status": "passed" if not problems else "invalid", "problems": problems}
    return (0 if not problems else 1), payload, ""


def notes_for(payload: dict[str, Any], stderr: str, fallback: str) -> str:
    """Concise routing notes off the packet, keeping the deterministic diagnostics."""
    for key in ("notes", "message", "problems", "errors", "healthFindings"):
        value = payload.get(key)
        if value:
            if isinstance(value, str):
                return value
            return json.dumps(value, sort_keys=True)
    return stderr or fallback


__all__ = ["notes_for", "okf", "parse_source_roots", "qa_context", "qa_context_validate"]
