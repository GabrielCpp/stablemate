"""Tests for per-CLI model resolution (runner/agent.py:_model_for_backend).

A node's ``model:`` may be a plain string (absolute default for every backend) or
a per-CLI map keyed by backend name with an optional ``"default"`` key. Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

from workhorse.runner.agent import _model_for_backend, _resolve_model
from workhorse.runner.profiles import Profile


def _litellm_profile() -> Profile:
    return Profile(
        name="litellm",
        cli="codex",
        models={"mimo": "mimo@mimo", "mimo-pro": "mimo@mimo-pro"},
        default_model="mimo",
        env={},
        effort="none",
    )


def test_none_yields_none():
    # No per-node model → caller falls through to env / backend default.
    assert _model_for_backend(None, "claude") is None
    assert _model_for_backend(None, "copilot") is None


def test_string_is_absolute_default_for_every_backend():
    # Regression: a plain string behaves exactly as before — same for all backends.
    for backend in ("claude", "codex", "copilot"):
        assert _model_for_backend("opus", backend) == "opus"


def test_map_picks_the_backend_entry():
    m = {"claude": "opus", "codex": "@gpt-5.5"}
    assert _model_for_backend(m, "claude") == "opus"
    assert _model_for_backend(m, "codex") == "@gpt-5.5"


def test_map_missing_backend_without_default_yields_none():
    # copilot is not listed and there's no "default" → fall through (None).
    m = {"claude": "opus", "codex": "@gpt-5.5"}
    assert _model_for_backend(m, "copilot") is None


def test_map_default_key_covers_unlisted_backends():
    m = {"claude": "opus", "default": "sonnet"}
    assert _model_for_backend(m, "claude") == "opus"   # explicit entry wins
    assert _model_for_backend(m, "codex") == "sonnet"  # falls to "default"
    assert _model_for_backend(m, "copilot") == "sonnet"


def test_haiku_map_only_pins_claude():
    # research's light nodes: claude:haiku, others fall through to their own default.
    m = {"claude": "haiku"}
    assert _model_for_backend(m, "claude") == "haiku"
    assert _model_for_backend(m, "codex") is None
    assert _model_for_backend(m, "copilot") is None


# ── _resolve_model: the (cli, profile) precedence ────────────────────────────────


def test_default_profile_matches_legacy_chain():
    # profile=None → node CLI-map, then AGENT_MODEL, then AGENT_CLAUDE_MODEL, else None.
    assert _resolve_model(None, {"codex": "@gpt-5.5"}, "codex", {}) == "@gpt-5.5"
    assert _resolve_model(None, None, "codex", {"AGENT_MODEL": "x"}) == "x"
    assert _resolve_model(None, None, "codex", {"AGENT_CLAUDE_MODEL": "y"}) == "y"
    assert _resolve_model(None, None, "codex", {}) is None


def test_named_profile_default_when_node_silent():
    p = _litellm_profile()
    assert _resolve_model(p, {"claude": "opus", "codex": "@gpt-5.5"}, "codex", {}) == "mimo@mimo"
    assert _resolve_model(p, None, "codex", {}) == "mimo@mimo"


def test_named_profile_node_per_profile_key_overrides():
    p = _litellm_profile()
    nm = {"claude": "opus", "codex": "@gpt-5.5", "litellm": "mimo-pro"}
    assert _resolve_model(p, nm, "codex", {}) == "mimo@mimo-pro"


def test_named_profile_ignores_cli_map():
    # Regression for the core bug: the node's codex entry must NOT leak through
    # under a profile (it used to send `-m gpt-5.5` against the mimo provider).
    p = _litellm_profile()
    assert _resolve_model(p, {"codex": "@gpt-5.5"}, "codex", {}) == "mimo@mimo"


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
