"""Tests for kit.workspace.resolve_workspace's single-repo fallback branch."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from workhorse_workflows.kit.paths import find_docs_root
from workhorse_workflows.kit.workspace import _git_network_command, resolve_workspace


def test_resolve_workspace_uses_the_repo_dir_argument_over_cwd():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
        repo_dir = Path(tmp) / "acme"
        repo_dir.mkdir()

        with patch("workhorse_workflows.kit.workspace.Path.cwd", return_value=Path(elsewhere)):
            repos = resolve_workspace(repo_dir=str(repo_dir))

        assert "acme" in repos
        assert repos["acme"]["path"] == str(repo_dir.resolve())


def test_resolve_workspace_falls_back_to_cwd_without_a_repo_dir():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "acme"
        repo_dir.mkdir()

        with patch("workhorse_workflows.kit.workspace.Path.cwd", return_value=repo_dir):
            repos = resolve_workspace()

        assert "acme" in repos
        assert repos["acme"]["path"] == str(repo_dir.resolve())


def test_a_repo_named_in_its_agents_yml_answers_to_that_name():
    """A checkout under another directory name, such as a worktree, keeps the name farrier installs its skills under."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "acme-worktree"
        repo_dir.mkdir()
        (repo_dir / "agents.yml").write_text("repo:\n  name: Globex_App\n", encoding="utf-8")

        repos = resolve_workspace(repo_dir=str(repo_dir))

        assert list(repos) == ["globex-app"]


def test_a_repo_with_no_name_in_its_agents_yml_is_named_by_its_directory():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "Acme_Web"
        repo_dir.mkdir()
        (repo_dir / "agents.yml").write_text("repo:\n  support_email: team@example.com\n", encoding="utf-8")

        repos = resolve_workspace(repo_dir=str(repo_dir))

        assert list(repos) == ["acme-web"]


def _home_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: dict[str, Path]) -> None:
    config = tmp_path / "home-config.toml"
    entries = ", ".join(f'{{ path = "{path}", name = "{name}" }}' for name, path in members.items())
    config.write_text(f"[workspaces]\nacme = [{entries}]\n", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def test_a_named_workspace_resolves_to_its_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    api = tmp_path / "api-service"
    web = tmp_path / "web-app"
    api.mkdir()
    web.mkdir()
    (web / "agents.yml").write_text("template:\n  stack: web\n", encoding="utf-8")
    _home_config(tmp_path, monkeypatch, {"api-service": api, "web-app": web})

    repos = resolve_workspace("acme", repo_dir=str(tmp_path / "elsewhere"))

    assert list(repos) == ["api-service", "web-app"]
    assert repos["api-service"]["path"] == str(api.resolve())
    assert repos["web-app"]["template"] == {"stack": "web"}


def test_an_unknown_workspace_name_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _home_config(tmp_path, monkeypatch, {"api-service": tmp_path})

    with pytest.raises(ValueError, match="acme"):
        resolve_workspace("globex")


def test_the_docs_root_is_the_artifacts_dir_while_a_workspace_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "acme"
    repo.mkdir()
    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.delenv("STABLEMATE_WORKSPACE", raising=False)
    assert Path(find_docs_root(str(repo))) == repo.resolve()

    monkeypatch.setenv("STABLEMATE_WORKSPACE", "acme")

    assert Path(find_docs_root(str(repo))).resolve() == artifacts.resolve()


def test_git_network_command_uses_configured_token_env():
    with patch.dict(
        os.environ,
        {"WORKHORSE_GIT_TOKEN": "secret"},
        clear=True,
    ):
        command = _git_network_command("clone", "https://github.com/example/private.git")

    assert command[0:2] == ["git", "-c"]
    assert "credential.helper=" in command[2]
    assert "secret" not in command[2]
    assert "$WORKHORSE_GIT_TOKEN" in command[2]
    assert command[-2:] == ["clone", "https://github.com/example/private.git"]

def test_git_network_command_needs_no_token_for_public_or_local_clone():
    with patch.dict(os.environ, {}, clear=True):
        command = _git_network_command("clone", "/mnt/repo-src")

    assert command == ["git", "clone", "/mnt/repo-src"]


def test_only_base_branch_of_the_repo_section_reaches_the_repo_info(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text(
        "repo:\n  name: acme\n  base_branch: develop\n  qa_mode: gui\n  path: ignored\n",
        encoding="utf-8",
    )

    info = resolve_workspace(repo_dir=str(tmp_path))["acme"]

    assert info["base_branch"] == "develop"
    assert "qa_mode" not in info
    assert "name" not in info
    assert info["path"] == str(tmp_path.resolve())


def test_base_branch_from_repo_reaches_the_pr_lookup(tmp_path: Path) -> None:
    from workhorse_workflows.coder.main.nodes.pr import _repo_base_branch

    (tmp_path / "agents.yml").write_text(
        "repo:\n  name: acme\n  base_branch: release\n", encoding="utf-8"
    )
    repos = resolve_workspace(repo_dir=str(tmp_path))

    assert _repo_base_branch(tmp_path, "acme", repos) == "release"
