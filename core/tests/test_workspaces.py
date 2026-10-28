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


def _git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


def _repo(path):
    path.mkdir(parents=True)
    _git(path, "init", "--quiet")
    _git(path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "--allow-empty", "-m", "x", "--quiet")
    return path


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    return (tmp_path / "artifacts").resolve()


def test_docs_home_is_none_without_workspaces(tmp_path, artifacts, cfg_file):
    assert cfgmod.docs_home(_repo(tmp_path / "api-service")) is None


def test_docs_home_is_the_artifacts_dir_from_a_member_folder(tmp_path, artifacts, cfg_file):
    api = _repo(tmp_path / "api-service")
    (api / "src").mkdir()
    cfg_file.write_text(f'[workspaces]\nacme = ["{api}"]\n')

    assert cfgmod.docs_home(api) == artifacts
    assert cfgmod.docs_home(api / "src") == artifacts


def test_docs_home_is_the_artifacts_dir_from_a_worktree_of_a_member(tmp_path, artifacts, cfg_file):
    api = _repo(tmp_path / "api-service")
    cfg_file.write_text(f'[workspaces]\nacme = ["{api}"]\n')
    tree = tmp_path / "elsewhere" / "api-service-feature"
    _git(api, "worktree", "add", "--quiet", "-b", "feature", str(tree))

    assert cfgmod.docs_home(tree) == artifacts


def test_docs_home_is_the_artifacts_dir_from_a_clone_of_a_member_url(tmp_path, artifacts, cfg_file):
    bare = tmp_path / "remote" / "api-service.git"
    bare.mkdir(parents=True)
    _git(bare, "init", "--bare", "--quiet")
    clone = tmp_path / "clones" / "api-service"
    subprocess.run(["git", "clone", "--quiet", bare.as_uri(), str(clone)], check=True, capture_output=True)
    cfg_file.write_text(
        f'[workspaces]\nacme = [{{ path = "{tmp_path}/missing", name = "api-service", url = "{bare.as_uri()}/" }}]\n'
    )

    assert cfgmod.docs_home(clone) == artifacts


def test_a_url_match_ignores_a_trailing_git_suffix(tmp_path, artifacts, cfg_file):
    clone = _repo(tmp_path / "api-service")
    _git(clone, "remote", "add", "origin", "https://example.com/acme/api-service")
    cfg_file.write_text(
        f'[workspaces]\nacme = [{{ path = "{tmp_path}/missing", url = "https://example.com/acme/api-service.git" }}]\n'
    )

    assert cfgmod.docs_home(clone) == artifacts


def test_docs_home_is_none_for_a_repository_in_no_workspace(tmp_path, artifacts, cfg_file):
    api = _repo(tmp_path / "api-service")
    other = _repo(tmp_path / "web-app")
    cfg_file.write_text(f'[workspaces]\nacme = ["{api}"]\n')

    assert cfgmod.docs_home(other) is None


def test_a_folder_outside_any_repository_matches_by_path_only(tmp_path, artifacts, cfg_file):
    plain = tmp_path / "plain"
    plain.mkdir()
    cfg_file.write_text(f'[workspaces]\nacme = ["{plain}"]\n')

    assert cfgmod.repository_identity(plain) == cfgmod.RepositoryIdentity(plain.resolve(), plain.resolve())
    assert cfgmod.docs_home(plain) == artifacts
    assert cfgmod.docs_home(tmp_path) is None


def test_overlapping_workspaces_share_one_docs_home(tmp_path, artifacts, cfg_file):
    api = _repo(tmp_path / "api-service")
    cfg_file.write_text(f'[workspaces]\nacme = ["{api}"]\nglobex = ["{api}"]\n')

    assert cfgmod.docs_home(api) == artifacts
    assert cfgmod.workspace_members() == {"api-service": api.resolve()}


def test_one_member_name_bound_to_two_folders_raises(tmp_path, cfg_file):
    cfg_file.write_text('[workspaces]\nacme = ["/a/api-service"]\nglobex = ["/b/api-service"]\n')

    with pytest.raises(cfgmod.ConfigError, match=r"api-service.*/a/api-service.*/b/api-service"):
        cfgmod.workspace_members()
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.docs_home(tmp_path)


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
