"""A run inside a named workspace reads the artifacts repo's docs and resolves refs against the members."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import write
from ostler import doctor
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


def test_doctor_from_a_member_reads_the_artifacts_docs_and_resolves_against_the_member(workspace):
    write(
        workspace["artifacts"] / "docs/services/billing/concepts/invoice.md",
        CONCEPT.format(ref="repo://api-service/src/x.py::create_invoice"),
    )

    graph = load(workspace["api"])
    report = doctor.run(graph)

    assert graph.root == workspace["artifacts"]
    assert graph.ui_nodes
    codes = {finding.code for finding in report.findings}
    assert not codes & {"dangling-code-ref", "missing-code-symbol", "unreachable-citation"}
    assert "unstamped-citation" in codes


def test_a_symbol_missing_in_the_member_is_an_error(workspace):
    write(
        workspace["artifacts"] / "docs/services/billing/concepts/invoice.md",
        CONCEPT.format(ref="repo://api-service/src/x.py::nope"),
    )

    report = doctor.run(load(workspace["api"]))

    assert "missing-code-symbol" in {finding.code for finding in report.findings}


def test_an_explicit_checkout_beats_the_member(workspace, tmp_path):
    other = tmp_path / "elsewhere"
    write(other / "src/x.py", "def other():\n    return 1\n")
    write(
        workspace["artifacts"] / "docs/services/billing/concepts/invoice.md",
        CONCEPT.format(ref="repo://api-service/src/x.py::create_invoice"),
    )

    report = doctor.run(load(workspace["api"]), checkouts={"api-service": other})

    assert "missing-code-symbol" in {finding.code for finding in report.findings}
