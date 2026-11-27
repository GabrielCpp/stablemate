from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol


class _Requester(Protocol):
    serial: str

    def request(self, method: str, params: Mapping[str, Any], deadline: float) -> Mapping[str, Any]: ...


def _expand_schema_node(
    raw: Mapping[str, Any],
    abbreviations: Mapping[str, str],
    defaults: Mapping[str, Any],
) -> dict[str, Any]:
    merged = {**defaults, **raw}
    children_raw = merged.pop("c", None)
    if children_raw is None:
        children_raw = merged.pop("children", None) or []
    else:
        merged.pop("children", None)
    pairs: dict[str, str] = {}
    for key, value in merged.items():
        full = abbreviations.get(key, key)
        if isinstance(value, bool):
            pairs[full] = "true" if value else "false"
        elif value is not None:
            pairs[full] = str(value)
    if pairs.get("content-desc") and not pairs.get("accessibilityText"):
        pairs["accessibilityText"] = pairs["content-desc"]
    return {
        "attributes": pairs,
        "children": [
            _expand_schema_node(child, abbreviations, defaults)
            for child in children_raw
            if isinstance(child, Mapping)
        ],
    }


def schema_to_hierarchy(text: str) -> str | None:
    for line in text.splitlines():
        start = line.find("{")
        if start < 0 or '"ui_schema"' not in line:
            continue
        try:
            payload = json.loads(line[start:])
        except ValueError:
            continue
        if not isinstance(payload, Mapping) or "ui_schema" not in payload:
            continue
        schema = payload.get("ui_schema") or {}
        abbreviations = schema.get("abbreviations") or {}
        defaults = schema.get("defaults") or {}
        elements = payload.get("elements") or []
        return json.dumps({
            "attributes": {},
            "children": [
                _expand_schema_node(item, abbreviations, defaults)
                for item in elements
                if isinstance(item, Mapping)
            ],
        })
    return None


def call_hierarchy_tool(
    session: _Requester,
    tool: str,
    deadline: float,
    parse_reply: Callable[[Mapping[str, Any]], str],
) -> tuple[str, str]:
    reply = session.request(
        "tools/call",
        {"name": tool, "arguments": {"device_id": session.serial}},
        deadline,
    )
    try:
        return tool, parse_reply(reply)
    except RuntimeError as exc:
        if tool == "inspect_view_hierarchy" and "inspect_view_hierarchy not found" in str(exc):
            fallback = "inspect_screen"
            second = session.request(
                "tools/call",
                {"name": fallback, "arguments": {"device_id": session.serial}},
                deadline,
            )
            return fallback, parse_reply(second)
        raise
