"""Every claude turn states the window it compacts at, and a power tier can change it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import FakeBackend, FakeClock, claude_cmd
from workhorse import profile
from workhorse._vendor.stablemate_core.profiles import PowerMapping
from workhorse.config_run import AgentResilience
from workhorse.context import WorkflowContext
from workhorse.runner import ladder
from workhorse.runner.spec import AgentNode


def _value_after(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def test_a_bare_claude_turn_states_the_default_window():
    assert _value_after(claude_cmd(), "--autocompact") == "400000"


def test_a_window_of_auto_is_passed_as_auto():
    assert _value_after(claude_cmd(compact_window="auto"), "--autocompact") == "auto"


def test_a_given_window_is_passed_as_a_number():
    assert _value_after(claude_cmd(compact_window=250000), "--autocompact") == "250000"


def _node() -> AgentNode:
    return AgentNode(type="agent", id="implement", prompt="Do the work.", next="next_node", power="high")


def _seen_window(mapped: PowerMapping, default: PowerMapping) -> Any:
    seen: dict[str, Any] = {}

    def fake_turn(prompt, node_id, session_id_path, model=None, **kwargs):
        seen.update(kwargs)
        return json.dumps({})

    with (
        patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)),
        patch.multiple(
            profile,
            resolve_power=lambda *a, **k: mapped,
            resolve_backend_default=lambda *a, **k: default,
        ),
    ):
        ladder.AgentRunner(
            backend=FakeBackend(turn=fake_turn),
            clock=FakeClock(),
            resilience=AgentResilience(),
        ).run(_node(), WorkflowContext(initial={}), Path("."), None)
    return seen["compact_window"]


def test_a_tier_window_reaches_the_backend_turn():
    assert _seen_window(PowerMapping(compact_window=500000), PowerMapping()) == 500000


def test_a_tier_window_beats_the_profile_default():
    assert _seen_window(PowerMapping(compact_window=500000), PowerMapping(compact_window=200000)) == 500000


def test_the_profile_default_applies_when_the_tier_names_none():
    assert _seen_window(PowerMapping(), PowerMapping(compact_window=200000)) == 200000


def test_no_window_anywhere_leaves_the_backend_to_choose():
    assert _seen_window(PowerMapping(), PowerMapping()) is None
