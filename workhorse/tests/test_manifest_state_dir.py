"""The run reads farrier's context manifest from the per-repo state folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workhorse._vendor.stablemate_core.base_cache import CACHE_DIR_ENV
from workhorse.manifest import load_context_manifest


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "cache"
    monkeypatch.setenv(CACHE_DIR_ENV, str(cache))
    monkeypatch.delenv("AGENT_CONTEXT_DIR", raising=False)
    monkeypatch.setenv("AGENT_CLI", "claude")
    repo = tmp_path / "acme"
    repo.mkdir()
    (repo / "agents.yml").write_text("repo:\n  name: acme-api\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_REPO_DIR", str(repo))
    return repo


def _write(tmp_path: Path, name: str, file: str, values: dict) -> None:
    folder = tmp_path / "cache" / "farrier" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / file).write_text(json.dumps({"vars": values}), encoding="utf-8")


def test_reads_the_plain_manifest_from_the_state_dir(repo, tmp_path):
    _write(tmp_path, "acme-api", "agents-context.json", {"who": "plain"})

    assert load_context_manifest(None).values["vars"] == {"who": "plain"}


def test_a_per_cli_manifest_wins(repo, tmp_path):
    _write(tmp_path, "acme-api", "agents-context.json", {"who": "plain"})
    _write(tmp_path, "acme-api", "agents-context.claude.json", {"who": "claude"})

    assert load_context_manifest(None).values["vars"] == {"who": "claude"}


def test_without_a_configured_name_the_folder_name_is_used(repo, tmp_path):
    (repo / "agents.yml").write_text("agents:\n  claude: true\n", encoding="utf-8")
    _write(tmp_path, "acme", "agents-context.json", {"who": "folder"})

    assert load_context_manifest(None).values["vars"] == {"who": "folder"}


def test_a_staged_context_dir_wins_in_a_container(repo, tmp_path, monkeypatch):
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "agents-context.json").write_text(
        json.dumps({"vars": {"who": "staged"}}), encoding="utf-8"
    )
    monkeypatch.setenv("AGENT_CONTEXT_DIR", str(staged))

    assert load_context_manifest(None).values["vars"] == {"who": "staged"}


def test_no_manifest_is_an_empty_context(repo):
    assert not load_context_manifest(None).present
