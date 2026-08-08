"""Checkpoint projection supports current pyflow and retained graph runs."""
from __future__ import annotations

import json

from groom.checkpoints import CheckpointPosition, parse_position


def test_pyflow_position_uses_state_and_waiting_on() -> None:
    position = parse_position(
        json.dumps({"engine": "pyflow", "state": "write_story", "waiting_on": "/w/context.md"})
    )

    assert position == CheckpointPosition("write_story", "/w/context.md")


def test_retired_position_uses_current_id() -> None:
    assert parse_position('{"current_id":"plan"}') == CheckpointPosition("plan", "")


def test_malformed_or_wrongly_typed_position_is_empty() -> None:
    for text in ("not json", "[]", '{"engine":"pyflow","state":4,"waiting_on":[]}'):
        assert parse_position(text) == CheckpointPosition()
