"""Shared fixtures for the coder port's tests."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Workflow
from workhorse.pyflow.driver import Resume, drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import coder


@pytest.fixture
def logger() -> logging.Logger:
    """The `logger` every node takes first."""
    return logging.getLogger("test.coder")


@pytest.fixture
def git() -> Callable[..., subprocess.CompletedProcess]:
    """`git` in a directory, checked."""

    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        )

    return _git


@pytest.fixture
def repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    """A real git repo with one commit, pinned as the consuming repo for the test."""
    root = tmp_path / "acme"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# acme\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def write() -> Callable[[Path, str], Path]:
    """Write text to a path, creating parents."""

    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_json(write: Callable[[Path, str], Path]) -> Callable[[Path, Any], Path]:
    """The same, for the workspace file and the other JSON artifacts a run leaves."""

    def _write_json(path: Path, data: Any) -> Path:
        return write(path, json.dumps(data, indent=2) + "\n")

    return _write_json


@pytest.fixture
def read_json() -> Callable[[Path], Any]:
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    return _read_json


@pytest.fixture
def env(tmp_path: Path) -> Callable[..., RunEnv]:
    """A `RunEnv` for a fresh run, or a resumed one when handed a run directory."""

    def _env(*, run_dir: Path | None = None, name: str = "coder") -> RunEnv:
        writer = (
            ArtifactWriter.resume(run_dir)
            if run_dir is not None
            else ArtifactWriter(name, tmp_path / "runs", run_id="t")
        )
        return RunEnv(
            writer=writer,
            workflow_dir=Path(coder.__file__).parent,
            session_id_path=writer.run_dir / ".session_id",
            config=RunConfig(),
        )

    return _env


@pytest.fixture
def ambient() -> dict[str, str]:
    """The run's ambient path inputs, as the operator would have passed them."""
    return {}


@pytest.fixture
def drive_flow(ambient: dict[str, str]) -> Callable[..., Any]:
    """`drive`, with the scripted agent handed to the run rather than patched in."""

    def _drive(flow: Workflow, run_env: RunEnv, agent: Any, resume: Resume | None = None) -> Any:
        for field, value in ambient.items():
            if field in type(flow).model_fields and not getattr(flow, field):
                setattr(flow, field, value)
        return drive(flow, replace(run_env, agent_runner=StubRunner(agent)), resume)

    return _drive


@pytest.fixture
def ran() -> Callable[[RunEnv, Any], bool]:
    """Whether a node recorded an output in this run — i.e."""

    def _ran(run_env: RunEnv, node: Any) -> bool:
        name = getattr(node, "__name__", str(node))
        return (run_env.writer.run_dir / name / "output.json").is_file()

    return _ran


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """An author for every commit, including the ones a node makes in a repo it created."""
    for key, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)

