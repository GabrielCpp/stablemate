"""Tests for the per-node wall-clock budget.

A node that must run a long command (e.g. a full benchmark) sets `timeout:` so its
turn isn't killed mid-run. The effective budget is also surfaced to the prompt as
`node_timeout_s` / `node_timeout_min` so the agent can size its work to fit.

    ./.venv/bin/python -m pytest tests/test_node_timeout.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import FakeBackend, FakeClock
from workhorse._vendor.stablemate_core.config import PowerMapping
from workhorse.config_run import AgentResilience
from workhorse.runner import ladder
from workhorse.context import WorkflowContext
from workhorse.runner.spec import AgentNode


def _node(timeout: float | str | None = "__unset__") -> AgentNode:
    kw: dict[str, Any] = {} if timeout == "__unset__" else {"timeout": timeout}
    return AgentNode(
        type="agent",
        id="implement",
        prompt="Do the work.",
        next="next_node",
        **kw,
    )


def _run_capturing(node, *, resilience: AgentResilience | None = None):
    """Run the node, capturing the prompt-render ctx and the timeout that reaches
    the invocation layer. Returns (render_ctx, invoke_timeout)."""
    seen: dict[str, Any] = {"ctx": None, "timeout": None}

    def fake_render(tmpl, ctx, wdir):
        seen["ctx"] = ctx
        return str(tmpl)

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        seen["timeout"] = timeout
        return json.dumps({})

    class ScriptedRunner(ladder.AgentRunner):
        def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
            return fake_invoke(prompt, node_id, session_id_path, model, **kwargs)

    with patch.object(ladder, "render", fake_render):
        ScriptedRunner(
            backend=FakeBackend(),
            clock=FakeClock(),
            resilience=resilience or AgentResilience(),
        ).run(node, WorkflowContext(initial={}), Path("."), None)
    return seen["ctx"], seen["timeout"]


def test_timeout_defaults_to_unset_and_resolves_to_1_hour():
    """The default budget is the *engine's*, not a literal on the node.

    It used to be a literal 3600 here, which made `resilience.result_timeout_s`
    unreachable for every node — the fallback was tested by the truthiness of a field
    that was never falsy. The observable budget is unchanged; what moved is where it
    comes from, which is what makes AGENT_RESULT_TIMEOUT_S mean anything.
    """
    assert _node().timeout is None

    _, invoke_timeout = _run_capturing(_node())

    assert invoke_timeout == 3600


def test_default_budget_threads_to_invocation_and_prompt():
    ctx, invoke_timeout = _run_capturing(_node())
    assert invoke_timeout == 3600
    assert ctx["node_timeout_s"] == 3600
    assert ctx["node_timeout_min"] == 60


def test_explicit_timeout_overrides_and_reaches_prompt():
    ctx, invoke_timeout = _run_capturing(_node(timeout=300))
    # An explicit per-node budget reaches the invocation layer (the CLI's wait)...
    assert invoke_timeout == 300
    # ...and is exposed to the prompt so the agent can size its commands.
    assert ctx["node_timeout_s"] == 300
    assert ctx["node_timeout_min"] == 5


def test_explicit_none_falls_back_to_engine_default():
    ctx, invoke_timeout = _run_capturing(_node(timeout=None))
    # The engine default now lives on the injected settings object, not on the module.
    default_s = AgentResilience().result_timeout_s
    assert invoke_timeout == default_s
    assert ctx["node_timeout_s"] == int(default_s)


def test_numeric_string_timeout_parses_to_seconds():
    # `timeout: 5000` (or "5000") is a plain seconds budget.
    assert _node(timeout="5000").timeout == 5000.0


def test_infinity_words_coerce_to_unbounded():
    for word in ("infinity", "inf", "INFINITE", "unbounded", "Never"):
        assert _node(timeout=word).timeout == float("inf")


def test_unbounded_timeout_threads_through_without_overflow():
    # The unbounded budget reaches the invocation layer as inf (the stream loop's
    # `elapsed > inf` is always False → never killed), and the prompt-surfaced budget
    # is the string "unbounded" rather than a crash on int(inf).
    ctx, invoke_timeout = _run_capturing(_node(timeout="infinity"))
    assert invoke_timeout == float("inf")
    assert ctx["node_timeout_s"] == "unbounded"
    assert ctx["node_timeout_min"] == "unbounded"


def test_the_engine_default_reaches_a_node_that_declares_no_timeout():
    """The regression that named the bug: AGENT_RESULT_TIMEOUT_S moved nothing.

    `AgentNode.timeout` defaulted to 3600 and the ladder tested it for truthiness, so
    the operator-settable engine default applied to exactly no node.
    """
    resilience = AgentResilience.from_env({"AGENT_RESULT_TIMEOUT_S": "7200"})

    ctx, invoke_timeout = _run_capturing(_node(), resilience=resilience)

    assert invoke_timeout == 7200
    assert ctx["node_timeout_s"] == 7200


# --- the power tier's wall-clock scale ---------------------------------------


def _scaled(scale: float | None):
    """Pin both power resolvers, so no test reads the developer's own config."""
    mapping = PowerMapping(timeout_scale=scale)
    return patch.multiple(
        ladder,
        resolve_power=lambda *a, **k: mapping,
        resolve_backend_default=lambda *a, **k: PowerMapping(),
    )


def test_an_unscaled_run_is_byte_identical():
    with _scaled(None):
        ctx, invoke_timeout = _run_capturing(_node(timeout=300))

    assert invoke_timeout == 300
    assert ctx["node_timeout_s"] == 300


def test_a_tier_scale_multiplies_the_node_budget_and_the_prompt():
    with _scaled(2.0):
        ctx, invoke_timeout = _run_capturing(_node(timeout=300))

    assert invoke_timeout == 600
    # The prompt must be told the budget it actually has: an agent sizing its commands
    # to an unscaled number is exactly the turn that gets killed at the wall.
    assert ctx["node_timeout_s"] == 600
    assert ctx["node_timeout_min"] == 10


def test_a_tier_scale_multiplies_the_engine_default_too():
    with _scaled(2.0):
        _, invoke_timeout = _run_capturing(_node())

    assert invoke_timeout == 7200


def test_an_unbounded_node_stays_unbounded_under_any_scale():
    with _scaled(3.0):
        ctx, invoke_timeout = _run_capturing(_node(timeout="infinity"))

    assert invoke_timeout == float("inf")
    assert ctx["node_timeout_s"] == "unbounded"


def test_the_tier_scale_beats_the_backend_default_scale():
    tier = PowerMapping(timeout_scale=2.0)
    default = PowerMapping(timeout_scale=5.0)
    with (
        patch.object(ladder, "resolve_power", lambda *a, **k: tier),
        patch.object(ladder, "resolve_backend_default", lambda *a, **k: default),
    ):
        _, invoke_timeout = _run_capturing(_node(timeout=300))

    assert invoke_timeout == 600


def test_the_backend_default_scale_applies_when_the_tier_omits_one():
    default = PowerMapping(timeout_scale=5.0)
    with (
        patch.object(ladder, "resolve_power", lambda *a, **k: PowerMapping()),
        patch.object(ladder, "resolve_backend_default", lambda *a, **k: default),
    ):
        _, invoke_timeout = _run_capturing(_node(timeout=300))

    assert invoke_timeout == 1500


if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
