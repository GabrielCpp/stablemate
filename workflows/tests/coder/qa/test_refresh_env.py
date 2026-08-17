"""Tests for the `refresh_env` mint step: `_read_manifest` and `_mint_qa_secret` in
`coder.qa.nodes.qa`.

A short-lived credential (a Firebase ID token, say) goes stale between QA-plan
authoring and the run that actually spends it — see that module's docstrings. These
cover the manifest half of the contract: no `refresh_env` block is a no-op, a
declared one runs its `mint` recipe and hands back its stdout, and every way that
recipe can misbehave (missing keys, a non-zero exit, empty output, a timeout) comes
back as a non-empty `error` rather than a token — the shape `run_qa_plan` turns into
a `blocked` result instead of running the plan against a stale or absent secret.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from workhorse_workflows.coder.qa.nodes.qa import _mint_qa_secret, _read_manifest

_LOGGER = logging.getLogger("test")


def _write_manifest(root: Path, body: str) -> None:
    (root / "qa-stack.yml").write_text(body, encoding="utf-8")


def test_read_manifest_is_empty_when_the_file_is_absent(tmp_path: Path):
    assert _read_manifest(tmp_path / "qa-stack.yml", _LOGGER) == {}


def test_read_manifest_is_empty_for_malformed_yaml(tmp_path: Path):
    _write_manifest(tmp_path, "not: [valid\n")
    assert _read_manifest(tmp_path / "qa-stack.yml", _LOGGER) == {}


def test_mint_qa_secret_is_a_noop_without_a_refresh_env_block():
    var, token, error = _mint_qa_secret({}, Path("."), _LOGGER)
    assert (var, token, error) == ("", "", "")


def test_mint_qa_secret_rejects_a_non_mapping_refresh_env():
    var, token, error = _mint_qa_secret({"refresh_env": "nope"}, Path("."), _LOGGER)
    assert var == ""
    assert token == ""
    assert "mapping" in error


@pytest.mark.parametrize(
    "refresh_env",
    [
        {"mint": "echo token"},
        {"var": "QA_EDITOR_ID_TOKEN"},
        {"var": "", "mint": "echo token"},
        {"var": "QA_EDITOR_ID_TOKEN", "mint": ""},
    ],
)
def test_mint_qa_secret_requires_both_var_and_mint(refresh_env: dict[str, str]):
    var, token, error = _mint_qa_secret({"refresh_env": refresh_env}, Path("."), _LOGGER)
    assert token == ""
    assert "var" in error or "mint" in error


def test_mint_qa_secret_runs_the_recipe_and_returns_its_stdout(tmp_path: Path):
    manifest = {
        "refresh_env": {
            "var": "QA_EDITOR_ID_TOKEN",
            "mint": "printf '%s' fresh-token-value",
        }
    }
    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)
    assert var == "QA_EDITOR_ID_TOKEN"
    assert token == "fresh-token-value"
    assert error == ""


def test_mint_qa_secret_runs_the_recipe_relative_to_the_repo_root(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / "mint.sh"
    script.write_text("#!/usr/bin/env bash\nprintf '%s' from-repo-relative-script\n")
    script.chmod(0o755)
    manifest = {"refresh_env": {"var": "TOKEN", "mint": "scripts/mint.sh"}}

    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)

    assert var == "TOKEN"
    assert token == "from-repo-relative-script"
    assert error == ""


def test_mint_qa_secret_reports_a_nonzero_exit_as_an_error(tmp_path: Path):
    manifest = {
        "refresh_env": {
            "var": "QA_EDITOR_ID_TOKEN",
            "mint": "echo boom >&2; exit 1",
        }
    }
    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)
    assert var == "QA_EDITOR_ID_TOKEN"
    assert token == ""
    assert "boom" in error


def test_mint_qa_secret_reports_empty_stdout_as_an_error(tmp_path: Path):
    manifest = {"refresh_env": {"var": "QA_EDITOR_ID_TOKEN", "mint": "true"}}
    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)
    assert var == "QA_EDITOR_ID_TOKEN"
    assert token == ""
    assert "no output" in error


def test_mint_qa_secret_reports_a_timeout_as_an_error(tmp_path: Path):
    manifest = {
        "refresh_env": {
            "var": "QA_EDITOR_ID_TOKEN",
            "mint": "sleep 5",
            "timeout": 0.1,
        }
    }
    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)
    assert var == "QA_EDITOR_ID_TOKEN"
    assert token == ""
    assert "could not be run" in error


def test_mint_qa_secret_never_lets_the_recipe_raise_out(monkeypatch, tmp_path: Path):
    def _boom(*args, **kwargs):
        raise OSError("no such executable")

    monkeypatch.setattr(subprocess, "run", _boom)
    manifest = {"refresh_env": {"var": "QA_EDITOR_ID_TOKEN", "mint": "does-not-matter"}}

    var, token, error = _mint_qa_secret(manifest, tmp_path, _LOGGER)

    assert var == "QA_EDITOR_ID_TOKEN"
    assert token == ""
    assert "could not be run" in error
