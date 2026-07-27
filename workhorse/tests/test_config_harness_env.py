"""Tests for per-harness environment config (``[harness.<backend>].env``).

Some agent-CLI knobs exist only as environment variables — no flag, no config key
workhorse could pass through. ``[harness.<backend>].env`` is the generic seam for
them: the operator names the variables, workhorse forwards them to that harness's
subprocess and to nothing else.

Two properties matter and are what this file pins:

* **Resolution is total.** A missing, empty, or wrong-typed section yields ``{}``,
  never an exception — a config read must not be what ends an unattended run.
* **The env actually reaches the spawn.** Each backend resolves its own table and
  hands it to the shared spawn path, so the variables land in the CLI's environment
  rather than being resolved and dropped.

Runnable two ways:

    ./.venv/bin/python tests/test_config_harness_env.py
    ./.venv/bin/python -m pytest tests/test_config_harness_env.py
"""

from __future__ import annotations

import os
from unittest.mock import patch

from stablemate_core.config import resolve_harness_env
from workhorse.runner import agent, backends
from workhorse.runner.backends import (
    AiderBackend,
    ClaudeBackend,
    CodexBackend,
    CopilotBackend,
    OpenCodeBackend,
)


CONFIG = {
    "harness": {
        "opencode": {"env": {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}},
        "claude": {"env": {"MAX_THINKING_TOKENS": "31999"}},
    },
    # A sibling top-level table, to prove the lookup is scoped and not a broad scan.
    "power": {"high": {"opencode": {"model": "openai/gpt-5.5"}}},
}


# ── Resolution ────────────────────────────────────────────────────────────────


def test_resolves_configured_backend():
    assert resolve_harness_env("opencode", CONFIG) == {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}
    assert resolve_harness_env("claude", CONFIG) == {"MAX_THINKING_TOKENS": "31999"}


def test_unconfigured_backend_is_empty():
    """A backend with no section gets nothing — not the other backend's variables."""
    assert resolve_harness_env("codex", CONFIG) == {}


def test_missing_sections_never_raise():
    """Every shape a hand-edited config can take degrades to {}, not an exception."""
    for cfg in (
        {},                                            # nothing configured at all
        {"harness": {}},                               # table present, no backends
        {"harness": {"opencode": {}}},                 # backend present, no env
        {"harness": {"opencode": {"env": {}}}},        # env present, empty
        {"harness": "opencode"},                       # harness is a string
        {"harness": {"opencode": "env"}},              # backend is a string
        {"harness": {"opencode": {"env": "FOO=1"}}},   # env is a string, not a table
        {"harness": {"opencode": {"env": ["FOO"]}}},   # env is an array
    ):
        assert resolve_harness_env("opencode", cfg) == {}, cfg


def test_non_string_values_are_dropped():
    """``FOO = 1`` is a TOML integer. Coercing it would make the config lie about
    what the process received, so it is dropped and the string keys still resolve."""
    cfg = {
        "harness": {
            "opencode": {
                "env": {
                    "GOOD": "1",
                    "AN_INT": 1,
                    "A_BOOL": True,
                    "A_FLOAT": 1.5,
                    "A_LIST": ["1"],
                    "NESTED": {"a": "b"},
                    "": "empty-key",
                }
            }
        }
    }
    assert resolve_harness_env("opencode", cfg) == {"GOOD": "1"}


# ── Delivery to the subprocess ────────────────────────────────────────────────


def _spawn_env(backend, **run_turn_kwargs):
    """Drive ``backend.run_turn`` with the spawn path faked, returning the ``env_extra``
    that reached ``stream_subprocess``. The CLI is never launched."""
    seen = {}

    def fake_stream(cmd, node_id, timeout, on_line, **kwargs):
        seen.update(kwargs)
        # Enough of a successful turn that classification does not raise: the JSONL
        # backends need a result event, aider needs any text at all.
        for line in (
            '{"type":"result","result":"ok","subtype":"success"}\n',
            '{"type":"turn.completed","result":"ok"}\n',
            '{"type":"step_finish"}\n',
            "ok\n",
        ):
            on_line(line)
        return False, 0

    with (
        patch.object(agent, "stream_subprocess", fake_stream),
        patch.object(backends, "_finalize_turn", lambda *a, **k: "ok"),
        patch.object(agent, "classify_turn", lambda *a, **k: "ok"),
    ):
        backend.run_turn("P", "n", None, **run_turn_kwargs)
    return seen.get("env_extra")


def _with_config(cfg):
    """Route the resolver every backend calls at ``cfg``, never the real config file."""
    return patch.object(
        backends, "resolve_harness_env", lambda backend: resolve_harness_env(backend, cfg)
    )


def test_configured_env_reaches_the_spawn():
    with _with_config(CONFIG):
        assert _spawn_env(OpenCodeBackend()) == {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}
        assert _spawn_env(ClaudeBackend()) == {"MAX_THINKING_TOKENS": "31999"}


def test_every_backend_forwards_its_own_table():
    """All five harnesses honor the seam — a backend that resolved but never passed
    its env would silently ignore the operator's config."""
    for backend in (
        ClaudeBackend(),
        CodexBackend(),
        CopilotBackend(),
        OpenCodeBackend(),
        AiderBackend(),
    ):
        marker = {f"{backend.name.upper()}_MARKER": "yes"}
        cfg = {"harness": {backend.name: {"env": marker}}}
        with _with_config(cfg):
            assert _spawn_env(backend) == marker, backend.name


def test_unconfigured_backend_spawns_with_no_extra_env():
    """No config must mean no change to the inherited environment — an empty dict is
    what ``stream_subprocess`` already treats as a no-op."""
    with _with_config({}):
        assert _spawn_env(OpenCodeBackend()) == {}


def test_compaction_runs_under_the_same_env():
    """``/compact`` is the same harness on the same session; a knob that shapes the
    conversation must also shape the turn that summarizes it."""
    seen = {}

    def fake_stream(cmd, node_id, timeout, on_line, **kwargs):
        seen.update(kwargs)
        on_line('{"type":"system","status":"compacting","session_id":"s2"}\n')
        on_line('{"type":"system","compact_result":"success","session_id":"s2"}\n')
        return False, 0

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        sid_path = Path(tmp) / "session"
        sid_path.write_text("session-abc")
        with (
            _with_config(CONFIG),
            patch.object(agent, "stream_subprocess", fake_stream),
        ):
            assert ClaudeBackend().compact(sid_path, "n") is True
    assert seen.get("env_extra") == {"MAX_THINKING_TOKENS": "31999"}


def test_harness_env_wins_over_the_inherited_shell():
    """Applied last in ``stream_subprocess``'s merge, so configuring a variable for a
    run overrides whatever the launching shell happened to export."""
    captured = {}

    def fake_spawn(cmd, node_id, **kwargs):
        captured.update(kwargs.get("env") or {})
        raise RuntimeError("stop before launching anything")

    with patch.dict(os.environ, {"HARNESS_KNOB": "from-shell"}, clear=False):
        with patch.object(agent, "_spawn_streaming", fake_spawn):
            try:
                agent.stream_subprocess(
                    ["true"], "n", 1.0, lambda line: None,
                    env_extra={"HARNESS_KNOB": "from-config"},
                )
            except RuntimeError:
                pass
    assert captured.get("HARNESS_KNOB") == "from-config"
    assert captured.get("WORKHORSE_NODE_ID") == "n", "node id still stamped"


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
