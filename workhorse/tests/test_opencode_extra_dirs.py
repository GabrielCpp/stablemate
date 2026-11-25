"""OpenCode has no ``--add-dir``, so an extra directory reaches it through the injected config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from workhorse.config_run import AgentResilience
from workhorse.runner.backends import turn
from workhorse.runner.backends.opencode import OpenCodeBackend, _config_content


def _extra(tmp_path: Path, *, skills: tuple[str, ...] = (), agents_md: bool = False) -> Path:
    root = tmp_path / "extra"
    root.mkdir()
    for folder in skills:
        (root / folder).mkdir(parents=True)
    if agents_md:
        (root / "AGENTS.md").write_text("rules\n")
    return root


def _config(operator: str | None, add_dirs: list[Path], model: str | None = None) -> dict[str, Any]:
    content = _config_content(operator, model, None, None, [str(path) for path in add_dirs])
    assert content is not None
    return json.loads(content)


def test_an_extra_dirs_skill_folders_and_agents_file_reach_the_config(tmp_path: Path) -> None:
    root = _extra(tmp_path, skills=(".claude/skills", ".agents/skills"), agents_md=True)
    config = _config(None, [root])
    assert config["skills"]["paths"] == [str(root / ".claude/skills"), str(root / ".agents/skills")]
    assert config["instructions"] == [str(root / "AGENTS.md")]


def test_a_missing_skill_folder_and_a_missing_agents_file_are_skipped(tmp_path: Path) -> None:
    root = _extra(tmp_path, skills=(".opencode/skills",))
    config = _config(None, [root])
    assert config["skills"]["paths"] == [str(root / ".opencode/skills")]
    assert "instructions" not in config


def test_an_extra_dir_with_nothing_to_load_adds_no_config(tmp_path: Path) -> None:
    assert _config_content(None, None, None, None, [str(_extra(tmp_path))]) is None


def test_the_operators_small_model_survives_and_their_lists_keep_our_entries(tmp_path: Path) -> None:
    root = _extra(tmp_path, skills=(".claude/skills",), agents_md=True)
    operator = json.dumps(
        {"small_model": "operator/small", "skills": {"paths": ["/ops/skills"]}, "instructions": ["/ops/RULES.md"]}
    )
    config = _config(operator, [root], model="turn/model")
    assert config["small_model"] == "operator/small"
    assert config["skills"]["paths"] == ["/ops/skills", str(root / ".claude/skills")]
    assert config["instructions"] == ["/ops/RULES.md", str(root / "AGENTS.md")]


def test_the_turn_model_pin_and_the_extra_dir_keys_share_one_config(tmp_path: Path) -> None:
    root = _extra(tmp_path, agents_md=True)
    config = _config(None, [root], model="turn/model")
    assert config == {"small_model": "turn/model", "instructions": [str(root / "AGENTS.md")]}


def test_the_built_command_line_never_passes_pure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake(cmd: list[str], node_id: str, timeout: float, stdin_data: Any, on_event: Any, **kwargs: Any) -> turn.TurnState:
        captured["cmd"] = cmd
        return turn.TurnState(result_text="X", session_id="s")

    monkeypatch.setattr(OpenCodeBackend, "harness_env", lambda self: {})
    resilience = AgentResilience()
    OpenCodeBackend(fake).run_turn(
        "P", "n", None, "m", timeout=resilience.result_timeout_s, resilience=resilience, add_dirs=[str(_extra(tmp_path))]
    )
    assert captured["cmd"][0] == "opencode"
    assert "--pure" not in captured["cmd"]
