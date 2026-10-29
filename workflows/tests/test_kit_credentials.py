"""Tests for kit.credentials.scoped_env: the one write-access to os.environ this package allows."""
from __future__ import annotations

import os

import pytest
from workhorse._vendor.stablemate_core.config import ConfigError

from workhorse_workflows.kit.credentials import github_token, scoped_env

_NAME = "STABLEMATE_TEST_SCOPED_ENV_VAR"


@pytest.fixture(autouse=True)
def _clean_env():
    previous = os.environ.pop(_NAME, None)
    yield
    if previous is None:
        os.environ.pop(_NAME, None)
    else:
        os.environ[_NAME] = previous


def test_scoped_env_sets_the_value_for_the_block_and_clears_it_after():
    assert _NAME not in os.environ

    with scoped_env(_NAME, "fresh-token"):
        assert os.environ[_NAME] == "fresh-token"

    assert _NAME not in os.environ


def test_scoped_env_restores_a_prior_value_rather_than_clearing_it():
    os.environ[_NAME] = "prior-value"

    with scoped_env(_NAME, "fresh-token"):
        assert os.environ[_NAME] == "fresh-token"

    assert os.environ[_NAME] == "prior-value"


def test_scoped_env_restores_even_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with scoped_env(_NAME, "fresh-token"):
            assert os.environ[_NAME] == "fresh-token"
            raise RuntimeError("callee blew up")

    assert _NAME not in os.environ


def test_a_manifest_that_fails_validation_stops_the_token_lookup_instead_of_using_a_fallback(tmp_path):
    """A broken manifest once read as absent, so a repo's own token env was dropped for GITHUB_TOKEN."""
    (tmp_path / "agents.yml").write_text("workflow:\n  githubTokenEnv: [not, a, name]\n")

    with pytest.raises(ConfigError, match="workflow.githubTokenEnv"):
        github_token(tmp_path)
