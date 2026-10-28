"""The PR boundary merges a repo with no origin locally and leaves one with an origin alone."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.coder.main.nodes.pr import open_run_prs

Git = Callable[..., subprocess.CompletedProcess]


def _init(git: Git, root: Path) -> Path:
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("# repo\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    return root


def _commit_on(git: Git, root: Path, branch: str, name: str, *, create: bool) -> None:
    git(root, "checkout", "-q", *(["-b"] if create else []), branch)
    (root / name).write_text(name, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", f"add {name}")


@pytest.fixture
def workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    git: Git,
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    api = _init(git, tmp_path / "api-service")
    artifacts = _init(git, tmp_path / "artifacts")
    name_workspace({"api-service": api})
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return {"api": api, "artifacts": artifacts}


def _run(api: Path) -> None:
    open_run_prs(
        logging.getLogger("test.pr"), "feat/x", "main", repo_dir=str(api), workspace="acme"
    )


def test_a_docs_repo_without_origin_fast_forwards_the_run_branch(
    workspace: dict[str, Path], git: Git
) -> None:
    artifacts = workspace["artifacts"]
    _commit_on(git, artifacts, "feat/x", "epic.md", create=True)

    _run(workspace["api"])

    assert git(artifacts, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert (artifacts / "epic.md").is_file()
    assert git(artifacts, "rev-list", "--merges", "--count", "main").stdout.strip() == "0"
    assert git(artifacts, "remote").stdout.strip() == ""


def test_a_diverged_trunk_gets_a_merge_commit(workspace: dict[str, Path], git: Git) -> None:
    artifacts = workspace["artifacts"]
    _commit_on(git, artifacts, "feat/x", "epic.md", create=True)
    _commit_on(git, artifacts, "main", "other.md", create=False)

    _run(workspace["api"])

    assert (artifacts / "epic.md").is_file() and (artifacts / "other.md").is_file()
    assert git(artifacts, "rev-list", "--merges", "--count", "main").stdout.strip() == "1"


def test_a_member_with_an_origin_is_not_merged_locally(
    workspace: dict[str, Path], tmp_path: Path, git: Git
) -> None:
    api = workspace["api"]
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(api, "remote", "add", "origin", str(bare))
    _commit_on(git, api, "feat/x", "svc.py", create=True)

    _run(api)

    git(api, "checkout", "-q", "main")
    assert not (api / "svc.py").exists()
    assert git(bare, "branch", "--list").stdout.strip() == ""
