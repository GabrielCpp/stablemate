"""Tests for kit.leased_env.scoped_env: the one write-access to os.environ this package allows."""
from __future__ import annotations

import os

import pytest

from workhorse_workflows.kit.leased_env import child_env, scoped_env, scoped_envs

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


def test_scoped_envs_sets_every_name_for_the_block_and_clears_them_after():
    with scoped_envs({_NAME: "one", _NAME + "_2": "two"}):
        assert os.environ[_NAME] == "one"
        assert os.environ[_NAME + "_2"] == "two"

    assert _NAME not in os.environ
    assert _NAME + "_2" not in os.environ


def test_child_env_is_none_without_an_override():
    assert child_env(None) is None
    assert child_env({}) is None


def test_child_env_lays_the_override_over_the_inherited_environment():
    with scoped_env("STABLEMATE_TEST_INHERITED_VAR", "kept"):
        built = child_env({_NAME: "override"})

    assert built is not None
    assert built[_NAME] == "override"
    assert built["STABLEMATE_TEST_INHERITED_VAR"] == "kept"
