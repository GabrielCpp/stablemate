"""Project inference from the working directory."""

from __future__ import annotations

from pathlib import Path

from saddlebag.context import infer_project


def test_infers_the_git_repo_name(tmp_path: Path):
    repo = tmp_path / "checkout-web"
    (repo / ".git").mkdir(parents=True)
    assert infer_project(repo) == "checkout-web"


def test_is_stable_from_a_subdirectory(tmp_path: Path):
    repo = tmp_path / "stablemate"
    nested = repo / "saddlebag" / "saddlebag"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    # Deep inside the repo, the answer is still the repo, not the subdir.
    assert infer_project(nested) == "stablemate"


def test_a_git_worktree_file_also_counts(tmp_path: Path):
    """git worktrees use a `.git` *file*, not a directory."""
    repo = tmp_path / "worktree-repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    assert infer_project(repo) == "worktree-repo"


def test_falls_back_to_the_directory_name_outside_a_repo(tmp_path: Path):
    plain = tmp_path / "just-a-folder"
    plain.mkdir()
    assert infer_project(plain) == "just-a-folder"


def test_the_nearest_repo_wins(tmp_path: Path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / ".git").mkdir()
    (inner / ".git").mkdir()
    assert infer_project(inner) == "inner"
