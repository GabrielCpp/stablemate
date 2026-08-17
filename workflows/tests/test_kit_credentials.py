"""Tests for kit.credentials.scoped_env: the one write-access to os.environ this
package allows.

A minted secret (a QA token freshly signed against a local auth emulator, say) must
reach a callee that reads `os.environ` itself, without ever becoming a node's return
value — see the module docstring. These tests are the contract that write is scoped:
set for the block, restored exactly afterward, on both the happy path and an
exception, whether or not the name held a prior value.
"""
from __future__ import annotations

import os

import pytest

from workhorse_workflows.kit.credentials import scoped_env

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
