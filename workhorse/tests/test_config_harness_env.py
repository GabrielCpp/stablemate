"""Tests for per-CLI environment config (``[cli.<backend>].env``)."""

from __future__ import annotations

import os
from unittest.mock import patch

from workhorse._vendor.stablemate_core.config import resolve_harness_env
from workhorse.config_run import AgentResilience
from workhorse.runner import backends, failure, process
from workhorse.runner.backends.cline import ClineBackend
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.copilot import CopilotBackend
from workhorse.runner.backends.opencode import OpenCodeBackend


CONFIG = {
    "cli": {
        "opencode": {"env": {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}},
        "claude": {"env": {"MAX_THINKING_TOKENS": "31999"}},
    },
    "profiles": {
        "opencode": {
            "cli": "opencode",
            "powers": {"high": {"model": "openai/gpt-5.5"}},
        },
    },
}




def test_resolves_configured_backend():
    assert resolve_harness_env("opencode", CONFIG) == {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}
    assert resolve_harness_env("claude", CONFIG) == {"MAX_THINKING_TOKENS": "31999"}


def test_unconfigured_backend_is_empty():
    """A backend with no section gets nothing — not the other backend's variables."""
    assert resolve_harness_env("codex", CONFIG) == {}


def test_missing_sections_never_raise():
    """Every shape a hand-edited config can take degrades to {}, not an exception."""
    for cfg in (
        {},
        {"cli": {}},
        {"cli": {"opencode": {}}},
        {"cli": {"opencode": {"env": {}}}},
        {"cli": "opencode"},
        {"cli": {"opencode": "env"}},
        {"cli": {"opencode": {"env": "FOO=1"}}},
        {"cli": {"opencode": {"env": ["FOO"]}}},
    ):
        assert resolve_harness_env("opencode", cfg) == {}, cfg


def test_non_string_values_are_dropped():
    """``FOO = 1`` is a TOML integer."""
    cfg = {
        "cli": {
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



RESILIENCE = AgentResilience()


def _spawn_env(backend, **run_turn_kwargs):
    """Drive ``backend.run_turn`` with the spawn path faked, returning the ``env_extra`` that reached ``stream_subprocess``."""
    seen = {}

    def fake_stream(cmd, node_id, timeout, on_line, **kwargs):
        seen.update(kwargs)
        for line in (
            '{"type":"result","result":"ok","subtype":"success"}\n',
            '{"type":"turn.completed","result":"ok"}\n',
            '{"type":"step_finish"}\n',
            "ok\n",
        ):
            on_line(line)
        return False, 0

    with (
        patch.object(process, "stream_subprocess", fake_stream),
        patch.object(failure, "classify_turn", lambda *a, **k: "ok"),
    ):
        backend.run_turn(
            "P", "n", None,
            timeout=RESILIENCE.result_timeout_s,
            resilience=RESILIENCE,
            **run_turn_kwargs,
        )
    return seen.get("env_extra")


def _with_config(cfg):
    """Route the resolver every backend calls at ``cfg``, never the real config file."""
    return patch.object(
        backends, "resolve_harness_env", lambda backend: resolve_harness_env(backend, cfg)
    )


OPENCODE_OWN = {"OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": "131072"}


def test_configured_env_reaches_the_spawn():
    with _with_config(CONFIG):
        assert _spawn_env(OpenCodeBackend()) == {
            "OPENCODE_DISABLE_AUTOCOMPACT": "1", **OPENCODE_OWN
        }
        assert _spawn_env(ClaudeBackend()) == {"MAX_THINKING_TOKENS": "31999"}


def test_every_backend_forwards_its_own_table():
    """All five harnesses honor the seam — a backend that resolved but never passed its env would silently ignore the operator's config."""
    for backend in (
        ClaudeBackend(),
        CodexBackend(),
        CopilotBackend(),
        OpenCodeBackend(),
        ClineBackend(),
    ):
        marker = {f"{backend.name.upper()}_MARKER": "yes"}
        cfg = {"cli": {backend.name: {"env": marker}}}
        own = OPENCODE_OWN if isinstance(backend, OpenCodeBackend) else {}
        with _with_config(cfg):
            assert _spawn_env(backend) == {**marker, **own}, backend.name


def test_unconfigured_backend_spawns_with_no_extra_env():
    """No config must mean no change to the inherited environment — an empty dict is what ``stream_subprocess`` already treats as a no-op."""
    with _with_config({}):
        assert _spawn_env(ClaudeBackend()) == {}
        assert _spawn_env(OpenCodeBackend()) == OPENCODE_OWN


def test_compaction_runs_under_the_same_env():
    """``/compact`` is the same harness on the same session; a knob that shapes the conversation must also shape the turn that summarizes it."""
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
            patch.object(process, "stream_subprocess", fake_stream),
        ):
            assert ClaudeBackend().compact(
                sid_path, "n",
                timeout=RESILIENCE.result_timeout_s,
                resilience=RESILIENCE,
            ) is True
    assert seen.get("env_extra") == {"MAX_THINKING_TOKENS": "31999"}


def test_harness_env_wins_over_the_inherited_shell():
    """Applied last in ``stream_subprocess``'s merge, so configuring a variable for a run overrides whatever the launching shell happened to export."""
    captured = {}

    def fake_spawn(self, cmd, node_id, **kwargs):
        captured.update(kwargs.get("env") or {})
        raise RuntimeError("stop before launching anything")

    with patch.dict(os.environ, {"HARNESS_KNOB": "from-shell"}, clear=False):
        with patch.object(process.ProcessSupervisor, "spawn", fake_spawn):
            try:
                process.stream_subprocess(
                    ["true"], "n", 1.0, lambda line: None,
                    resilience=RESILIENCE,
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
