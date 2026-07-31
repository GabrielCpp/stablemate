"""Recovering the node's declared outputs from an agent's free-form answer."""

from __future__ import annotations

import json
import re
from typing import Any

from workhorse.runner.failure import OutputParseError
from workhorse.runner.spec import AgentNode

try:
    from json_repair import repair_json as _repair_json
except ImportError:  # tolerant parsing degrades to strict-only if the dep is absent
    _repair_json = None


def extract_outputs(text: str, node: AgentNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    wanted = [o.key for o in node.outputs]
    parsed = parse_json_from_text(text, wanted)
    if parsed is None:
        raise OutputParseError(
            f"Node '{node.id}' declared outputs {wanted} "
            f"but agent response contained no parseable JSON"
        )

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            raise OutputParseError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in agent JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result


def parse_json_from_text(text: str, wanted_keys: list[str] | None = None) -> dict | None:
    """Extract the node's JSON object from an agent response.

    Strict first: a well-formed fenced or bare JSON object that already carries
    the declared output keys is parsed with the stdlib and returned unchanged —
    no coercion, so genuinely-malformed output still trips the retry/reframe
    ladder when strict parsing would have been enough.

    Only when strict parsing fails to yield an object containing the wanted keys
    do we fall back to the tolerant ``json-repair`` pass, which fixes trailing
    commas, single quotes, comments, and truncated/unclosed braces, and can
    return several candidate objects when the response embeds more than one (an
    example plus the real answer, say) — in which case we prefer the object that
    carries the declared output keys.
    """
    wanted = set(wanted_keys or ())
    strict = _parse_json_strict(text)
    if strict is not None and wanted.issubset(strict):
        return strict

    tolerant = _parse_json_tolerant(text, wanted)
    if tolerant is not None:
        return tolerant

    # Best strict effort (a dict missing some keys, or None) so the caller can
    # raise the precise "key not found" / "no parseable JSON" error.
    return strict


def _parse_json_strict(text: str) -> dict | None:
    """Stdlib-only extraction: fenced ```json block, then first/last brace span."""
    # Try fenced code block first
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try first top-level JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _parse_json_tolerant(text: str, wanted: set[str]) -> dict | None:
    """Repair-and-extract via ``json-repair``, preferring the object with the
    wanted keys. Returns None if the dep is absent or no dict could be recovered."""
    if _repair_json is None:
        return None
    try:
        obj = _repair_json(text, return_objects=True)
    except Exception:  # noqa: BLE001 — repair is best-effort; never let it crash a run
        return None
    return _select_object(obj, wanted)


def _select_object(obj: Any, wanted: set[str]) -> dict | None:
    """Pick the best dict from json-repair output.

    json-repair returns a dict for a single object, a list when the response
    embedded several, and ``''`` / other scalars when nothing JSON-like was
    found. Prefer the last dict (the final answer usually comes last) that
    carries every wanted key; else the last dict seen; else None.
    """
    candidates: list[dict] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            candidates.append(o)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(obj)
    if not candidates:
        return None
    for cand in reversed(candidates):
        if wanted.issubset(cand):
            return cand
    return candidates[-1]
