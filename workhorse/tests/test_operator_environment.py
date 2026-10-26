"""A turn never loads less of the operator's environment than an interactive session of its CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from workhorse.runner.backends import operator_config_dirs
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
