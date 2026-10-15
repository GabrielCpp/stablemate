"""Tests for kit.qa.runner on a repo whose book declares its stack in `stack.yml`."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
import yaml

from ostler import model
from ostler.environments import leases, runtime
from ostler.qa import addresses, runbook
from ostler.qa.outcome import QaOutcome

from workhorse_workflows.kit.qa import runner

LOG = logging.getLogger(__name__)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "env-home"))
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    book = root / "docs" / "features" / "web"
    (book / "ops").mkdir(parents=True)
    (book / "ops" / "web.yml.j2").write_text("image: nginx\n", encoding="utf-8")
    (book / "ops" / "stack.yml").write_text(yaml.safe_dump({"services": {
        "web": {"about": "the web app", "define": "web.yml.j2", "address": "web", "port": 80}}}),
        encoding="utf-8")
    return root


def test_a_command_against_the_copy_reads_the_copys_address_book(repo: Path) -> None:
    env = runner.stack_env(LOG, model.load(repo), near=str(repo / "docs" / "features" / "web"),
                           lease="story-1")
    assert env[addresses.LEASE_ENV] == "story-1"
    assert env[addresses.BOOK_ENV].endswith(f"acme-story-1/{runtime.ADDRESSES}")


def test_a_run_copy_is_released_and_the_shared_copy_stays(repo: Path) -> None:
    released = runner.release_copy(LOG, repo_dir=str(repo), lease="story-1")
    assert released is not None and released.ok
    assert runner.release_copy(LOG, repo_dir=str(repo)) is None


def test_bring_up_reports_the_copys_front_address(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runbook, "has_served_surface", lambda *_args: True)
    monkeypatch.setattr(leases, "up", lambda *_args, **_kw: QaOutcome(
        True, "stack brought up and healthy at http://localhost:49200",
        {"entry_url": "http://localhost:49200"}))
    status = runner.ensure_stack(LOG, repo_dir=str(repo), lease="story-1")
    assert (status.ready, status.entry_url) == ("yes", "http://localhost:49200")
    monkeypatch.setattr(leases, "up", lambda *_args, **_kw: QaOutcome(False, "stack bring-up failed: x"))
    assert runner.ensure_stack(LOG, repo_dir=str(repo), lease="story-1").ready == "no"


def test_the_scored_run_reads_the_address_book_the_copy_wrote(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class _Ostler:
        def __init__(self, _root: Path) -> None:
            pass

        def qa_run(self, *_args: object, **_kw: object) -> QaOutcome:
            seen["book"] = os.environ.get(addresses.BOOK_ENV, "")
            return QaOutcome(True, "passed", {"status": "passed"})

    monkeypatch.setattr(runner, "Ostler", _Ostler)
    near = str(repo / "docs" / "features" / "web")
    runner.run_qa_plan(LOG, spec_dir="docs/specs/story-1", repo_dir=str(repo), near=near,
                       lease="story-1")
    assert seen["book"] == runner.stack_env(LOG, model.load(repo), near=near,
                                            lease="story-1")[addresses.BOOK_ENV]
    assert seen["book"].endswith(f"acme-story-1/{runtime.ADDRESSES}")
