"""Tests for `_mint_qa_secrets` in `coder.qa.nodes.qa` — the per-run credential mint.

A short-lived credential goes stale between QA-plan authoring and the run that actually
spends it, so the recipes that produce one live on the book's runbook as `secrets:` and
are run immediately before `qa_run`. These cover that half of the contract: no `secrets:`
is a no-op, a declared one runs its recipe and hands back its stdout, several of them are
minted together (the one-variable ceiling the old `refresh_env` block imposed is gone),
and every way a recipe can misbehave — an empty recipe, a non-zero exit, empty output, a
timeout, an exec failure — comes back as a non-empty `error` and *no* tokens at all,
which is the shape `run_qa_plan` turns into a `blocked` result instead of running the plan
against a stale or absent secret.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from workhorse_workflows.coder.qa.nodes import qa as qa_nodes
from workhorse_workflows.coder.qa.nodes.qa import _mint_qa_secrets

_LOGGER = logging.getLogger("test")


def test_no_secrets_is_a_noop():
    assert _mint_qa_secrets({}, Path("."), _LOGGER) == ({}, "")


def test_a_secret_without_a_recipe_is_an_error():
    minted, error = _mint_qa_secrets({"QA_TOKEN": ""}, Path("."), _LOGGER)
    assert minted == {}
    assert "QA_TOKEN" in error


def test_runs_the_recipe_and_returns_its_stdout(tmp_path: Path):
    minted, error = _mint_qa_secrets(
        {"QA_EDITOR_ID_TOKEN": "printf '%s' fresh-token-value"}, tmp_path, _LOGGER
    )
    assert minted == {"QA_EDITOR_ID_TOKEN": "fresh-token-value"}
    assert error == ""


def test_mints_every_declared_secret(tmp_path: Path):
    """The ceiling that made this rewrite necessary: a run blocked needing two."""
    minted, error = _mint_qa_secrets(
        {"QA_TOKEN": "printf '%s' one", "QA_API_KEY": "printf '%s' two"}, tmp_path, _LOGGER
    )
    assert minted == {"QA_TOKEN": "one", "QA_API_KEY": "two"}
    assert error == ""


def test_runs_the_recipe_relative_to_the_repo_root(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / "mint.sh"
    script.write_text("#!/usr/bin/env bash\nprintf '%s' from-repo-relative-script\n")
    script.chmod(0o755)

    minted, error = _mint_qa_secrets({"TOKEN": "scripts/mint.sh"}, tmp_path, _LOGGER)

    assert minted == {"TOKEN": "from-repo-relative-script"}
    assert error == ""


def test_reports_a_nonzero_exit_as_an_error(tmp_path: Path):
    minted, error = _mint_qa_secrets(
        {"QA_EDITOR_ID_TOKEN": "echo boom >&2; exit 1"}, tmp_path, _LOGGER
    )
    assert minted == {}
    assert "boom" in error


def test_reports_empty_stdout_as_an_error(tmp_path: Path):
    minted, error = _mint_qa_secrets({"QA_EDITOR_ID_TOKEN": "true"}, tmp_path, _LOGGER)
    assert minted == {}
    assert "no output" in error


def test_reports_a_timeout_as_an_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(qa_nodes, "SECRET_MINT_TIMEOUT_S", 0.1)
    minted, error = _mint_qa_secrets({"QA_EDITOR_ID_TOKEN": "sleep 5"}, tmp_path, _LOGGER)
    assert minted == {}
    assert "could not be run" in error


def test_never_lets_the_recipe_raise_out(monkeypatch, tmp_path: Path):
    def _boom(*args, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(subprocess, "run", _boom)

    minted, error = _mint_qa_secrets({"QA_EDITOR_ID_TOKEN": "whatever"}, tmp_path, _LOGGER)

    assert minted == {}
    assert "could not be run" in error


def test_an_earlier_failure_discards_the_tokens_already_minted(tmp_path: Path):
    """A partial set is a run that fails later for a reason the caller was already told."""
    minted, error = _mint_qa_secrets(
        {"GOOD": "printf '%s' ok", "BAD": "exit 3"}, tmp_path, _LOGGER
    )
    assert minted == {}
    assert "BAD" in error
