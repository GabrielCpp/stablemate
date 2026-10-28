"""The docs repo and the code workspace every `fix` flow test drains against."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from workhorse._vendor.stablemate_core import config as core_config

from coder.fix.scripted import RECORD, TEXT


@pytest.fixture
def artifacts() -> Path:
    """The artifacts repo the register lives in, with one commit so a close has a parent."""
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


@pytest.fixture
def docs(repo: Path, artifacts: Path) -> Path:
    """The docs repo, with one drainable `qa` record on the register and nothing else."""
    filing = Ostler(repo).file_record(
        repo="api", area="widget", pattern="paginate", summary=TEXT, filed_by="qa", record_id=RECORD
    )
    assert filing.record is not None, filing.message
    (repo / "docs" / "services").mkdir(parents=True, exist_ok=True)
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """Two real code repos and the named workspace that lists them, outside the docs tree."""
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    name_workspace(repos)
    return repos
