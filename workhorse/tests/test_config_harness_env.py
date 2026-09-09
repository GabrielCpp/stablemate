"""Tests for per-CLI environment config (``[cli.<backend>].env``).

Some agent-CLI knobs exist only as environment variables — no flag, no config key
workhorse could pass through. ``[cli.<backend>].env`` is the generic seam for
them: the operator names the variables, workhorse forwards them to that CLI's
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
    # A sibling top-level table, to prove the lookup is scoped and not a broad scan.
    "profiles": {
        "opencode": {
            "cli": "opencode",
            "powers": {"high": {"model": "openai/gpt-5.5"}},
        },
    },
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
        {"cli": {}},                                   # table present, no backends
        {"cli": {"opencode": {}}},                     # backend present, no env
        {"cli": {"opencode": {"env": {}}}},            # env present, empty
        {"cli": "opencode"},                           # cli table is a string
        {"cli": {"opencode": "env"}},                  # backend is a string
        {"cli": {"opencode": {"env": "FOO=1"}}},       # env is a string, not a table
        {"cli": {"opencode": {"env": ["FOO"]}}},       # env is an array
    ):
        assert resolve_harness_env("opencode", cfg) == {}, cfg


def test_non_string_values_are_dropped():
    """``FOO = 1`` is a TOML integer. Coercing it would make the config lie about
    what the process received, so it is dropped and the string keys still resolve."""
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


# ── Delivery to the subprocess ────────────────────────────────────────────────

#: The turn budget and the ladder's knobs are injected at the CLI edge; a test that
#: drives a backend directly states them rather than relying on a module constant.
RESILIENCE = AgentResilience()


def _spawn_env(backend, **run_turn_kwargs):
    """Drive ``backend.run_turn`` with the spawn path faked, returning the ``env_extra``
    that reached ``stream_subprocess``. The CLI is never launched."""
    seen = {}

    def fake_stream(cmd, node_id, timeout, on_line, **kwargs):
        seen.update(kwargs)
        # Enough of a successful turn that classification does not raise: the JSONL
        # backends each need their own terminal event.
        for line in (
            '{"type":"result","result":"ok","subtype":"success"}\n',
            '{"type":"turn.completed","result":"ok"}\n',
            '{"type":"step_finish"}\n',
            "ok\n",
        ):
            on_line(line)
        return False, 0

    # Only the shared classifier is stubbed: every backend — Claude directly, the
    # others through ``backends.turn.finalize_turn`` — ends its turn there, so one
    # patch at that boundary covers all five without reaching into any adapter.
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


#: The one variable the opencode adapter exports on its own, whatever the config says
#: (it lifts opencode's 32k output cap to the model's own limit); an operator's value
#: for the same name wins. See ``backends.opencode``.
OPENCODE_OWN = {"OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": "131072"}


def test_configured_env_reaches_the_spawn():
    with _with_config(CONFIG):
        assert _spawn_env(OpenCodeBackend()) == {
            "OPENCODE_DISABLE_AUTOCOMPACT": "1", **OPENCODE_OWN
        }
        assert _spawn_env(ClaudeBackend()) == {"MAX_THINKING_TOKENS": "31999"}


def test_every_backend_forwards_its_own_table():
    """All five harnesses honor the seam — a backend that resolved but never passed
    its env would silently ignore the operator's config."""
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
    """No config must mean no change to the inherited environment — an empty dict is
    what ``stream_subprocess`` already treats as a no-op. opencode is the exception
    by design: its adapter always exports its own output-cap override."""
    with _with_config({}):
        assert _spawn_env(ClaudeBackend()) == {}
        assert _spawn_env(OpenCodeBackend()) == OPENCODE_OWN


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
            patch.object(process, "stream_subprocess", fake_stream),
        ):
            assert ClaudeBackend().compact(
                sid_path, "n",
                timeout=RESILIENCE.result_timeout_s,
                resilience=RESILIENCE,
            ) is True
    assert seen.get("env_extra") == {"MAX_THINKING_TOKENS": "31999"}


def test_harness_env_wins_over_the_inherited_shell():
    """Applied last in ``stream_subprocess``'s merge, so configuring a variable for a
    run overrides whatever the launching shell happened to export."""
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
