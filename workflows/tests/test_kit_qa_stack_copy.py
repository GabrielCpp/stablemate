"""Tests for kit.qa.runner on a repo whose book declares its stack in `stack.yml`."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from _workspace import lay_out, run_git
from ostler.environments import leases, runtime
from ostler.qa import addresses, runbook
from ostler.qa.outcome import QaOutcome

from workhorse_workflows.coder.shared.stack import stack_target
from workhorse_workflows.kit.qa import runner

LOG = logging.getLogger(__name__)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "env-home"))
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    book = root / "services" / "web"
    (book / "ops").mkdir(parents=True)
    (book / "ops" / "web.yml.j2").write_text("image: nginx\n", encoding="utf-8")
    (book / "ops" / "stack.yml").write_text(yaml.safe_dump({"services": {
        "web": {"about": "the web app", "define": "web.yml.j2", "address": "web", "port": 80}}}),
        encoding="utf-8")
    return root


def test_a_command_against_the_copy_reads_the_copys_address_book(repo: Path) -> None:
    env = runner.stack_env(repo, near=str(repo / "services" / "web"), lease="story-1")
    assert env[addresses.LEASE_ENV] == "story-1"
    assert env[addresses.BOOK_ENV].endswith(f"acme-story-1/{runtime.ADDRESSES}")


def test_a_run_copy_is_released_and_the_shared_copy_stays(repo: Path) -> None:
    released = runner.release_copy(LOG, repo_dir=str(repo), lease="story-1")
    assert released is not None and released.ok
    assert runner.release_copy(LOG, repo_dir=str(repo)) is None


def test_bring_up_reports_the_copys_front_address(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    near = str(repo / "services" / "web")
    runner.run_qa_plan(LOG, spec_dir="specs/story-1", repo_dir=str(repo), near=near,
                       lease="story-1")
    assert seen["book"] == runner.stack_env(repo, near=near, lease="story-1")[addresses.BOOK_ENV]
    assert seen["book"].endswith(f"acme-story-1/{runtime.ADDRESSES}")


def test_a_story_that_spans_books_scores_against_the_copy_its_bring_up_started(
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
    runner.run_qa_plan(LOG, spec_dir="specs/story-1", repo_dir=str(repo), lease="story-1")
    assert seen["book"] == runner.stack_env(repo, lease="story-1")[addresses.BOOK_ENV]
    assert seen["book"].endswith(f"acme-story-1/{runtime.ADDRESSES}")

def test_bring_up_boots_the_device_beside_the_copy_and_reports_a_failed_install(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leases, "up", lambda *_args, **_kw: QaOutcome(
        True, "stack brought up and healthy at http://localhost:49200",
        {"entry_url": "http://localhost:49200", "address_book": "/copy/addresses.json"}))
    seen: list[object] = []

    def devices(_root: object, *, env: dict[str, str], **_kw: object) -> list[dict[str, object]]:
        seen.append((env["STABLEMATE_LEASE"], Path(env["STABLEMATE_ADDRESS_BOOK"]).name))
        return [{"ready": "no", "failed_step": "install-app", "error": "adb: no devices",
                 "source": "app", "manifest": {"stack_file": "services/app/ops/stack.yml"}}]

    monkeypatch.setattr(runbook, "bring_up_book_devices", devices)
    status = runner.ensure_stack(LOG, repo_dir=str(repo), lease="story-1")
    assert seen == [("story-1", "addresses.json")]
    assert (status.ready, status.failed_step) == ("no", "install-app")
    assert status.notes == ("Device step 'install-app' failed: adb: no devices. Repair that step "
                            "under `device:` in `services/app/ops/stack.yml`.")
    monkeypatch.setattr(runbook, "bring_up_book_devices", lambda *_a, **_kw: [{"ready": "yes"}])
    assert runner.ensure_stack(LOG, repo_dir=str(repo), lease="story-1").ready == "yes"


def test_a_label_reaches_the_ostler_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    class _Ostler:
        def __init__(self, _root: Path) -> None:
            pass

        def qa_run(self, *_args: object, **kw: object) -> QaOutcome:
            seen.append(kw.get("label"))
            return QaOutcome(True, "passed", {"status": "passed"})

    monkeypatch.setattr(runner, "Ostler", _Ostler)
    runner.run_qa_plan(LOG, spec_dir="specs/story-1", repo_dir=str(repo), lease="story-1")
    runner.run_qa_plan(LOG, spec_dir="specs/story-1", repo_dir=str(repo), lease="story-1",
                       label="docs-exercise")
    assert seen == [None, "docs-exercise"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_a_plan_run_removes_the_files_it_left_and_keeps_the_rest(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.rmtree(repo / ".git")
    _git(repo, "init", "-q")
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo / "agent-wrote.txt").write_text("the story's work\n", encoding="utf-8")
    spec = repo / "specs" / "story-1"
    spec.mkdir(parents=True)

    class _Ostler:
        def __init__(self, _root: Path) -> None:
            pass

        def qa_run(self, *_args: object, **_kw: object) -> QaOutcome:
            (repo / "book-scratch" / "seed").mkdir(parents=True)
            (repo / "book-scratch" / "seed" / "input.json").write_text("{}", encoding="utf-8")
            (repo / "inputs.json").write_text("{}", encoding="utf-8")
            (repo / "nested").mkdir()
            _git(repo / "nested", "init", "-q")
            (repo / "nested" / "seed.txt").write_text("seed\n", encoding="utf-8")
            (repo / "build").mkdir()
            (repo / "build" / "out.txt").write_text("ignored\n", encoding="utf-8")
            (spec / "qa").mkdir()
            (spec / "qa" / "qa-run.ndjson").write_text("{}\n", encoding="utf-8")
            return QaOutcome(True, "passed", {"status": "passed"})

    monkeypatch.setattr(runner, "Ostler", _Ostler)
    runner.run_qa_plan(LOG, spec_dir=str(spec), repo_dir=str(repo), lease="story-1")
    assert not (repo / "inputs.json").exists()
    assert not (repo / "book-scratch").exists()
    assert not (repo / "nested").exists()
    assert (repo / "agent-wrote.txt").is_file()
    assert (repo / "build" / "out.txt").is_file()
    assert (spec / "qa" / "qa-run.ndjson").is_file()


def test_a_book_with_a_stack_file_brings_its_stack_copy_up(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    leased: list[str] = []

    def up(_root: Path, **kw: object) -> QaOutcome:
        leased.append(str(kw["lease"]))
        return QaOutcome(True, "stack brought up and healthy at http://localhost:49200",
                         {"entry_url": "http://localhost:49200"})

    monkeypatch.setattr(leases, "up", up)
    status = runner.ensure_stack(LOG, repo_dir=str(repo), lease="story-1")
    assert (status.ready, status.entry_url, leased) == ("yes", "http://localhost:49200", ["story-1"])


def _stack_beside(root: Path, *names: str) -> None:
    for name in names:
        stack = root / "services" / name / "ops" / "stack.yml"
        stack.parent.mkdir(parents=True, exist_ok=True)
        stack.write_text("services: {}\n", encoding="utf-8")


def test_the_one_named_service_with_a_stack_file_picks_its_book(tmp_path: Path) -> None:
    _stack_beside(tmp_path, "api")

    assert runner.story_near(tmp_path, ["api"]) == str(tmp_path / "services" / "api")


def test_two_named_services_with_stack_files_pick_no_book(tmp_path: Path) -> None:
    _stack_beside(tmp_path, "api", "web")

    assert runner.story_near(tmp_path, ["api", "web"]) == ""


def test_no_named_service_picks_no_book(tmp_path: Path) -> None:
    _stack_beside(tmp_path, "api")

    assert runner.story_near(tmp_path, []) == ""


def test_a_named_service_without_a_stack_file_picks_no_book(tmp_path: Path) -> None:
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "api" / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")

    assert runner.story_near(tmp_path, ["api"]) == ""


def test_no_stack_file_is_unneeded_not_a_runbook_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "env-home"))
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    (root / "services" / "api").mkdir(parents=True)
    (root / "services" / "api" / "service.py").write_text("SERVICE = 1\n", encoding="utf-8")

    status = runner.ensure_stack(LOG, repo_dir=str(root), lease="story-1")

    assert status.ready == "unneeded", status
    assert "ops/stack.yml" in status.notes


def test_in_a_workspace_the_stack_target_is_the_artifacts_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "env-home"))
    laid = lay_out(tmp_path, run_git)
    config = tmp_path / "home-config.toml"
    config.write_text(f'[workspaces]\nacme = ["{laid.api}", "{laid.web}"]\n', encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    for base in (laid.artifacts, laid.api):
        stack = base / "services" / "api" / "ops" / "stack.yml"
        stack.parent.mkdir(parents=True)
        stack.write_text(yaml.safe_dump({"services": {}}), encoding="utf-8")

    target = stack_target(LOG, "S", "l", repo_dir=str(laid.api), services=["api"])

    assert target.near == str(laid.artifacts / "services" / "api")
