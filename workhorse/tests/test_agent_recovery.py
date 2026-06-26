"""Tests for run_agent's resilience ladder: transient retry → reframe → default.

The worker runs unattended for days, so a node Claude can't answer must never
crash the run. These tests patch _invoke_claude (no CLI, no real sleeping) and
assert the escalation order and the workflow-advancing fallback.

    ./.venv/bin/python tests/test_agent_recovery.py
    ./.venv/bin/python -m pytest tests/test_agent_recovery.py
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from workhorse.runner import agent
from workhorse.runner.agent import ClaudeInvocationError
from workhorse.graph.context import WorkflowContext
from workhorse.graph.nodes import AgentNode, OutputSpec


def _node() -> AgentNode:
    return AgentNode(
        type="agent",
        id="review_implementation",
        prompt="Review the work and decide.",
        # Declarative fallbacks: the workflow author says what's safe to emit when
        # this node can't be answered, so the generic runner needn't guess.
        outputs=[
            OutputSpec(key="decision", default="continue"),
            OutputSpec(key="review", default={"status": "auto_approved"}),
        ],
        next="next_node",
    )


def _run(node, **kw):
    # node.prompt is normally a template FILE path; render it inline for the test.
    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        return agent.run_agent(node, WorkflowContext(initial={}), Path("."), None, **kw)


def test_success_on_first_attempt_returns_outputs():
    payload = json.dumps({"decision": "approve", "review": "looks good"})
    with patch.object(agent, "_invoke_claude", lambda *a, **k: payload):
        _, outputs = _run(_node())
    assert outputs == {"decision": "approve", "review": "looks good"}


def test_empty_result_then_reframe_succeeds():
    """An empty result (the original 'No result event' bug) raises invoke error;
    the node is reframed and the next attempt succeeds — no crash."""
    calls = {"n": 0}
    good = json.dumps({"decision": "continue", "review": "ok"})

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # Mirrors _run_claude_cli when result text is empty.
            raise ClaudeInvocationError(
                "No 'result' event received from Claude for node 'review_implementation'",
                transient=True,
            )
        return good

    with patch.object(agent, "_invoke_claude", fake_invoke), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(_node())

    assert outputs == {"decision": "continue", "review": "ok"}
    assert calls["n"] == 2, "should reframe once then succeed"


def test_persistent_failure_defaults_to_next_node():
    """When every reframing fails, return safe defaults so the controller can
    advance to node.next instead of raising."""
    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise ClaudeInvocationError("No 'result' event received", transient=True)

    with patch.object(agent, "_invoke_claude", always_fail), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(_node(), max_rephrase_attempts=3)

    # Heuristic defaults keep the workflow moving.
    assert outputs["decision"] == "continue"
    assert outputs["review"]["status"] == "auto_approved"


def test_reframe_count_then_default():
    """Exactly max_rephrase_attempts+1 invocations before defaulting."""
    calls = {"n": 0}

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise ClaudeInvocationError("No 'result' event received", transient=True)

    with patch.object(agent, "_invoke_claude", always_fail), \
         patch.object(agent.time, "sleep", lambda s: None):
        _run(_node(), max_rephrase_attempts=2)

    assert calls["n"] == 3, "initial + 2 reframes, then default (no further invoke)"


def test_unparseable_output_reframes_then_defaults():
    """A node that always returns unparseable text exhausts output retries, then
    reframes, then defaults — never crashes."""
    def junk(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        return "I cannot produce JSON, sorry."

    with patch.object(agent, "_invoke_claude", junk), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(_node(), max_output_retries=1, max_rephrase_attempts=1)

    assert outputs["decision"] == "continue"


def test_default_outputs_use_declared_defaults_else_none():
    """The generic runner emits each output's declared default; an output with no
    declared default falls back to None (no key-name guessing)."""
    node = AgentNode(
        type="agent",
        id="n",
        prompt="do it",
        outputs=[OutputSpec(key="decision", default="continue"), OutputSpec(key="notes")],
        next="next_node",
    )

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise ClaudeInvocationError("No 'result' event received", transient=True)

    with patch.object(agent, "_invoke_claude", always_fail), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(node, max_rephrase_attempts=1)

    assert outputs == {"decision": "continue", "notes": None}


def test_new_node_starts_clean_dropping_prior_session(tmp_path=None):
    """A fresh node (resume_session=False) must NOT chain a previous node's
    session: the stale .session_id is dropped before the first invocation."""
    import tempfile
    sid_path = Path(tempfile.mkdtemp()) / ".session_id"
    sid_path.write_text("prev-node-session-abc")  # left by an earlier node

    good = json.dumps({"decision": "continue", "review": "ok"})
    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)), \
         patch.object(agent, "_invoke_claude", lambda *a, **k: good):
        agent.run_agent(_node(), WorkflowContext(initial={}), Path("."), sid_path)

    # The stub never re-wrote it, so a cleared file means "started clean".
    assert not sid_path.exists(), "new node should drop the prior node's session"


def test_interrupted_node_keeps_session_for_resume(tmp_path=None):
    """An interrupted node (resume_session=True) keeps its session so the CLI
    can --resume and continue where it left off."""
    import tempfile
    sid_path = Path(tempfile.mkdtemp()) / ".session_id"
    sid_path.write_text("this-node-session-xyz")

    good = json.dumps({"decision": "continue", "review": "ok"})
    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)), \
         patch.object(agent, "_invoke_claude", lambda *a, **k: good):
        agent.run_agent(
            _node(), WorkflowContext(initial={}), Path("."), sid_path,
            resume_session=True,
        )

    assert sid_path.exists() and sid_path.read_text() == "this-node-session-xyz", \
        "interrupted node must keep its session for --resume"


def test_context_overflow_is_detected():
    assert agent._is_context_overflow("API Error: prompt is too long: 200000 tokens > 200000") is True
    assert agent._is_context_overflow("the conversation is too long to continue") is True
    assert agent._is_context_overflow("rate limit") is False
    assert agent._is_context_overflow("spending cap reached") is False


def test_overflow_compacts_then_continues_same_prompt():
    """On context overflow the runner compacts the session and retries the SAME
    prompt (preserving progress) rather than reframing."""
    calls = {"n": 0}
    good = json.dumps({"decision": "approve", "review": "done"})

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClaudeInvocationError("Context window exhausted", overflow=True)
        # second invocation (after compaction) succeeds; must be the original prompt
        assert "reframe" not in prompt.lower() and "do your best" not in prompt.lower()
        return good

    compacted = {"n": 0}

    def fake_compact(session_id_path, node_id, model=None):
        compacted["n"] += 1
        return True  # compaction succeeded

    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)), \
         patch.object(agent, "_invoke_claude", fake_invoke), \
         patch.object(agent, "_compact_session", fake_compact), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(_node(), max_rephrase_attempts=2)

    assert outputs == {"decision": "approve", "review": "done"}
    assert compacted["n"] == 1, "should compact exactly once"
    assert calls["n"] == 2, "invoke, compact, then invoke again — no reframe"


def test_overflow_falls_back_to_reframe_when_compaction_fails():
    """If compaction can't help, the runner reframes (fresh session) then defaults."""
    def always_overflow(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise ClaudeInvocationError("prompt is too long", overflow=True)

    def failed_compact(session_id_path, node_id, model=None):
        return False  # /compact unavailable/ineffective

    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)), \
         patch.object(agent, "_invoke_claude", always_overflow), \
         patch.object(agent, "_compact_session", failed_compact), \
         patch.object(agent.time, "sleep", lambda s: None):
        _, outputs = _run(_node(), max_rephrase_attempts=1, max_compact_attempts=1)

    # Compaction failed → reframe exhausted → declared defaults.
    assert outputs["decision"] == "continue"


def test_overflow_compaction_attempts_are_bounded():
    """Compaction is tried at most max_compact_attempts times, then reframe."""
    compacted = {"n": 0}

    def always_overflow(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise ClaudeInvocationError("context window exceeded", overflow=True)

    def ok_compact(session_id_path, node_id, model=None):
        compacted["n"] += 1
        return True  # succeeds but the node keeps overflowing anyway

    with patch.object(agent, "render", lambda tmpl, ctx, wdir: str(tmpl)), \
         patch.object(agent, "_invoke_claude", always_overflow), \
         patch.object(agent, "_compact_session", ok_compact), \
         patch.object(agent.time, "sleep", lambda s: None):
        _run(_node(), max_rephrase_attempts=1, max_compact_attempts=2)

    assert compacted["n"] == 2, "compaction must be bounded by max_compact_attempts"


def test_default_outputs_disabled_raises():
    """With defaulting off, a persistently failing node raises for a hard stop."""
    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise ClaudeInvocationError("No 'result' event received", transient=True)

    with patch.object(agent, "_invoke_claude", always_fail), \
         patch.object(agent, "USE_DEFAULT_OUTPUTS", False), \
         patch.object(agent.time, "sleep", lambda s: None):
        try:
            _run(_node(), max_rephrase_attempts=1)
            raise AssertionError("expected raise when defaulting is disabled")
        except ClaudeInvocationError:
            pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
