"""A run inside a named workspace reads the artifacts repo's docs and resolves refs against the members."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import write, write_prefix
from ostler import ids
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import find_root, load

CONCEPT = """\
---
type: concept
slug: invoice
title: Invoice
---
# Invoice

- code: `{ref}`

An invoice.
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    api = tmp_path / "code" / "api-service"
    web = tmp_path / "code" / "web-app"
    write(api / "src/x.py", "def create_invoice():\n    return 1\n")
    write(web / "src/y.py", "def render():\n    return 1\n")
    subprocess.run(["git", "init", "--quiet", str(api)], check=True)
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{api}", "{web}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    return {"api": api, "web": web, "artifacts": artifacts}


def test_find_root_is_the_artifacts_repo_from_inside_a_member(workspace):
    assert find_root(workspace["api"] / "src") == workspace["artifacts"]


def test_find_root_walks_up_from_a_repository_in_no_workspace(workspace, tmp_path, monkeypatch):
    config = tmp_path / "other.toml"
    config.write_text(f'[workspaces]\nacme = ["{workspace["web"]}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))

    assert find_root(workspace["api"] / "src") == workspace["api"].resolve()


def test_a_mint_from_a_member_uses_the_artifacts_repos_prefix(workspace):
    write_prefix(workspace["artifacts"], "ARTI")
    write_prefix(workspace["api"], "MEMB")

    minted = ids.allocate(load(workspace["api"] / "src"))

    assert minted.startswith("ARTI-")
