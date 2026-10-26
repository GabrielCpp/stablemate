"""A `working-directory:` of `repo://<member>/<path>` runs in the workspace member's checkout."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import write
from ostler import doctor
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import load
from ostler.qa import runbook as rb

RUNBOOK = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- entry-url: http://localhost:18084
- health-path: /healthz
- working-directory: {app}

## Steps

### serve

- kind: service
- run: ./serve.sh
- working-directory: {serve}
- health: curl -fsS http://localhost:18084/healthz

### seed-it

- kind: seed
- run: ./seed.sh
- working-directory: {seed}
"""

INHERITING = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- entry-url: http://localhost:18084
- working-directory: repo://api-service/api

## Steps

### serve

- kind: service
- run: ./serve.sh
- health: curl -fsS http://localhost:18084/healthz

### seed-it

- kind: seed
- run: ./seed.sh
"""

SERVER = """---
type: server
title: API
---

# API

- launch: ./serve.sh
- entry-url: http://localhost:3000/
- working-directory: {app}
"""

FIXTURE = """---
type: fixture
title: Seeded acme
---
# Seeded acme

## Steps

### seed-it
- kind: seed
- run: ./seed.sh
- working-directory: {directory}
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    api = tmp_path / "code" / "api-service"
    web = tmp_path / "code" / "web-app"
    write(api / "api/handlers.py", "def list_entries():\n    return []\n")
    write(web / "src/y.py", "def render():\n    return 1\n")
    (api / ".git").mkdir()
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{api}", "{web}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    monkeypatch.setenv(core_config.WORKSPACE_ENV, "acme")
    return {"api": api.resolve(), "web": web.resolve(), "artifacts": artifacts}


def _book(workspace: dict[str, Path], name: str, text: str) -> Path:
    path = workspace["artifacts"] / "docs" / "services" / "app" / "ops" / f"{name}.md"
    write(path, text)
    return workspace["artifacts"]


def test_a_runbook_step_and_the_app_run_in_the_member_checkout(workspace):
    root = _book(workspace, "qa-stack", RUNBOOK.format(
        app="repo://api-service/api", serve="repo://api-service/.", seed="repo://api-service/api"))

    manifest = rb.load_stack(root)

    assert manifest["app_cwd"] == str(workspace["api"] / "api")
    assert manifest["launch_cwd"] == str(workspace["api"])
    assert [s["working-directory"] for s in manifest["seed"]] == [str(workspace["api"] / "api")]


def test_a_step_inherits_a_qualified_runbook_directory(workspace):
    root = _book(workspace, "qa-stack", INHERITING)

    manifest = rb.load_stack(root)

    assert [s["working-directory"] for s in manifest["seed"]] == [str(workspace["api"] / "api")]


def test_a_server_runs_in_the_member_checkout(workspace):
    root = workspace["artifacts"]
    write(root / "docs/services/api/server.md", SERVER.format(app="repo://api-service/api"))

    assert rb.load_stack(root)["app_cwd"] == str(workspace["api"] / "api")


def test_an_unqualified_directory_still_reads_from_the_docs_home(workspace):
    root = workspace["artifacts"]
    write(root / "docs/services/api/server.md", SERVER.format(app="app"))

    assert rb.load_stack(root)["app_cwd"] == str((root / "app").resolve())


def test_a_member_the_workspace_lacks_fails_naming_it_and_the_known_ones(workspace):
    root = workspace["artifacts"]
    write(root / "docs/services/api/server.md", SERVER.format(app="repo://billing/api"))

    with pytest.raises(rb.WorkingDirectoryError) as raised:
        rb.load_stack(root)

    message = str(raised.value)
    assert "billing" in message
    assert "api-service" in message
    assert "web-app" in message


def _directory_findings(workspace: dict[str, Path], directory: str) -> list[doctor.Finding]:
    root = workspace["artifacts"]
    write(root / "docs/services/acme/fixtures/seeded-acme.md", FIXTURE.format(directory=directory))
    return [f for f in doctor.run(load(root)).findings if f.code == "fixture-step-directory"]


def test_a_fixture_step_directory_in_a_member_that_holds_it_is_clean(workspace):
    assert _directory_findings(workspace, "repo://api-service/api") == []


def test_a_fixture_step_directory_a_member_lacks_is_refused(workspace):
    [found] = _directory_findings(workspace, "repo://api-service/missing")

    assert found.severity == "error"
    assert "repo://api-service/missing" in found.message


def test_a_fixture_step_directory_in_an_unknown_member_is_left_to_the_bring_up(workspace):
    assert _directory_findings(workspace, "repo://billing/api") == []
