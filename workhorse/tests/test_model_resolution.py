"""Tests for per-CLI model resolution (runner/agent.py:_model_for_backend).

A node's ``model:`` may be a plain string (absolute default for every backend) or
a per-CLI map keyed by backend name with an optional ``"default"`` key. Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

from workhorse.runner.agent import _model_for_backend


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


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
