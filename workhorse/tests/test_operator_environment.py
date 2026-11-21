"""A turn never loads less of the operator's environment than an interactive session of its CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from workhorse.config_run import AgentResilience
from workhorse.runner import process
from workhorse.runner.backends import AgentProfile, operator_config_dirs
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.registry import backend_names

COVERED_BACKENDS = {"claude", "codex", "opencode", "copilot", "cline"}

CONFIG_DIRS = {
    "claude": (".claude",),
    "codex": (".codex", ".agents"),
    "opencode": (".config/opencode", ".claude/skills", ".agents/skills"),
}


@pytest.mark.parametrize("backend", backend_names())
def test_a_turn_never_loads_less_of_the_operators_environment_than_its_cli_does(backend: str) -> None:
    """A new backend fails here until its environment test exists and its name joins the covered set."""
    assert backend in COVERED_BACKENDS


@pytest.mark.parametrize("harness", sorted(CONFIG_DIRS))
def test_the_operator_config_dirs_are_the_existing_ones_the_cli_loads_from(
    harness: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert operator_config_dirs(harness) == ()
    for name in CONFIG_DIRS[harness]:
        (tmp_path / name).mkdir(parents=True)
    assert operator_config_dirs(harness) == tuple(tmp_path / name for name in CONFIG_DIRS[harness])


def test_the_operator_config_dirs_follow_the_cli_s_own_override_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for variable, harness, directory in (
        ("CLAUDE_CONFIG_DIR", "claude", tmp_path / "claude"),
        ("CODEX_HOME", "codex", tmp_path / "codex"),
        ("XDG_CONFIG_HOME", "opencode", tmp_path / "xdg"),
    ):
        target = directory / "opencode" if harness == "opencode" else directory
        target.mkdir(parents=True)
        monkeypatch.setenv(variable, str(directory))
        assert operator_config_dirs(harness) == (target,)


def _claude_launch(agent: AgentProfile | None) -> tuple[list[str], dict[str, str]]:
    seen: dict[str, Any] = {}

    def fake_stream(cmd, node_id, timeout, on_line, **options):
        seen["cmd"] = cmd
        seen["env"] = options.get("env_extra") or {}
        return False, 0

    with patch.object(process, "stream_subprocess", fake_stream):
        try:
            ClaudeBackend().run_turn(
                "P", "n", None, "sonnet", timeout=60, resilience=AgentResilience(), agent=agent
            )
        except Exception:
            pass
    return list(seen["cmd"]), dict(seen["env"])


def _flag_values(cmd: list[str], flag: str) -> list[str]:
    values = []
    for arg in cmd[cmd.index(flag) + 1 :]:
        if arg.startswith("--"):
            break
        values.append(arg)
    return values


def test_a_plain_claude_turn_narrows_nothing_the_operator_loads() -> None:
    cmd, env = _claude_launch(AgentProfile(name="owner"))
    for flag in ("--setting-sources", "--strict-mcp-config", "--tools", "--mcp-config"):
        assert flag not in cmd
    assert _flag_values(cmd, "--disallowedTools") == [
        "Workflow", "Monitor", "ScheduleWakeup", "CronCreate", "RemoteTrigger",
    ]
    assert not {name for name in env if name in ("HOME", "CLAUDE_CONFIG_DIR") or name.startswith("XDG_")}


def test_a_profile_that_turns_every_tool_off_is_the_one_deliberate_narrowing() -> None:
    cmd, _ = _claude_launch(AgentProfile(name="judge", tools={"*": False}))
    assert "--tools" in cmd
    assert "--strict-mcp-config" in cmd
