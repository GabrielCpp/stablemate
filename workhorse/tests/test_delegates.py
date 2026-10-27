"""The subagents a profile opts a run into, and how each CLI receives them at launch."""

from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from _fakes import FakeBackend, FakeClock
from workhorse._vendor.stablemate_core import config
from workhorse._vendor.stablemate_core.profiles import PowerMapping
from workhorse.config_run import AgentResilience
from workhorse.profile import ProfileSelection, resolve_delegates_for
from workhorse.runner import ladder
from workhorse.runner.backends import turn
from workhorse.runner.backends import delegates as delegates_module
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.copilot import CopilotBackend
from workhorse.runner.backends.delegates import Delegate, delegates_for
from workhorse.runner.backends.opencode import OpenCodeBackend

RESILIENCE = AgentResilience()

LOOKUP = Delegate(
    name="lookup",
    model="small",
    effort="low",
    description="Read-only lookup.",
    instructions="Answer one question.",
    read_only=True,
)
WORKER = Delegate(
    name="worker",
    model="mid",
    effort=None,
    description="Bounded task.",
    instructions="Do the task.",
    read_only=False,
)

_PROFILE = """\
config_version = 2

[profiles.mine]
cli = "fake"

[profiles.mine.delegates.lookup]
model = "small"
effort = "low"

[profiles.plain]
cli = "fake"
"""


@pytest.fixture(autouse=True)
def _fresh_warnings(monkeypatch):
    monkeypatch.setattr(delegates_module, "_warned", set())


@pytest.fixture
def profile_config(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(_PROFILE)
    monkeypatch.setenv(config.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(config.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv("CODEX_PROFILE", raising=False)
    return path


def _stream_capturing(captured, read_files=False):
    def fake(cmd, node_id, timeout, stdin_data, on_event, **kwargs):
        captured["cmd"] = cmd
        captured["env_extra"] = kwargs.get("env_extra")
        if read_files:
            captured["files"] = {
                arg: Path(json.loads(arg.split("=", 1)[1])).read_text()
                for arg in cmd
                if arg.startswith("agents.") and ".config_file=" in arg
            }
        return turn.TurnState(result_text="OK", session_id="s")

    return fake


def _claude_cmd(**kwargs):
    captured = {}

    def fake_popen(cmd, *a, **k):
        captured["cmd"] = cmd
        raise RuntimeError("stop before spawning")

    with patch("subprocess.Popen", fake_popen):
        try:
            ClaudeBackend().run_turn("P", "n", None, timeout=60, resilience=RESILIENCE, **kwargs)
        except Exception:
            pass
    return captured["cmd"]


def test_the_catalog_keeps_its_order_and_drops_a_role_with_no_model():
    picked = delegates_for(
        {"worker": PowerMapping(model="mid"), "lookup": PowerMapping(model="small", effort="low")}
    )
    assert [(d.name, d.model, d.effort, d.read_only) for d in picked] == [
        ("lookup", "small", "low", True),
        ("worker", "mid", None, False),
    ]
    assert delegates_for({"lookup": PowerMapping(effort="low")}) == ()


def test_an_unknown_role_is_named_once_and_ignored():
    out = io.StringIO()
    with redirect_stdout(out):
        first = delegates_for({"scout": PowerMapping(model="small")})
        delegates_for({"scout": PowerMapping(model="small")})
    assert first == ()
    assert out.getvalue().count("delegates.scout is not a subagent role") == 1


def test_a_profile_without_delegates_gives_none(profile_config):
    assert resolve_delegates_for("fake", "plain") == ()
    assert [d.name for d in resolve_delegates_for("fake", "mine")] == ["lookup"]
    assert resolve_delegates_for("claude", "mine") == ()


def test_every_turn_carries_the_profiles_delegates_to_the_cli(profile_config):
    seen = []

    def run(prompt, node_id, sid, model, **kwargs):
        seen.append(kwargs["delegates"])
        return "OK"

    runner = ladder.AgentRunner(
        backend=FakeBackend(turn=run), clock=FakeClock(), profile=ProfileSelection("mine")
    )
    runner.turn("P", "n", None, timeout=60)
    runner.profile.name = "plain"
    runner.turn("P", "n", None, timeout=60)

    assert [d.name for d in seen[0]] == ["lookup"]
    assert seen[1] == ()


def test_claude_defines_each_delegate_as_a_session_agent():
    cmd = _claude_cmd(model="opus", delegates=(LOOKUP, WORKER))
    agents = json.loads(cmd[cmd.index("--agents") + 1])
    assert agents == {
        "lookup": {
            "description": "Read-only lookup.",
            "prompt": "Answer one question.",
            "model": "small",
            "effort": "low",
            "tools": ["Read", "Grep", "Glob", "Bash"],
        },
        "worker": {"description": "Bounded task.", "prompt": "Do the task.", "model": "mid"},
    }
    assert "--agents" not in _claude_cmd(model="opus")


def test_opencode_merges_each_delegate_into_its_config_as_a_subagent(profile_config):
    captured = {}
    OpenCodeBackend(_stream_capturing(captured)).run_turn(
        "P", "n", None, model="big", timeout=60, resilience=RESILIENCE, delegates=(LOOKUP, WORKER)
    )
    content = json.loads(captured["env_extra"]["OPENCODE_CONFIG_CONTENT"])
    assert content["small_model"] == "big"
    assert content["agent"] == {
        "lookup": {
            "mode": "subagent",
            "model": "small",
            "description": "Read-only lookup.",
            "prompt": "Answer one question.",
            "variant": "minimal",
            "permission": {"edit": "deny"},
        },
        "worker": {
            "mode": "subagent",
            "model": "mid",
            "description": "Bounded task.",
            "prompt": "Do the task.",
        },
    }


def test_codex_defines_each_delegate_as_a_role_with_a_file_for_the_turn(profile_config):
    captured = {}
    CodexBackend(_stream_capturing(captured, read_files=True)).run_turn(
        "P", "n", None, model="@gpt-big", effort="max", timeout=60, resilience=RESILIENCE,
        delegates=(LOOKUP, WORKER),
    )
    cmd = captured["cmd"]
    assert 'agents.lookup.description="Read-only lookup."' in cmd
    files = captured["files"]
    lookup_file = next(arg for arg in files if arg.startswith("agents.lookup."))
    assert files[lookup_file] == (
        'model = "small"\n'
        'model_reasoning_effort = "low"\n'
        'sandbox_mode = "read-only"\n'
        'developer_instructions = "Answer one question."\n'
    )
    worker_file = next(arg for arg in files if arg.startswith("agents.worker."))
    assert files[worker_file] == 'model = "mid"\ndeveloper_instructions = "Do the task."\n'
    assert not Path(json.loads(lookup_file.split("=", 1)[1])).exists()


def test_codex_without_delegates_adds_no_role(profile_config):
    captured = {}
    CodexBackend(_stream_capturing(captured)).run_turn(
        "P", "n", None, model="@gpt-big", timeout=60, resilience=RESILIENCE
    )
    assert not any(arg.startswith("agents.") for arg in captured["cmd"])


def test_a_cli_with_no_launch_time_subagents_says_so_once(profile_config):
    out = io.StringIO()
    captured = {}
    with redirect_stdout(out):
        for _ in range(2):
            CopilotBackend(_stream_capturing(captured)).run_turn(
                "P", "n", Path(tempfile.mkdtemp()) / ".sid", timeout=60, resilience=RESILIENCE,
                delegates=(LOOKUP,),
            )
    assert out.getvalue().count("copilot defines no subagents at launch") == 1


_POWERS = """\
config_version = 2

[profiles.top]
cli = "fake"

[profiles.top.powers.max]
model = "big"
effort = "high"

[profiles.top.delegates.lookup]
model = "small"

[profiles.named]
cli = "fake"

[profiles.named.powers.max]
model = "big"

[profiles.named.delegates.advisor]
model = "chosen"

[profiles.bare]
cli = "fake"

[profiles.bare.delegates.lookup]
model = "small"
"""


@pytest.fixture
def powers_config(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(_POWERS)
    monkeypatch.setenv(config.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(config.LEGACY_CONFIG_PATH_ENV, raising=False)
    return path


def test_the_advisor_defaults_to_the_max_tier_model(powers_config):
    picked = {d.name: d for d in resolve_delegates_for("fake", "top")}
    assert list(picked) == ["lookup", "advisor"]
    assert (picked["advisor"].model, picked["advisor"].effort) == ("big", "high")
    assert picked["advisor"].read_only


def test_an_explicit_advisor_wins_over_the_default(powers_config):
    picked = {d.name: d for d in resolve_delegates_for("fake", "named")}
    assert picked["advisor"].model == "chosen"


def test_no_default_advisor_when_the_cli_takes_no_subagents(powers_config):
    assert [d.name for d in resolve_delegates_for("fake", "top", subagents=False)] == ["lookup"]


def test_no_max_model_means_no_advisor(powers_config):
    assert [d.name for d in resolve_delegates_for("fake", "bare")] == ["lookup"]
