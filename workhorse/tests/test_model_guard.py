"""The model guard holds a claude turn's subagents to the models its profile names."""

import io
import json
import shlex
from contextlib import redirect_stdout
from unittest.mock import patch

from _fakes import claude_cmd
from workhorse.profile import profile_models
from workhorse.runner.backends import model_guard
from workhorse.config_run import AgentResilience

PROFILE = ("claude-opus-5-5", "claude-sonnet-5-5", "haiku")
RESILIENCE = AgentResilience()


def _refusal(model, tool="Agent"):
    tool_input = {} if model is None else {"model": model}
    return model_guard.model_refusal(tool, tool_input, model_guard.allowed_models(PROFILE))


def test_a_model_outside_the_profile_is_denied_with_the_allowed_aliases():
    for model in ("fable", "claude-fable-5-1", "Fable"):
        reason = _refusal(model)
        assert reason is not None
        assert model in reason
        assert "opus" in reason and "haiku" in reason


def test_the_profile_models_and_their_family_aliases_pass():
    for model in ("opus", "sonnet", "haiku", "claude-opus-5-5", "claude-sonnet-5-5"):
        assert _refusal(model) is None


def test_a_call_with_no_model_passes():
    assert _refusal(None) is None
    assert _refusal("") is None


def test_another_tool_passes():
    assert _refusal("fable", tool="Bash") is None


def test_the_hook_prints_a_denial_for_fable_and_nothing_for_opus():
    def run(model):
        call = json.dumps({"tool_name": "Agent", "tool_input": {"model": model}})
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO(call)), redirect_stdout(out):
            model_guard.main(list(model_guard.allowed_models(PROFILE)))
        return out.getvalue()

    denied = json.loads(run("claude-fable-5-1"))["hookSpecificOutput"]
    assert denied["permissionDecision"] == "deny"
    assert run("opus") == ""


def test_the_claude_command_line_carries_the_hook_on_the_agent_tool():
    cmd = claude_cmd(models=PROFILE)
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    [entry] = settings["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Agent"
    argv = shlex.split(entry["hooks"][0]["command"])
    assert argv[1:3] == ["-m", model_guard.HOOK_MODULE]
    assert "claude-opus-5-5" in argv and "opus" in argv


def test_a_turn_with_no_profile_models_carries_no_settings():
    assert "--settings" not in claude_cmd()


def test_profile_models_lists_default_powers_and_delegates():
    from workhorse._vendor.stablemate_core.schema import HomeConfig

    home = HomeConfig.model_validate(
        {
            "profiles": {
                "claude": {
                    "cli": "claude",
                    "default": {"model": "claude-sonnet-5-5"},
                    "powers": {"max": {"model": "claude-opus-5-5"}},
                    "delegates": {"lookup": {"model": "haiku"}},
                }
            }
        }
    )
    with patch("workhorse.profile.load_home_config", return_value=home):
        assert profile_models("claude", "claude") == ("claude-sonnet-5-5", "claude-opus-5-5", "haiku")
        assert profile_models("claude", "") == ("claude-sonnet-5-5", "claude-opus-5-5", "haiku")
