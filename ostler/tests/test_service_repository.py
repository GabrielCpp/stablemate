"""The service id rule: one `docs/services/<service>/` folder cites the code of one repository."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import write
from ostler import doctor
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import load

CONCEPT = """\
---
type: concept
slug: {slug}
title: {slug}
---
# {slug}

- code: `{ref}`

A concept.
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    api = tmp_path / "code" / "api-service"
    web = tmp_path / "code" / "web-app"
    write(api / "src/x.py", "def create_invoice():\n    return 1\n")
    write(web / "src/y.py", "def render():\n    return 1\n")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{api}", "{web}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    return Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()


def page(artifacts: Path, service: str, slug: str, ref: str) -> None:
    write(artifacts / f"docs/services/{service}/concepts/{slug}.md", CONCEPT.format(slug=slug, ref=ref))


def spanning(artifacts: Path) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(artifacts)).findings if f.code == "service-spans-repositories"]


def test_a_service_citing_two_repositories_is_an_error_naming_both(workspace: Path) -> None:
    page(workspace, "billing", "invoice", "repo://api-service/src/x.py::create_invoice")
    page(workspace, "billing", "screen", "repo://web-app/src/y.py::render")

    found = spanning(workspace)

    assert len(found) == 1
    assert found[0].severity == "error"
    assert "billing" in found[0].message
    assert "api-service" in found[0].message and "web-app" in found[0].message


def test_a_service_citing_one_repository_is_clean(workspace: Path) -> None:
    page(workspace, "billing", "invoice", "repo://api-service/src/x.py::create_invoice")
    page(workspace, "billing", "totals", "repo://api-service/src/x.py")
    page(workspace, "storefront", "screen", "repo://web-app/src/y.py::render")

    assert spanning(workspace) == []
