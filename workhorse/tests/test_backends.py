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
    AiderBackend,
    ClaudeBackend,
    CodexBackend,
    CopilotBackend,
    OpenCodeBackend,
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


def test_non_claude_backends_registered():
    # codex, copilot, aider, opencode: all stateless, no in-place compaction, and
    # no built-in default model (the node/AGENT_MODEL names it).
    for name, cls in (
        ("codex", CodexBackend),
        ("copilot", CopilotBackend),
        ("aider", AiderBackend),
        ("opencode", OpenCodeBackend),
    ):
        b = get_backend(name)
        assert isinstance(b, cls)
        assert b.name == name
        assert b.default_model is None
        assert b.supports_compaction is False  # none compact in place


def _fake_stream(canned):
    """Return a _stream_jsonl stand-in that records the cmd/stdin/cwd and returns canned
    (state, diagnostics, timed_out, returncode)."""
    captured = {}

    def fake(cmd, node_id, timeout, stdin_data, on_event, cwd=None):
        captured["cmd"] = cmd
        captured["stdin"] = stdin_data
        captured["cwd"] = cwd
        return canned

    return fake, captured


def test_codex_effort_sets_reasoning_override():
    """`effort` maps to a `-c model_reasoning_effort="<level>"` config override."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "t"}, "", False, 0)
    )
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
        fake, captured = _fake_stream(
            ({"result_text": "OK", "session_id": "t"}, "", False, 0)
        )
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
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "t"}, "", False, 0)
    )
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
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "s"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake):
        CopilotBackend().run_turn("BASE PROMPT", "n", sidp, effort="high")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "BASE PROMPT" in cmd and "ultrathink" not in " ".join(cmd)


def test_codex_run_turn_fresh_then_resume():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "tid-123"}, "", False, 0)
    )

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
    fake2, captured2 = _fake_stream(
        ({"result_text": "OK2", "session_id": "tid-123"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake2):
        CodexBackend().run_turn("P2", "n", sidp)
    assert captured2["cmd"][:3] == ["codex", "exec", "resume"]
    assert "tid-123" in captured2["cmd"]


def test_codex_profile_from_env():
    """CODEX_PROFILE is the run-level *fallback*: when a node names no profile, it
    injects a top-level `--profile <name>` (before `exec`); a leading-'@' model
    still maps to `-m`, overriding the profile's pinned model."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "t1"}, "", False, 0)
    )

    prior = os.environ.get("CODEX_PROFILE")
    os.environ["CODEX_PROFILE"] = "openrouter"
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            # '@slug' = model only; profile comes from the CODEX_PROFILE fallback.
            CodexBackend().run_turn(
                "PROMPT", "n", sidp, model="@deepseek/deepseek-chat-v3.1"
            )
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
    fake2, captured2 = _fake_stream(
        ({"result_text": "OK2", "session_id": "t1"}, "", False, 0)
    )
    os.environ["CODEX_PROFILE"] = "openrouter"
    try:
        with patch.object(backends, "_stream_jsonl", fake2):
            CodexBackend().run_turn("P2", "n", sidp)
    finally:
        if prior is None:
            os.environ.pop("CODEX_PROFILE", None)
        else:
            os.environ["CODEX_PROFILE"] = prior
    assert captured2["cmd"][:5] == [
        "codex",
        "--profile",
        "openrouter",
        "exec",
        "resume",
    ]


def test_codex_per_node_profile_overrides_env():
    """A node's `<profile>@<slug>` beats the CODEX_PROFILE fallback; a bare token is
    a profile name (model comes from the profile, so no `-m`)."""
    prior = os.environ.get("CODEX_PROFILE")
    os.environ["CODEX_PROFILE"] = "openrouter"  # run default the node should override
    try:
        sidp = Path(tempfile.mkdtemp()) / ".s"
        fake, captured = _fake_stream(
            ({"result_text": "X", "session_id": "s"}, "", False, 0)
        )
        with patch.object(backends, "_stream_jsonl", fake):
            CodexBackend().run_turn("P", "n", sidp, model="local@qwen2.5-coder:32b")
        cmd = captured["cmd"]
        assert cmd[:4] == ["codex", "--profile", "local", "exec"]  # node profile wins
        assert cmd[cmd.index("-m") + 1] == "qwen2.5-coder:32b"

        sidp2 = Path(tempfile.mkdtemp()) / ".s"
        fake2, captured2 = _fake_stream(
            ({"result_text": "X", "session_id": "s"}, "", False, 0)
        )
        with patch.object(backends, "_stream_jsonl", fake2):
            CodexBackend().run_turn("P", "n", sidp2, model="local")  # bare = profile
        assert captured2["cmd"][:4] == ["codex", "--profile", "local", "exec"]
        assert "-m" not in captured2["cmd"]  # model pinned by the profile
    finally:
        if prior is None:
            os.environ.pop("CODEX_PROFILE", None)
        else:
            os.environ["CODEX_PROFILE"] = prior


def test_codex_profile_at_slug_model_string():
    """A `<profile>@<slug>` codex model string drives the CLI as
    `codex --profile mimo exec ... -m mimo-pro` — the codex config profile selects
    the provider/auth bundle, the slug overrides its pinned model."""
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "OK", "session_id": "t"}, "", False, 0)
    )
    prior = os.environ.pop("CODEX_PROFILE", None)
    try:
        with patch.object(backends, "_stream_jsonl", fake):
            CodexBackend().run_turn("P", "n", sidp, model="mimo@mimo-pro")
    finally:
        if prior is not None:
            os.environ["CODEX_PROFILE"] = prior
    cmd = captured["cmd"]
    assert cmd[:4] == ["codex", "--profile", "mimo", "exec"]
    assert cmd[cmd.index("-m") + 1] == "mimo-pro"


def test_parse_codex_model():
    assert backends._parse_codex_model(None) == (None, None)
    assert backends._parse_codex_model("") == (None, None)
    assert backends._parse_codex_model("local") == ("local", None)
    assert backends._parse_codex_model("openrouter@deepseek/x-v3.1") == (
        "openrouter",
        "deepseek/x-v3.1",
    )
    assert backends._parse_codex_model("openrouter@") == ("openrouter", None)
    assert backends._parse_codex_model("@gpt-5.5") == (None, "gpt-5.5")


def test_copilot_run_turn_fresh_then_resume():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "ANSWER", "session_id": "sess-1"}, "", False, 0)
    )

    with patch.object(backends, "_stream_jsonl", fake):
        out = CopilotBackend().run_turn("PROMPT", "n", sidp)

    assert out == "ANSWER"
    cmd = captured["cmd"]
    assert cmd[0] == "copilot" and "-p" in cmd and "PROMPT" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert "--allow-all" in cmd and "--no-ask-user" in cmd
    assert "--session-id" not in cmd  # fresh run: no resume yet
    assert sidp.read_text() == "sess-1"

    fake2, captured2 = _fake_stream(
        ({"result_text": "A2", "session_id": "sess-1"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake2):
        CopilotBackend().run_turn("P2", "n", sidp)
    assert captured2["cmd"][captured2["cmd"].index("--session-id") + 1] == "sess-1"


def test_codex_on_event_extracts_text_and_session():
    state = {"result_text": "", "session_id": None}
    diag: list[str] = []
    backends._codex_on_event(
        {"type": "thread.started", "thread_id": "abc"}, state, "n", diag
    )
    backends._codex_on_event(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
        state,
        "n",
        diag,
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
        backends._finalize_turn(
            "codex", "n", dict(base), "rate limit hit", False, 1, None
        )
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
        backends._finalize_turn(
            "codex", "n", {"result_text": "", "session_id": None}, "", False, 0, None
        )
        raise AssertionError("expected raise on empty result")
    except agent.BackendInvocationError as e:
        assert e.transient is True
    # Clean success returns the text.
    assert backends._finalize_turn("codex", "n", dict(base), "", False, 0, None) == "x"


def test_finalize_turn_non_recoverable_names_each_backend():
    """A non-zero exit whose output is NOT a retryable marker is non-recoverable
    (transient=False, not overflow), and the message names the ACTUAL backend — the
    one shared classifier (agent.classify_turn) gives every CLI a uniform,
    backend-named error instead of a hardcoded 'Claude'."""
    diag = "Unexpected server error. Check server logs for details."
    for name in ("opencode", "codex", "copilot", "claude"):
        try:
            backends._finalize_turn(
                name,
                "write_epic",
                {"result_text": "", "session_id": None},
                diag,
                False,
                1,
                None,
            )
            raise AssertionError(f"{name}: expected raise on a hard CLI exit")
        except agent.BackendInvocationError as e:
            assert e.transient is False, f"{name}: server error must be non-recoverable"
            assert e.overflow is False
            assert name in str(e), f"{name}: message must name the backend"
            assert "Claude" not in str(e), "must not hardcode 'Claude'"


def test_agentnode_power_is_optional():
    """A node may omit `power:`; the backend default fills in at run time."""
    node = AgentNode(type="agent", id="n", prompt="do it", next="done")
    assert node.power is None
    node2 = AgentNode(type="agent", id="n2", prompt="p", power="high", next="done")
    assert node2.power == "high"


# ── OpenCode backend (opencode run --format json) ───────────────────────────────


def test_opencode_run_turn_fresh_then_resume():
    sidp = Path(tempfile.mkdtemp()) / ".session_id"
    fake, captured = _fake_stream(
        ({"result_text": "PONG", "session_id": "ses_1"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake):
        out = OpenCodeBackend().run_turn(
            "PROMPT", "n", sidp, model="openrouter/xiaomi/mimo-v2.5", effort="high"
        )
    assert out == "PONG"
    cmd = captured["cmd"]
    # --print-logs --log-level ERROR routes opencode's quota/limit errors to stderr so
    # the runner's cap detector can see them (and abort the stream early on a cap).
    assert cmd[:7] == [
        "opencode",
        "--print-logs",
        "--log-level",
        "ERROR",
        "run",
        "--format",
        "json",
    ]
    assert cmd[cmd.index("-m") + 1] == "openrouter/xiaomi/mimo-v2.5"
    assert cmd[cmd.index("--variant") + 1] == "high"  # effort → variant
    assert "--session" not in cmd  # fresh run
    # The prompt is the final positional, guarded by `--`.
    assert cmd[-2:] == ["--", "PROMPT"]
    assert captured["stdin"] is None  # message is on argv, not stdin
    assert sidp.read_text() == "ses_1"  # session persisted for resume

    fake2, captured2 = _fake_stream(
        ({"result_text": "P2", "session_id": "ses_1"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake2):
        OpenCodeBackend().run_turn("P2", "n", sidp, model="openrouter/xiaomi/mimo-v2.5")
    assert captured2["cmd"][captured2["cmd"].index("--session") + 1] == "ses_1"


def test_opencode_effort_variant_mapping_and_omit():
    sidp = Path(tempfile.mkdtemp()) / ".s"
    cases = {"low": "minimal", "high": "high", "xhigh": "max", "max": "max"}
    for effort, variant in cases.items():
        fake, captured = _fake_stream(
            ({"result_text": "X", "session_id": "s"}, "", False, 0)
        )
        with patch.object(backends, "_stream_jsonl", fake):
            OpenCodeBackend().run_turn("P", "n", sidp, model="m", effort=effort)
        assert captured["cmd"][captured["cmd"].index("--variant") + 1] == variant
    # "medium" has no opencode variant → omitted entirely.
    fake, captured = _fake_stream(
        ({"result_text": "X", "session_id": "s"}, "", False, 0)
    )
    with patch.object(backends, "_stream_jsonl", fake):
        OpenCodeBackend().run_turn("P", "n", sidp, model="m", effort="medium")
    assert "--variant" not in captured["cmd"]


def test_opencode_on_event_text_session_and_error():
    state = {"result_text": "", "session_id": None}
    diag: list[str] = []
    backends._opencode_on_event(
        {"type": "step_start", "sessionID": "ses_9", "part": {}}, state, "n", diag
    )
    backends._opencode_on_event(
        {"type": "text", "sessionID": "ses_9", "part": {"id": "p1", "text": "PONG"}},
        state,
        "n",
        diag,
    )
    assert state["session_id"] == "ses_9"
    assert state["result_text"] == "PONG"
    # A second distinct text part is appended, preserving order.
    backends._opencode_on_event(
        {"type": "text", "sessionID": "ses_9", "part": {"id": "p2", "text": "more"}},
        state,
        "n",
        diag,
    )
    assert state["result_text"] == "PONG\nmore"
    # An error event is captured as a diagnostic.
    backends._opencode_on_event(
        {"type": "error", "sessionID": "ses_9", "error": {"data": {"message": "boom"}}},
        state,
        "n",
        diag,
    )
    assert any("boom" in d for d in diag)


# ── Aider backend (aider --message, plain-text capture) ─────────────────────────


def _fake_text_turn():
    """Stand-in for _run_text_turn that records the cmd and returns canned text."""
    captured = {}

    def fake(backend_name, cmd, node_id, timeout, cwd, session_id_path):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return "AIDER OK"

    return fake, captured


def test_aider_run_turn_builds_noninteractive_cmd():
    fake, captured = _fake_text_turn()
    with patch.object(backends, "_run_text_turn", fake):
        out = AiderBackend().run_turn(
            "PROMPT", "n", None, model="openrouter/xiaomi/mimo-v2.5", cwd="/repo"
        )
    assert out == "AIDER OK"
    cmd = captured["cmd"]
    assert cmd[0] == "aider"
    assert cmd[cmd.index("--message") + 1] == "PROMPT"
    assert cmd[cmd.index("--model") + 1] == "openrouter/xiaomi/mimo-v2.5"
    # Fully non-interactive, no repo/git mutation behind our back.
    for flag in (
        "--yes-always",
        "--no-stream",
        "--no-pretty",
        "--no-auto-commits",
        "--no-gitignore",
    ):
        assert flag in cmd
    assert captured["cwd"] == "/repo"


def test_aider_effort_clamped_to_high():
    for level, expected in (
        ("low", "low"),
        ("high", "high"),
        ("xhigh", "high"),
        ("max", "high"),
    ):
        fake, captured = _fake_text_turn()
        with patch.object(backends, "_run_text_turn", fake):
            AiderBackend().run_turn("P", "n", None, model="m", effort=level)
        assert (
            captured["cmd"][captured["cmd"].index("--reasoning-effort") + 1] == expected
        )


def test_aider_no_effort_omits_flag():
    fake, captured = _fake_text_turn()
    with patch.object(backends, "_run_text_turn", fake):
        AiderBackend().run_turn("P", "n", None, model="m")
    assert "--reasoning-effort" not in captured["cmd"]


def test_codex_reset_at_skips_non_openai_models_without_network():
    """The reset probe is Codex-only: an OpenRouter (or empty) model returns None with
    no network call (those caps go through the daily-key-limit path)."""
    # No urllib patch needed: a network attempt here would be a bug, so its absence
    # (these return before any request) is the assertion.
    assert backends._codex_reset_at("openrouter/xiaomi/mimo-v2.5") is None
    assert backends._codex_reset_at(None) is None
    assert backends._codex_reset_at("") is None


def test_codex_reset_at_disabled_by_env():
    """WORKHORSE_CODEX_RESET_PROBE=0 turns the probe off entirely."""
    with patch.dict(os.environ, {"WORKHORSE_CODEX_RESET_PROBE": "0"}):
        assert backends._codex_reset_at("openai/gpt-5.5") is None


def test_opencode_cap_attaches_codex_reset_at():
    """On a Codex usage cap, run_turn fetches the precise reset epoch and the raised
    cap error carries it — so the runner sleeps until the window reopens, not a flat
    default hour."""
    reset = 1782759835.0
    capped = (
        {"result_text": "", "session_id": None},
        'error.error="AI_APICallError: The usage limit has been reached"',
        True,  # cap_abort flagged timed_out
        0,
    )
    fake, _ = _fake_stream(capped)
    with (
        patch.object(backends, "_stream_jsonl", fake),
        patch.object(
            backends, "_codex_reset_at", lambda model, *a, **k: reset
        ),
    ):
        try:
            OpenCodeBackend().run_turn(
                "P", "review_implementation", None, model="openai/gpt-5.5"
            )
            raise AssertionError("expected a cap BackendInvocationError")
        except agent.BackendInvocationError as exc:
            assert exc.reset_at == reset, (
                "precise Codex reset must ride through to the runner"
            )
            assert "cap reached" in str(
                exc
            ) and "Timeout waiting for result" not in str(exc)


def test_opencode_non_cap_does_not_probe_codex():
    """A normal (non-cap) opencode turn never touches the Codex reset probe."""
    ok = ({"result_text": "DONE", "session_id": "s"}, "", False, 0)
    fake, _ = _fake_stream(ok)
    calls = {"n": 0}
    with (
        patch.object(backends, "_stream_jsonl", fake),
        patch.object(
            backends,
            "_codex_reset_at",
            lambda *a, **k: calls.__setitem__("n", calls["n"] + 1),
        ),
    ):
        out = OpenCodeBackend().run_turn("P", "n", None, model="openai/gpt-5.5")
    assert out == "DONE"
    assert calls["n"] == 0, "no cap → no probe"


def _drive_stream_jsonl(lines, on_event):
    """Run backends._stream_jsonl, feeding ``lines`` to its on_line callback through a
    faked stream_subprocess that stops the moment on_line requests an early abort
    (mirroring agent.stream_subprocess). Returns (state, diagnostics, timed_out, rc)."""

    def fake_stream(cmd, node_id, timeout, on_line, **kwargs):
        for raw in lines:
            if on_line(
                raw
            ):  # cap detected → break + (real code) kill the process group
                return True, 0
        return False, 0

    with patch.object(agent, "stream_subprocess", fake_stream):
        return backends._stream_jsonl(
            ["opencode"], "review_implementation", 3600, None, on_event
        )


def test_opencode_cap_log_line_aborts_stream_early():
    """A cap surfaced as a raw --print-logs ERROR line aborts the stream immediately
    (timed_out flagged so the runner waits the window out) instead of waiting ~3600s
    for the watchdog while opencode retries internally."""
    consumed = {"n": 0}

    def on_event(event, state, node_id, diagnostics):
        consumed["n"] += 1  # only real JSON events reach here; the cap line is non-JSON

    state, diag, timed_out, rc = _drive_stream_jsonl(
        [
            '{"type":"step","text":"working"}\n',
            'level=ERROR message="stream error" error.error="AI_APICallError: '
            'The usage limit has been reached"\n',
            '{"type":"step","text":"SHOULD NOT BE READ"}\n',  # after the abort
        ],
        on_event,
    )
    assert timed_out is True, "cap abort must flag timed_out so the turn finalizes"
    assert "usage limit" in diag.lower()
    assert consumed["n"] == 1, "stream must stop at the cap line — later events unread"
    # The runner's classifier then frames this as a cap, not a timeout.
    try:
        agent.classify_turn(
            "opencode",
            "review_implementation",
            result_text=state.get("result_text") or None,
            diagnostics=diag,
            timed_out=timed_out,
            returncode=rc,
            timeout=3600,
        )
        raise AssertionError("expected a cap BackendInvocationError")
    except agent.BackendInvocationError as exc:
        assert "cap reached" in str(exc) and "Timeout waiting for result" not in str(
            exc
        )


def test_opencode_cap_structured_error_event_aborts_stream_early():
    """A cap surfaced as a structured JSON error event (not a log line) is caught the
    same way — the on_event-appended diagnostics trip the cap abort."""

    def on_event(event, state, node_id, diagnostics):
        if event.get("type") == "error":
            diagnostics.append(event.get("message") or "")

    state, diag, timed_out, rc = _drive_stream_jsonl(
        [
            '{"type":"step","text":"working"}\n',
            '{"type":"error","message":"The usage limit has been reached"}\n',
            '{"type":"step","text":"SHOULD NOT BE READ"}\n',
        ],
        on_event,
    )
    assert timed_out is True
    assert "usage limit" in diag.lower()


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
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
