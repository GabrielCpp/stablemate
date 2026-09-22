"""A repair turn pays for every tool schema on every step, so the adapter narrows the agent."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from workhorse._vendor.stablemate_core import config
from workhorse.config_run import AgentResilience
from workhorse.runner.backends import AgentProfile
from workhorse.runner.backends import turn
from workhorse.runner.backends.opencode import OpenCodeBackend

RESILIENCE = AgentResilience()

PROFILE = AgentProfile(
    name="okf-repair",
    tools={"webfetch": False, "websearch": False, "task": False},
    steps=20,
    disable_mcp=("playwright",),
    tool_output_max_lines=400,
    tool_output_max_bytes=20000,
)


@contextmanager
def _config(text: str):
    """Point the shared config at a temp file holding ``text``."""
    prior_cli = os.environ.pop("AGENT_CLI", None)
    prior_path = os.environ.get(config.CONFIG_PATH_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(text)
        os.environ[config.CONFIG_PATH_ENV] = str(path)
        try:
            yield path
        finally:
            if prior_path is None:
                os.environ.pop(config.CONFIG_PATH_ENV, None)
            else:
                os.environ[config.CONFIG_PATH_ENV] = prior_path
            if prior_cli is not None:
                os.environ["AGENT_CLI"] = prior_cli


def _fake_stream(canned):
    """A ``stream_jsonl`` stand-in that records the argv and environment of one turn."""
    captured = {}

    def fake(cmd, node_id, timeout, stdin_data, on_event, **kwargs):
        captured["cmd"] = cmd
        captured["env_extra"] = kwargs.get("env_extra")
        return canned

    return fake, captured


def _turn(profile, *, operator_config: str = "", model: str | None = "minimax/MiniMax-M3"):
    """Run one canned turn under ``profile`` and return its argv and injected config."""
    cfg = (
        "[harness.opencode]\n"
        f"env = {{ OPENCODE_CONFIG_CONTENT = '{operator_config}' }}\n"
        if operator_config
        else ""
    )
    with _config(cfg):
        fake, captured = _fake_stream(turn.TurnState(result_text="X", session_id="s"))
        OpenCodeBackend(fake).run_turn(
            "P", "n", None, model, timeout=RESILIENCE.result_timeout_s,
            resilience=RESILIENCE, agent=profile,
        )
    raw = captured["env_extra"].get("OPENCODE_CONFIG_CONTENT")
    return captured["cmd"], json.loads(raw) if raw else {}


def test_the_turn_names_the_profile_and_the_config_defines_it():
    """``--agent`` alone is inert: opencode falls back to its default agent when nothing defines the name."""
    cmd, cfg = _turn(PROFILE)
    assert cmd[cmd.index("--agent") + 1] == "okf-repair"
    assert "okf-repair" in cfg["agent"]


def test_the_tools_the_turn_never_calls_are_denied():
    """A denied tool leaves the request entirely, which is the point: its schema is resent on every step."""
    _, cfg = _turn(PROFILE)
    assert cfg["agent"]["okf-repair"]["tools"] == {
        "webfetch": False,
        "websearch": False,
        "task": False,
    }


def test_denying_an_edit_alias_is_refused():
    """opencode folds ``write``, ``edit`` and ``patch`` onto one permission, so denying any of them disarms the turn."""
    for alias in ("write", "edit", "patch"):
        try:
            _turn(AgentProfile(name="x", tools={alias: False}))
        except ValueError as exc:
            assert alias in str(exc)
        else:
            raise AssertionError(f"denying {alias} should have been refused")


def test_the_browser_server_and_the_output_clip_ride_along():
    """A Playwright MCP server the repair turn has never called still ships its schemas on every step."""
    _, cfg = _turn(PROFILE)
    assert cfg["mcp"] == {"playwright": {"enabled": False}}
    assert cfg["tool_output"] == {"max_lines": 400, "max_bytes": 20000}


def test_the_step_budget_is_absent_until_a_profile_asks_for_one():
    """An unset budget must not become a default one: opencode's own limit stands."""
    _, cfg = _turn(AgentProfile(name="okf-repair"))
    assert "steps" not in cfg["agent"]["okf-repair"]
    _, budgeted = _turn(PROFILE)
    assert budgeted["agent"]["okf-repair"]["steps"] == 20


def test_an_operator_config_is_merged_rather_than_replaced():
    """The previous adapter skipped itself whenever an operator set the variable, losing the ``small_model`` pin on every machine with a harness env entry."""
    _, cfg = _turn(PROFILE, operator_config='{"theme":"ansi","small_model":"openai/gpt-5.5"}')
    assert cfg["theme"] == "ansi"
    assert cfg["small_model"] == "openai/gpt-5.5"
    assert cfg["agent"]["okf-repair"]["steps"] == 20


def test_a_turn_with_no_profile_is_unchanged():
    """Every other node still invokes opencode exactly as it did before."""
    cmd, cfg = _turn(None)
    assert "--agent" not in cmd
    assert cfg == {"small_model": "minimax/MiniMax-M3"}


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
