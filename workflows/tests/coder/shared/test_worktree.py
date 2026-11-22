"""The folders no proof is reopened by: the artifacts dir, and nothing the book owns."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.worktree import is_product, not_product_roots


@pytest.fixture
def artifacts(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The artifacts dir inside the one repo, as the paddock layout puts it."""
    inside = repo / "artifacts"
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(inside))
    return inside


def test_the_artifacts_dir_is_the_only_folder_that_is_not_product(repo: Path, artifacts: Path) -> None:
    assert not_product_roots(str(repo)) == [artifacts.resolve()]


def test_a_service_book_file_is_product_and_a_spec_file_is_not(repo: Path, artifacts: Path) -> None:
    excluded = not_product_roots(str(repo))

    assert is_product(repo, "services/app/journeys/x.py", excluded)
    assert not is_product(repo, "artifacts/specs/STORY-1/qa_plan.py", excluded)
    assert not is_product(repo, "test-results/trace.zip", excluded)


def test_the_artifacts_book_worktree_is_not_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git
) -> None:
    artifacts = tmp_path / "book-home"
    artifacts.mkdir()
    git(artifacts, "init", "-q", "-b", "main")
    (artifacts / "README.md").write_text("book\n", encoding="utf-8")
    git(artifacts, "add", "-A")
    git(artifacts, "commit", "-qm", "Initial commit")
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(artifacts))
    code = tmp_path / "acme"
    code.mkdir()
    git(code, "init", "-q", "-b", "feat/one")
    (code / "README.md").write_text("acme\n", encoding="utf-8")
    git(code, "add", "-A")
    git(code, "commit", "-qm", "Initial commit")
    cut = tmp_path / "book-home-feat-one"
    git(artifacts, "worktree", "add", "-q", "-b", "feat/one", str(cut))

    excluded = not_product_roots(str(code))

    assert cut.resolve() in excluded
    assert artifacts.resolve() in excluded
    assert not is_product(code, f"../{cut.name}/services/api/service.py", excluded)
    assert is_product(code, "src/app.py", excluded)
