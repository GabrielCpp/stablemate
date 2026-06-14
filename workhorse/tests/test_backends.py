"""Tests for the agent-CLI backend facade (runner/backends.py).

Verifies per-run selection (AGENT_CLI / explicit name), the default backend, the
fail-fast on an unknown name, and that AgentNode.model is now optional (the
backend supplies the default). Runnable two ways:

    ./.venv/bin/python tests/test_backends.py
    ./.venv/bin/python -m pytest tests/test_backends.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from workhorse.runner import agent, backends
from workhorse.runner.backends import (
    AgentBackend,
    ClaudeBackend,
    CodexBackend,
    CopilotBackend,
    get_backend,
)
from workhorse.graph.nodes import AgentNode


def _without_agent_cli():
    """Context-free helper: clear AGENT_CLI, return its prior value to restore."""
    prior = os.environ.pop("AGENT_CLI", None)
    return prior


def test_default_backend_is_claude():
    prior = _without_agent_cli()
    try:
        b = get_backend()
        assert isinstance(b, ClaudeBackend)
        assert isinstance(b, AgentBackend)
        assert b.name == "claude"
        assert b.default_model == "sonnet"
        assert b.supports_compaction is True
    finally:
        if prior is not None:
            os.environ["AGENT_CLI"] = prior


def test_env_var_selects_backend():
    prior = os.environ.get("AGENT_CLI")
    os.environ["AGENT_CLI"] = "claude"
    try:
        assert isinstance(get_backend(), ClaudeBackend)
    finally:
        if prior is None:
            os.environ.pop("AGENT_CLI", None)
        else:
            os.environ["AGENT_CLI"] = prior


def test_explicit_name_overrides_env():
    prior = os.environ.get("AGENT_CLI")
    os.environ["AGENT_CLI"] = "bogus"  # would fail if env were consulted
    try:
        assert get_backend("claude").name == "claude"
    finally:
        if prior is None:
            os.environ.pop("AGENT_CLI", None)
        else:
            os.environ["AGENT_CLI"] = prior


def test_unknown_backend_raises():
    try:
        get_backend("does-not-exist")
        raise AssertionError("expected ValueError for an unknown backend name")
    except ValueError as e:
        assert "does-not-exist" in str(e)


def test_get_backend_caches_instance():
    assert get_backend("claude") is get_backend("claude")


def test_codex_and_copilot_registered():
    for name, cls in (("codex", CodexBackend), ("copilot", CopilotBackend)):
        b = get_backend(name)
        assert isinstance(b, cls)
        assert b.name == name
        assert b.default_model is None
        assert b.supports_compaction is False  # neither compacts in place


def _fake_stream(canned):
    """Return a _stream_jsonl stand-in that records the cmd/stdin and returns canned
    (state, diagnostics, timed_out, returncode)."""
    captured = {}

    def fake(cmd, node_id, timeout, stdin_data, on_event):
        captured["cmd"] = cmd
        captured["stdin"] = stdin_data
        return canned

    return fake, captured


def test_codex_effort_sets_reasoning_override():
    """`effort` maps to a `-c model_reasoning_effort="<level>"` config override."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "OK", "session_id": "t"}, "", False, 0))
    prior = os.environ.pop("CODEX_PROFILE", None)
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            CodexBackend().run_turn("P", "n", sidp, model="@gpt-5.5", effort="high")
    finally:
        if prior is not None:
            os.environ["CODEX_PROFILE"] = prior
    cmd = captured["cmd"]
    assert cmd[cmd.index("-c") + 1] == 'model_reasoning_effort="high"'


def test_codex_effort_clamped_to_high():
    """Codex tops out at "high"; the Claude-superset levels clamp down."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    for level in ("xhigh", "max"):
        fake, captured = _fake_stream(({"result_text": "OK", "session_id": "t"}, "", False, 0))
        prior = os.environ.pop("CODEX_PROFILE", None)
        try:
            with patch.object(backends, "_stream_jsonl", fake):
                CodexBackend().run_turn("P", "n", sidp, model="@gpt-5.5", effort=level)
        finally:
            if prior is not None:
                os.environ["CODEX_PROFILE"] = prior
        cmd = captured["cmd"]
        assert cmd[cmd.index("-c") + 1] == 'model_reasoning_effort="high"'


def test_codex_no_effort_omits_override():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "OK", "session_id": "t"}, "", False, 0))
    prior = os.environ.pop("CODEX_PROFILE", None)
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            CodexBackend().run_turn("P", "n", sidp, model="@gpt-5.5")
    finally:
        if prior is not None:
            os.environ["CODEX_PROFILE"] = prior
    assert "model_reasoning_effort" not in " ".join(captured["cmd"])


def _capture_claude_cmd(**run_turn_kwargs):
    """Run ClaudeBackend.run_turn with subprocess.Popen stubbed to capture the argv
    and short-circuit (the cmd is assembled before Popen is called)."""
    captured = {}

    class _Boom(Exception):
        pass

    def fake_popen(cmd, *a, **k):
        captured["cmd"] = cmd
        raise _Boom()

    with patch("subprocess.Popen", fake_popen):
        try:
            ClaudeBackend().run_turn("P", "n", None, **run_turn_kwargs)
        except Exception:
            pass
    return captured["cmd"]


def test_claude_effort_maps_to_native_flag():
    """`effort` becomes a native `--effort <level>` flag on the claude CLI (no prompt
    mutation), for every supported level."""
    for level in ("low", "medium", "high", "xhigh", "max"):
        cmd = _capture_claude_cmd(model="opus", effort=level)
        assert cmd[cmd.index("--effort") + 1] == level
        assert cmd[cmd.index("--model") + 1] == "opus"


def test_claude_no_effort_omits_flag():
    cmd = _capture_claude_cmd(model="opus")
    assert "--effort" not in cmd


def test_copilot_effort_maps_to_native_flag():
    """Copilot has a native `--effort <level>` flag; the prompt is passed verbatim."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "OK", "session_id": "s"}, "", False, 0))
    with patch.object(backends, "_stream_jsonl", fake):
        CopilotBackend().run_turn("BASE PROMPT", "n", sidp, effort="high")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "BASE PROMPT" in cmd and "ultrathink" not in " ".join(cmd)


def test_codex_run_turn_fresh_then_resume():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "OK", "session_id": "tid-123"}, "", False, 0))

    prior = os.environ.pop("CODEX_PROFILE", None)  # no profile → bare `codex exec`
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            # Leading '@' = model only, no profile (default provider).
            out = CodexBackend().run_turn("PROMPT", "n", sidp, model="@gpt-5.5")
    finally:
        if prior is not None:
            os.environ["CODEX_PROFILE"] = prior

    assert out == "OK"
    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--profile" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-m") + 1] == "gpt-5.5"
    assert "resume" not in captured["cmd"]
    assert captured["cmd"][-1] == "-" and captured["stdin"] == "PROMPT"
    assert "--dangerously-bypass-approvals-and-sandbox" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-m") + 1] == "gpt-5.5"
    assert sidp.read_text() == "tid-123"  # session persisted for resume

    # Second call resumes by the persisted id.
    fake2, captured2 = _fake_stream(({"result_text": "OK2", "session_id": "tid-123"}, "", False, 0))
    with patch.object(backends, "_stream_jsonl", fake2):
        CodexBackend().run_turn("P2", "n", sidp)
    assert captured2["cmd"][:3] == ["codex", "exec", "resume"]
    assert "tid-123" in captured2["cmd"]


def test_codex_profile_from_env():
    """CODEX_PROFILE is the run-level *fallback*: when a node names no profile, it
    injects a top-level `--profile <name>` (before `exec`); a leading-'@' model
    still maps to `-m`, overriding the profile's pinned model."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "OK", "session_id": "t1"}, "", False, 0))

    prior = os.environ.get("CODEX_PROFILE")
    os.environ["CODEX_PROFILE"] = "openrouter"
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            # '@slug' = model only; profile comes from the CODEX_PROFILE fallback.
            CodexBackend().run_turn("PROMPT", "n", sidp, model="@deepseek/deepseek-chat-v3.1")
    finally:
        if prior is None:
            os.environ.pop("CODEX_PROFILE", None)
        else:
            os.environ["CODEX_PROFILE"] = prior

    cmd = captured["cmd"]
    # --profile must precede `exec` (it's a top-level flag).
    assert cmd[:4] == ["codex", "--profile", "openrouter", "exec"]
    assert cmd[cmd.index("-m") + 1] == "deepseek/deepseek-chat-v3.1"
    # Resume also carries the top-level profile ahead of `exec resume`.
    fake2, captured2 = _fake_stream(({"result_text": "OK2", "session_id": "t1"}, "", False, 0))
    os.environ["CODEX_PROFILE"] = "openrouter"
    try:
        with patch.object(backends, "_stream_jsonl", fake2):
            CodexBackend().run_turn("P2", "n", sidp)
    finally:
        if prior is None:
            os.environ.pop("CODEX_PROFILE", None)
        else:
            os.environ["CODEX_PROFILE"] = prior
    assert captured2["cmd"][:5] == ["codex", "--profile", "openrouter", "exec", "resume"]


def test_codex_per_node_profile_overrides_env():
    """A node's `<profile>@<slug>` beats the CODEX_PROFILE fallback; a bare token is
    a profile name (model comes from the profile, so no `-m`)."""
    prior = os.environ.get("CODEX_PROFILE")
    os.environ["CODEX_PROFILE"] = "openrouter"  # run default the node should override
    try:
        sidp = Path(tempfile.mkdtemp()) / ".s"
        fake, captured = _fake_stream(({"result_text": "X", "session_id": "s"}, "", False, 0))
        with patch.object(backends, "_stream_jsonl", fake):
            CodexBackend().run_turn("P", "n", sidp, model="local@qwen2.5-coder:32b")
        cmd = captured["cmd"]
        assert cmd[:4] == ["codex", "--profile", "local", "exec"]  # node profile wins
        assert cmd[cmd.index("-m") + 1] == "qwen2.5-coder:32b"

        sidp2 = Path(tempfile.mkdtemp()) / ".s"
        fake2, captured2 = _fake_stream(({"result_text": "X", "session_id": "s"}, "", False, 0))
        with patch.object(backends, "_stream_jsonl", fake2):
            CodexBackend().run_turn("P", "n", sidp2, model="local")  # bare = profile
        assert captured2["cmd"][:4] == ["codex", "--profile", "local", "exec"]
        assert "-m" not in captured2["cmd"]  # model pinned by the profile
    finally:
        if prior is None:
            os.environ.pop("CODEX_PROFILE", None)
        else:
            os.environ["CODEX_PROFILE"] = prior


def test_parse_codex_model():
    assert backends._parse_codex_model(None) == (None, None)
    assert backends._parse_codex_model("") == (None, None)
    assert backends._parse_codex_model("local") == ("local", None)
    assert backends._parse_codex_model("openrouter@deepseek/x-v3.1") == ("openrouter", "deepseek/x-v3.1")
    assert backends._parse_codex_model("openrouter@") == ("openrouter", None)
    assert backends._parse_codex_model("@gpt-5.5") == (None, "gpt-5.5")


def test_copilot_run_turn_fresh_then_resume():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(({"result_text": "ANSWER", "session_id": "sess-1"}, "", False, 0))

    with patch.object(backends, "_stream_jsonl", fake):
        out = CopilotBackend().run_turn("PROMPT", "n", sidp)

    assert out == "ANSWER"
    cmd = captured["cmd"]
    assert cmd[0] == "copilot" and "-p" in cmd and "PROMPT" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert "--allow-all-tools" in cmd and "--no-ask-user" in cmd
    assert "--session-id" not in cmd  # fresh run: no resume yet
    assert sidp.read_text() == "sess-1"

    fake2, captured2 = _fake_stream(({"result_text": "A2", "session_id": "sess-1"}, "", False, 0))
    with patch.object(backends, "_stream_jsonl", fake2):
        CopilotBackend().run_turn("P2", "n", sidp)
    assert captured2["cmd"][captured2["cmd"].index("--session-id") + 1] == "sess-1"


def test_codex_on_event_extracts_text_and_session():
    state = {"result_text": "", "session_id": None}
    diag: list[str] = []
    backends._codex_on_event({"type": "thread.started", "thread_id": "abc"}, state, "n", diag)
    backends._codex_on_event(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}, state, "n", diag
    )
    assert state["session_id"] == "abc"
    assert state["result_text"] == "hi"


def test_copilot_on_event_extracts_text_and_session():
    state = {"result_text": "", "session_id": None}
    diag: list[str] = []
    backends._copilot_on_event(
        {"type": "assistant.message", "data": {"content": "hello"}}, state, "n", diag
    )
    backends._copilot_on_event(
        {"type": "result", "sessionId": "s9", "exitCode": 0}, state, "n", diag
    )
    assert state["result_text"] == "hello"
    assert state["session_id"] == "s9"


def test_finalize_turn_classifies_failures():
    base = {"result_text": "x", "session_id": None}
    # Non-zero exit whose output matches a transient marker → transient.
    try:
        backends._finalize_turn("codex", "n", dict(base), "rate limit hit", False, 1, None)
        raise AssertionError("expected raise on non-zero exit")
    except agent.BackendInvocationError as e:
        assert e.transient is True
    # Timeout is always transient.
    try:
        backends._finalize_turn("copilot", "n", dict(base), "", True, 0, None)
        raise AssertionError("expected raise on timeout")
    except agent.BackendInvocationError as e:
        assert e.transient is True
    # Empty result is transient.
    try:
        backends._finalize_turn("codex", "n", {"result_text": "", "session_id": None}, "", False, 0, None)
        raise AssertionError("expected raise on empty result")
    except agent.BackendInvocationError as e:
        assert e.transient is True
    # Clean success returns the text.
    assert backends._finalize_turn("codex", "n", dict(base), "", False, 0, None) == "x"


def test_agentnode_model_is_optional():
    """A node may omit `model:`; the backend default fills in at run time."""
    node = AgentNode(type="agent", id="n", prompt="do it", next="done")
    assert node.model is None
    # An explicit model is preserved unchanged.
    node2 = AgentNode(type="agent", id="n2", prompt="p", model="opus", next="done")
    assert node2.model == "opus"


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
