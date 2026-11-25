"""Path keys of the home config: `~` and environment variables expand when the file is read."""

from __future__ import annotations

import pytest

from stablemate_core import config as cfgmod


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    return path


def test_path_keys_expand_the_home_variable_and_the_tilde(cfg_file, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("WORKSPACE", str(tmp_path / "ws"))
    cfg_file.write_text(
        'config_version = 2\n'
        'library_dir = "$HOME/agent-library"\n'
        'stablemate_dir = "${WORKSPACE}/stablemate"\n'
        'base_dir = "~/base"\n'
        'worktree_dir = "$HOME/worktrees"\n'
        'artifacts_dir = "$HOME/artifacts"\n'
        'paddock_dir = "$HOME/benchmarks"\n'
        '[workspaces]\nacme = ["$HOME/acme"]\n'
    )
    home = cfgmod.load_home_config()
    root = tmp_path / "home"
    assert (home.library_dir, home.stablemate_dir, home.base_dir) == (
        str(root / "agent-library"), str(tmp_path / "ws" / "stablemate"), str(root / "base"))
    assert (home.worktree_dir, home.artifacts_dir, home.paddock_dir) == (
        str(root / "worktrees"), str(root / "artifacts"), str(root / "benchmarks"))
    assert [m.path for m in cfgmod.resolve_workspace("acme")] == [root / "acme"]
    assert "$HOME/agent-library" in cfg_file.read_text()
