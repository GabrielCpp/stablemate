"""Tests for per-CLI model resolution (runner/agent.py:_model_for_backend /
_resolve_model).

A node's ``model:`` may be a plain string (absolute default for every backend) or
a per-CLI map keyed by backend name with an optional ``"default"`` key. The active
backend (AGENT_CLI / --cli) picks its key; resolution then falls through to
AGENT_MODEL / AGENT_CLAUDE_MODEL, else None (caller uses the backend default).
Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

from workhorse.runner.agent import _model_for_backend, _resolve_model

ALL_BACKENDS = ("claude", "codex", "copilot", "aider", "opencode")


def test_none_yields_none():
    # No per-node model → caller falls through to env / backend default.
    assert _model_for_backend(None, "claude") is None
    assert _model_for_backend(None, "opencode") is None


def test_string_is_absolute_default_for_every_backend():
    # Regression: a plain string behaves exactly as before — same for all backends.
    for backend in ALL_BACKENDS:
        assert _model_for_backend("opus", backend) == "opus"


def test_map_picks_the_backend_entry():
    m = {"claude": "opus", "codex": "@gpt-5.5", "aider": "openrouter/xiaomi/mimo-v2.5"}
    assert _model_for_backend(m, "claude") == "opus"
    assert _model_for_backend(m, "codex") == "@gpt-5.5"
    assert _model_for_backend(m, "aider") == "openrouter/xiaomi/mimo-v2.5"


def test_map_missing_backend_without_default_yields_none():
    # copilot is not listed and there's no "default" → fall through (None).
    m = {"claude": "opus", "codex": "@gpt-5.5"}
    assert _model_for_backend(m, "copilot") is None
    assert _model_for_backend(m, "opencode") is None


def test_map_default_key_covers_unlisted_backends():
    m = {"claude": "opus", "default": "sonnet"}
    assert _model_for_backend(m, "claude") == "opus"     # explicit entry wins
    assert _model_for_backend(m, "codex") == "sonnet"    # falls to "default"
    assert _model_for_backend(m, "opencode") == "sonnet"


def test_haiku_map_only_pins_claude():
    # research's light nodes: claude:haiku, others fall through to their own default.
    m = {"claude": "haiku"}
    assert _model_for_backend(m, "claude") == "haiku"
    assert _model_for_backend(m, "codex") is None
    assert _model_for_backend(m, "aider") is None


# ── _resolve_model: node CLI-map → AGENT_MODEL → AGENT_CLAUDE_MODEL → None ────────


def test_resolve_prefers_node_cli_map():
    assert _resolve_model({"codex": "@gpt-5.5"}, "codex", {}) == "@gpt-5.5"


def test_resolve_openrouter_model_for_openrouter_backend():
    # The MiMo experiment: an aider node names an OpenRouter slug directly, no proxy.
    nm = {"claude": "opus", "aider": "openrouter/xiaomi/mimo-v2.5"}
    assert _resolve_model(nm, "aider", {}) == "openrouter/xiaomi/mimo-v2.5"
    assert _resolve_model(nm, "opencode", {}) is None  # unlisted, no default


def test_resolve_falls_through_to_env_then_none():
    assert _resolve_model(None, "codex", {"AGENT_MODEL": "x"}) == "x"
    assert _resolve_model(None, "codex", {"AGENT_CLAUDE_MODEL": "y"}) == "y"
    assert _resolve_model(None, "codex", {}) is None


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
