"""The artifacts repo, the consuming repo and the drive a `review-debt` test runs against."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _fakes import StubRunner
from ostler import Ostler
from ostler.register import Status
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Workflow
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import review_debt


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)


@pytest.fixture
def artifacts() -> Path:
    """The artifacts repo the register lives in, with one commit so a later commit has a parent."""
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real git repo with one commit, pinned as the consuming repo for the test."""
    root = tmp_path / "acme"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, capture_output=True)
    (root / "README.md").write_text("# acme\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "Initial commit"], cwd=root, check=True, capture_output=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def file_record(repo: Path, artifacts: Path) -> Callable[..., str]:
    """File one record on the register through the producer, and return its id."""

    def _file(record_id: str, *, repo_name: str = "api-service", area: str = "cart", status: Status = "open") -> str:
        filing = Ostler(repo).file_record(
            repo=repo_name,
            area=area,
            pattern="guard-the-total",
            summary=f"summary of {record_id}",
            filed_by="qa",
            record_id=record_id,
            status=status,
        )
        assert filing.record is not None, filing.message
        return record_id

    return _file


@pytest.fixture
def env(tmp_path: Path) -> Callable[..., RunEnv]:
    """A `RunEnv` for a fresh run."""

    def _env(name: str = "review-debt") -> RunEnv:
        writer = ArtifactWriter(name, tmp_path / "runs", run_id="t")
        return RunEnv(
            writer=writer,
            workflow_dir=Path(review_debt.__file__).parent,
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
        )

    return _env


@pytest.fixture
def drive_flow(repo: Path) -> Callable[..., Any]:
    """`drive`, with the scripted agent handed to the run and the consuming repo as its `repo_dir`."""

    def _drive(flow: Workflow, run_env: RunEnv, agent: Any) -> Any:
        flow.repo_dir = str(repo)
        return drive(flow, replace(run_env, agent_runner=StubRunner(agent)))

    return _drive


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test.review_debt")
