"""Shared fixtures for the coder port's tests.

Same shape as the author suite: nodes run for real against a temp git repo pinned as
`AGENT_REPO_DIR`, and only the agent turn is ever scripted. What is different here is
that two of the three small flows reach *outside* the filesystem — `genesis` shells out
to `farrier`, `fix_ci` talks to GitHub — so each of those gets one named seam rather than
a patched resolver, and every node above and below the seam is the real one.

`env` and `drive_flow` are here rather than in each flow's module because all three flows
drive the same way, and a per-module copy is three places for the writer's resume shape
to drift.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Workflow
from workhorse.pyflow import engine as pyflow_engine
from workhorse.pyflow.driver import Resume, drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import coder


@pytest.fixture
def logger() -> logging.Logger:
    """The `logger` every node takes first. Diagnostics only — nothing asserts on it."""
    return logging.getLogger("test.coder")


@pytest.fixture
def git() -> Callable[..., subprocess.CompletedProcess]:
    """`git` in a directory, checked. Every repo in these tests is a real one."""

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
    """A real git repo with one commit, pinned as the consuming repo for the test.

    `genesis` is the one flow that does *not* use it — it creates its own target — but it
    still wants `AGENT_REPO_DIR` off the developer's own checkout, which is what this
    fixture guarantees for every test that requests it.
    """
    root = tmp_path / "acme"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# acme\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    monkeypatch.setenv("AGENT_REPO_DIR", str(root))
    return root


@pytest.fixture
def write() -> Callable[[Path, str], Path]:
    """Write text to a path, creating parents. Returns the path, for one-liners."""

    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_json(write: Callable[[Path, str], Path]) -> Callable[[Path, Any], Path]:
    """The same, for the workspace file, the dream inbox and the ledger."""

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
    """A `RunEnv` for a fresh run, or a resumed one when handed a run directory.

    `nodes` is left `None`, which tells the engine to trust the `@blueprint.node` stamp on
    the function rather than to look the name up in a registry. That is what lets a flow
    be driven end to end before `coder/workflow.py` exists — the registry is the entry
    point's business, not the flow's.

    `workflow_dir` is the **coder** package, not the flow's module directory, because
    `handoff` subscopes the writer and not the environment: a sub-flow's prompt paths
    resolve against the parent package exactly as they do in a real run.
    """

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
            config=RunConfig(backend_factory=lambda cli=None: None),
        )

    return _env


@pytest.fixture
def drive_flow() -> Callable[..., Any]:
    """`drive`, with the agent seam swapped for the duration of the call.

    The seam is patched where the engine reads it — `pyflow.engine.agent_runner.run_agent`
    — so the whole `agent()` path above it (prompt resolution, the reply schema, the
    recorded turn) is the real one and only the model call is scripted.
    """

    def _drive(flow: Workflow, run_env: RunEnv, agent: Any, resume: Resume | None = None) -> Any:
        real = pyflow_engine.agent_runner.run_agent
        pyflow_engine.agent_runner.run_agent = agent
        try:
            return drive(flow, run_env, resume)
        finally:
            pyflow_engine.agent_runner.run_agent = real

    return _drive


@pytest.fixture
def ran() -> Callable[[RunEnv, Any], bool]:
    """Whether a node recorded an output in this run — i.e. whether its state ran.

    A skipped branch is invisible in the result value, so the artifacts are what prove it:
    `run_dir/<node>/output.json` exists only for a node that actually ran.
    """

    def _ran(run_env: RunEnv, node: Any) -> bool:
        name = getattr(node, "__name__", str(node))
        return (run_env.writer.run_dir / name / "output.json").is_file()

    return _ran


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """An author for every commit, including the ones a node makes in a repo it created.

    `genesis_git_init` runs `git init` and `git commit` in a directory of its own making,
    so there is no `git config user.email` for it to inherit and no fixture that could
    have set one. On a machine with no global identity the commit fails, the node reports
    `initial commit failed`, and genesis fails for a reason that has nothing to do with
    the port. The environment variables are set rather than a global config, so the suite
    never writes to the developer's own git configuration.
    """
    for key, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def _no_inherited_workspace(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The two resolvers that read the ambient environment, unset for every test.

    `resolve_workspace` reads `CODER_WORKSPACE` and `find_docs_root` reads
    `CODER_DOCS_PATH`, and both take precedence over the `AGENT_REPO_DIR` the `repo`
    fixture pins. A developer running the suite with either exported would have `fix_ci`
    iterate their real repos and `dream` write into their real docs tree. Each test that
    wants one sets it.
    """
    monkeypatch.delenv("CODER_WORKSPACE", raising=False)
    monkeypatch.delenv("CODER_DOCS_PATH", raising=False)
    yield
