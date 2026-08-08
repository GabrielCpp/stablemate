"""Tolerant projection of Workhorse checkpoint position for dashboard consumers."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckpointPosition:
    current_node: str = ""
    waiting_on: str = ""


def parse_position(text: str) -> CheckpointPosition:
    """Read pyflow and retired checkpoint positions without raising."""
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return CheckpointPosition()
    if not isinstance(payload, dict):
        return CheckpointPosition()
    current = payload.get("state") if payload.get("engine") == "pyflow" else payload.get("current_id")
    waiting = payload.get("waiting_on") if payload.get("engine") == "pyflow" else ""
    return CheckpointPosition(
        current_node=current if isinstance(current, str) else "",
        waiting_on=waiting if isinstance(waiting, str) else "",
    )
