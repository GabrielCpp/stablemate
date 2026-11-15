"""Tests for kit.credentials: the GitHub token comes from the saddlebag secret agents.yml names."""
from __future__ import annotations

import pytest
from saddlebag import SecretUnavailable
from workhorse._vendor.stablemate_core.config import ConfigError
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.kit import credentials
from workhorse_workflows.kit.credentials import github_token


def _manifest(root, body: str) -> None:
    (root / "agents.yml").write_text(body)


def test_the_token_comes_from_the_saddlebag_secret_agents_yml_names(tmp_path, monkeypatch):
    _manifest(tmp_path, "workflow:\n  githubTokenSecret: github-token\n")
    asked: list[str] = []

    def fake(name: str, field: str = "password") -> str:
        asked.append(name)
        return "stored-token"

    monkeypatch.setattr(credentials, "secret_value", fake)

    assert github_token(tmp_path) == "stored-token"
    assert asked == ["github-token"]


@pytest.mark.parametrize("body", ["", "workflow:\n  prompts: {}\n"])
def test_with_no_secret_configured_there_is_no_token_even_when_gh_token_is_set(tmp_path, monkeypatch, body):
    _manifest(tmp_path, body)
    monkeypatch.setenv("GH_TOKEN", "ambient-token")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-token")
    monkeypatch.setattr(credentials, "secret_value", lambda *a, **k: pytest.fail("saddlebag must not be asked"))

    assert github_token(tmp_path) == ""


def test_a_configured_secret_saddlebag_cannot_produce_fails_the_run_with_its_text(tmp_path, monkeypatch):
    _manifest(tmp_path, "workflow:\n  githubTokenSecret: github-token\n")

    def refuse(name: str, field: str = "password") -> str:
        raise SecretUnavailable("no such secret: github-token")

    monkeypatch.setattr(credentials, "secret_value", refuse)

    with pytest.raises(WorkflowFailed, match="no such secret: github-token"):
        github_token(tmp_path)


def test_a_manifest_that_fails_validation_stops_the_token_lookup_instead_of_using_a_fallback(tmp_path):
    """A broken manifest once read as absent, so a repo's own token setting was dropped for a fallback."""
    _manifest(tmp_path, "workflow:\n  githubTokenSecret: [not, a, name]\n")

    with pytest.raises(ConfigError, match="workflow.githubTokenSecret"):
        github_token(tmp_path)


def test_a_manifest_that_still_says_github_token_env_stops_the_token_lookup(tmp_path):
    _manifest(tmp_path, "workflow:\n  githubTokenEnv: GH_TOKEN\n")

    with pytest.raises(ConfigError, match="workflow.githubTokenEnv is gone"):
        github_token(tmp_path)
