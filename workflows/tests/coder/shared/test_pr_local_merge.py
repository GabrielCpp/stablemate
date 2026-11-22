"""The PR boundary merges a repo with no origin locally, leaves one with an origin alone, and lands the book branch after the code."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse._vendor.stablemate_core import book_branch

from workhorse_workflows.coder.main.nodes import pr
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
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-token")
    config = tmp_path / "home-config.toml"
    config.write_text(
        f'worktree_dir = "{tmp_path / "worktrees"}"\n' + config.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return {"api": api, "artifacts": artifacts}


def _run(api: Path) -> None:
    open_run_prs(
        logging.getLogger("test.pr"), "feat/x", "main", repo_dir=str(api), workspace="acme"
    )


def _book_branch(git: Git, api: Path, name: str) -> Path:
    book = book_branch.open_book_branch(api, "feat/x")
    (book / name).write_text(name, encoding="utf-8")
    git(book, "add", "-A")
    git(book, "commit", "-qm", f"add {name}")
    return book


def test_a_local_merge_of_the_code_lands_the_book_by_rebase_with_no_merge_commit(
    workspace: dict[str, Path], git: Git
) -> None:
    artifacts = workspace["artifacts"]
    _commit_on(git, workspace["api"], "feat/x", "svc.py", create=True)
    book = _book_branch(git, workspace["api"], "epic.md")
    _commit_on(git, artifacts, "main", "other.md", create=False)

    _run(workspace["api"])

    assert git(artifacts, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert (artifacts / "epic.md").is_file() and (artifacts / "other.md").is_file()
    assert git(artifacts, "rev-list", "--merges", "--count", "main").stdout.strip() == "0"
    assert not book.exists()
    assert git(artifacts, "branch", "--list", "feat/x").stdout.strip() == ""


def test_a_code_pr_keeps_a_local_book_branch_and_names_the_land_command(
    workspace: dict[str, Path],
    tmp_path: Path,
    git: Git,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = workspace["api"]
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(api, "remote", "add", "origin", str(bare))
    _commit_on(git, api, "feat/x", "svc.py", create=True)
    book = _book_branch(git, api, "epic.md")
    monkeypatch.setattr(pr, "_push_and_pr", lambda *args: ("opened", "https://example.com/pr/1"))
    monkeypatch.setattr(pr, "resolve_github_token", lambda path: "token")
    caplog.set_level(logging.INFO)

    _run(api)

    assert book.is_dir()
    assert git(workspace["artifacts"], "branch", "--list", "feat/x").stdout.strip() != ""
    assert not (workspace["artifacts"] / "epic.md").exists()
    assert "ostler book land --branch feat/x" in caplog.text


def test_an_artifacts_repo_with_origin_and_token_gets_its_book_pr(
    workspace: dict[str, Path], tmp_path: Path, git: Git, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, artifacts = workspace["api"], workspace["artifacts"]
    for repo, name in ((api, "api.git"), (artifacts, "artifacts.git")):
        bare = tmp_path / name
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(repo, "remote", "add", "origin", str(bare))
    _commit_on(git, api, "feat/x", "svc.py", create=True)
    book = _book_branch(git, api, "epic.md")
    recorded: list[tuple[Path, str, str]] = []

    def record(logger, path, branch, base, *rest):
        recorded.append((Path(path).resolve(), branch, base))
        return "opened", "https://example.com/pr/1"

    monkeypatch.setattr(pr, "_push_and_pr", record)
    monkeypatch.setattr(pr, "resolve_github_token", lambda path: "token")

    _run(api)

    assert (book.resolve(), "feat/x", "main") in recorded
    assert (api.resolve(), "feat/x", "main") in recorded
    assert book.is_dir()


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
