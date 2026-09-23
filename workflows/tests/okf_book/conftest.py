"""Fixtures that copy a paddock app into a scratch git repo and drive the workflow over it."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from okf_book.support import APPS, ListingRunner, driver, git
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.work_set import WorkSet
from workhorse_workflows.okf_book.workflow import OkfBook, workflow


@pytest.fixture(autouse=True)
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)


@pytest.fixture
def app(tmp_path: Path) -> Callable[[str], Path]:
    """A committed copy of a paddock fixture app, so the tracked fixture is never written."""

    def _app(name: str) -> Path:
        repo = tmp_path / name
        _ = shutil.copytree(APPS / name, repo, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        _ = git(repo, "init", "-q")
        _ = git(repo, "add", "-A")
        _ = git(repo, "commit", "-q", "-m", "fixture")
        return repo

    return _app


def _env(tmp_path: Path, runner: ListingRunner, run_id: str) -> RunEnv:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id=run_id)
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
    )
    return replace(env, agent_runner=runner)


@pytest.fixture
def run_book(tmp_path: Path) -> Callable[[OkfBook, ListingRunner], WorkSet]:
    """Drive the workflow to its end with a scripted listing turn."""

    run_ids: list[str] = []

    def _run(flow: OkfBook, runner: ListingRunner) -> WorkSet:
        run_ids.append(f"t{len(run_ids)}")
        result = driver(flow, _env(tmp_path, runner, run_ids[-1]))
        assert isinstance(result, WorkSet)
        return result

    return _run

