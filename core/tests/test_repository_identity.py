"""A folder's repository identity is asked of git once, and asked again only when what git reads to give it changed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stablemate_core import config as cfgmod


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "init")
    return path


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Every git question the identity sends, with no answer kept from another test."""
    monkeypatch.setattr(cfgmod, "_placed", {})
    calls: list[tuple[str, ...]] = []
    real = cfgmod._git

    def counted(folder: Path, *args: str) -> str | None:
        calls.append(args)
        return real(folder, *args)

    monkeypatch.setattr(cfgmod, "_git", counted)
    return calls


def test_a_second_ask_of_an_unchanged_repository_runs_no_git(tmp_path: Path, asked: list[tuple[str, ...]]):
    api = repo(tmp_path / "api")
    first = cfgmod.repository_identity(api)
    sent = len(asked)
    git(api, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "more")

    assert cfgmod.repository_identity(api) == first
    assert len(asked) == sent


def test_a_folder_that_becomes_a_repository_is_asked_again(tmp_path: Path, asked: list[tuple[str, ...]]):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cfgmod.repository_identity(plain) == cfgmod.RepositoryIdentity(plain.resolve(), plain.resolve())

    git(plain, "init", "-q", "-b", "main")
    git(plain, "remote", "add", "origin", "https://example.com/acme/api-service.git")

    assert cfgmod.repository_identity(plain).origin_url == "https://example.com/acme/api-service.git"


def test_a_folder_under_a_new_repository_is_asked_again(tmp_path: Path, asked: list[tuple[str, ...]]):
    inner = tmp_path / "outer" / "inner"
    inner.mkdir(parents=True)
    assert cfgmod.repository_identity(inner).folder == inner.resolve()

    git(tmp_path / "outer", "init", "-q", "-b", "main")

    assert cfgmod.repository_identity(inner).folder == (tmp_path / "outer").resolve()


def test_a_new_worktree_at_a_folder_asked_before_is_its_own_checkout(tmp_path: Path, asked: list[tuple[str, ...]]):
    api = repo(tmp_path / "api")
    linked = tmp_path / "api-run"
    linked.mkdir()
    assert cfgmod.repository_identity(linked).folder == linked.resolve()
    linked.rmdir()

    git(api, "worktree", "add", "-q", "-b", "run", str(linked))

    assert cfgmod.repository_identity(linked) == cfgmod.RepositoryIdentity(linked.resolve(), api.resolve())


def test_a_changed_origin_is_asked_again(tmp_path: Path, asked: list[tuple[str, ...]]):
    api = repo(tmp_path / "api")
    git(api, "remote", "add", "origin", "https://example.com/acme/api-service.git")
    assert cfgmod.repository_identity(api).origin_url == "https://example.com/acme/api-service.git"

    git(api, "remote", "set-url", "origin", "https://example.com/acme/web-app.git")

    assert cfgmod.repository_identity(api).origin_url == "https://example.com/acme/web-app.git"


def test_a_failed_ask_inside_a_repository_is_not_kept(tmp_path: Path, asked: list[tuple[str, ...]], monkeypatch: pytest.MonkeyPatch):
    api = repo(tmp_path / "api")
    git(api, "remote", "add", "origin", "https://example.com/acme/api-service.git")
    counted = cfgmod._git
    monkeypatch.setattr(cfgmod, "_git", lambda folder, *args: None)
    assert cfgmod.repository_identity(api).origin_url == ""
    monkeypatch.setattr(cfgmod, "_git", counted)

    assert cfgmod.repository_identity(api).origin_url == "https://example.com/acme/api-service.git"
