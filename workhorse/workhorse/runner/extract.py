"""Recovering the node's declared outputs from an agent's free-form answer."""

from __future__ import annotations

import json
from typing import Any

from workhorse.runner.failure import OutputParseError
from workhorse.runner.spec import AgentNode

from json_repair import repair_json


def extract_outputs(text: str, node: AgentNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    declared = [o.key for o in node.outputs]
    wanted = [o.key for o in node.outputs if o.required] or declared
    parsed = parse_json_from_text(text, wanted)
    if parsed is None:
        raise OutputParseError(
            f"Node '{node.id}' declared outputs {declared} "
            f"but agent response contained no parseable JSON"
        )

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            if not spec.required:
                continue
            raise OutputParseError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in agent JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result


def parse_json_from_text(text: str, wanted_keys: list[str] | None = None) -> dict | None:
    """Extract the node's JSON object from an agent response."""
    wanted = set(wanted_keys or ())
    objects = _json_objects(text)
    for obj in objects:
        unwrapped = _unwrap(obj, wanted)
        if unwrapped is not None:
            return unwrapped

    tolerant = _parse_json_tolerant(text, wanted)
    if tolerant is not None:
        return tolerant

    return objects[0] if objects else None


def _unwrap(obj: dict, wanted: set[str]) -> dict | None:
    """``obj`` itself if it carries every wanted key, else the nested object that does."""
    if not wanted or wanted.issubset(obj):
        return obj
    queue = [v for v in obj.values() if isinstance(v, dict)]
    while queue:
        nxt: list[dict] = []
        for cand in queue:
            if wanted.issubset(cand):
                return cand
            nxt.extend(v for v in cand.values() if isinstance(v, dict))
        queue = nxt
    return None


def _json_objects(text: str) -> list[dict]:
    """Every syntactically-complete JSON object embedded in *text*, in source order."""
    decoder = json.JSONDecoder()
    found: list[dict] = []
    idx = 0
    while (idx := text.find("{", idx)) != -1:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except ValueError:
            idx += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
            idx = end
        else:
            idx += 1
    return found


def _parse_json_tolerant(text: str, wanted: set[str]) -> dict | None:
    """Repair-and-extract via ``json-repair``, preferring the object with the wanted keys."""
    try:
        obj = repair_json(text, return_objects=True)
    except Exception:  # noqa: BLE001 — repair is best-effort; never let it crash a run
        return None
    return _select_object(obj, wanted)


def _select_object(obj: Any, wanted: set[str]) -> dict | None:
    """Pick the best dict from json-repair output."""
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
        found = _unwrap(cand, wanted)
        if found is not None:
            return found
    return candidates[-1]
