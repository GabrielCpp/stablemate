"""Named workspaces in the home config, and the artifacts repo a workspace run writes into."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stablemate_core import config as cfgmod


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.WORKSPACE_ENV, raising=False)
    return path


def test_a_workspace_lists_paths_and_inline_tables(cfg_file):
    cfg_file.write_text(
        "[workspaces]\n"
        'acme = ["~/code/api-service", { path = "/srv/Web_App", name = "web", '
        'url = "https://example.com/web-app.git", branch = "dev" }]\n'
    )

    api, web = cfgmod.resolve_workspace("acme")

    assert api == cfgmod.WorkspaceMember(
        "api-service", Path("~/code/api-service").expanduser(), "", ""
    )
    assert web == cfgmod.WorkspaceMember(
        "web", Path("/srv/Web_App"), "https://example.com/web-app.git", "dev"
    )


def test_a_member_without_a_name_gets_its_normalised_basename(cfg_file):
    cfg_file.write_text('[workspaces]\nacme = ["/srv/Web_App.v2"]\n')

    assert cfgmod.resolve_workspace("acme")[0].name == "web-app-v2"


def test_an_unknown_workspace_lists_the_known_ones(cfg_file):
    cfg_file.write_text('[workspaces]\nacme = ["/a"]\nglobex = ["/b"]\n')

    with pytest.raises(ValueError, match="acme, globex"):
        cfgmod.resolve_workspace("initech")


def test_duplicate_member_names_raise(cfg_file):
    cfg_file.write_text('[workspaces]\nacme = ["/a/api-service", "/b/api-service"]\n')

    with pytest.raises(ValueError, match="api-service"):
        cfgmod.resolve_workspace("acme")


def test_an_entry_without_a_path_raises(cfg_file):
    cfg_file.write_text('[workspaces]\nacme = [{ name = "x" }]\n')

    with pytest.raises(cfgmod.ConfigError):
        cfgmod.resolve_workspace("acme")


def test_active_workspace_reads_the_env(monkeypatch):
    monkeypatch.delenv(cfgmod.WORKSPACE_ENV, raising=False)
    assert cfgmod.active_workspace() == ""
    monkeypatch.setenv(cfgmod.WORKSPACE_ENV, "acme")
    assert cfgmod.active_workspace() == "acme"


def test_docs_home_is_the_artifacts_dir_only_in_a_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    monkeypatch.delenv(cfgmod.WORKSPACE_ENV, raising=False)
    assert cfgmod.docs_home(tmp_path) is None

    monkeypatch.setenv(cfgmod.WORKSPACE_ENV, "acme")
    assert cfgmod.docs_home(tmp_path) == (tmp_path / "artifacts").resolve()


def test_ensure_artifacts_repo_inits_ignores_session_folders_and_adds_no_remote(tmp_path, monkeypatch):
    target = tmp_path / "artifacts"
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(target))

    root = cfgmod.ensure_artifacts_repo()

    assert root == target.resolve()
    assert (root / ".git").exists()
    assert (root / ".gitignore").read_text().splitlines() == ["specs/", "scratch/", "researches/"]
    remotes = subprocess.run(
        ["git", "-C", str(root), "remote"], capture_output=True, text=True, check=True
    )
    assert remotes.stdout.strip() == ""


def test_ensure_artifacts_repo_appends_missing_ignores_and_keeps_custom_lines(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    root = cfgmod.ensure_artifacts_repo()
    (root / ".gitignore").write_text("mine\nspecs/\n")

    assert cfgmod.ensure_artifacts_repo() == root
    assert (root / ".gitignore").read_text().splitlines() == [
        "mine", "specs/", "scratch/", "researches/",
    ]
    before = (root / ".gitignore").read_text()
    cfgmod.ensure_artifacts_repo()
    assert (root / ".gitignore").read_text() == before
