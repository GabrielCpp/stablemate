"""Tests for the per-node wall-clock budget.

A node that must run a long command (e.g. a full benchmark) sets `timeout:` so its
turn isn't killed mid-run. The effective budget is also surfaced to the prompt as
`node_timeout_s` / `node_timeout_min` so the agent can size its work to fit.

    ./.venv/bin/python -m pytest tests/test_node_timeout.py
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from workhorse.runner import agent
from workhorse.graph.context import WorkflowContext
from workhorse.graph.nodes import AgentNode


def _node(timeout="__unset__") -> AgentNode:
    kw = {} if timeout == "__unset__" else {"timeout": timeout}
    return AgentNode(
        type="agent",
        id="implement",
        prompt="Do the work.",
        next="next_node",
        **kw,
    )


def _run_capturing(node):
    """Run the node, capturing the prompt-render ctx and the timeout that reaches
    the invocation layer. Returns (render_ctx, invoke_timeout)."""
    seen = {"ctx": None, "timeout": None}

    def fake_render(tmpl, ctx, wdir):
        seen["ctx"] = ctx
        return str(tmpl)

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        seen["timeout"] = timeout
        return json.dumps({})

    with patch.object(agent, "render", fake_render), \
         patch.object(agent, "_invoke_claude", fake_invoke):
        agent.run_agent(node, WorkflowContext(initial={}), Path("."), None)
    return seen["ctx"], seen["timeout"]


def test_timeout_defaults_to_1_hour():
    # The default per-node budget is 1 hour so benchmark-running nodes aren't killed.
    assert _node().timeout == 3600


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
    assert invoke_timeout == agent.DEFAULT_RESULT_TIMEOUT_S
    assert ctx["node_timeout_s"] == int(agent.DEFAULT_RESULT_TIMEOUT_S)


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
