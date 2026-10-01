from __future__ import annotations

import subprocess
from pathlib import Path

from workhorse.testing import make_git_repo

from workhorse_workflows.okf_book.main.nodes.source_view import build_source_view, source_view_folder
from workhorse_workflows.okf_book.main.nodes.turn_budget import folder_tokens


def test_the_source_copy_holds_the_product_files_at_their_paths_and_no_test(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo")
    (repo / "api" / "mocks").mkdir(parents=True)
    _ = (repo / "api" / "main.go").write_text("a" * 40, encoding="utf-8")
    _ = (repo / "api" / "main_test.go").write_text("b" * 4000, encoding="utf-8")
    _ = (repo / "api" / "mocks" / "repository.go").write_text("c" * 4000, encoding="utf-8")
    _ = (repo / "api" / "stale.go").write_text("d", encoding="utf-8")
    _ = build_source_view(repo, "api")
    (repo / "api" / "stale.go").unlink()

    view = build_source_view(repo, "api")

    assert view == source_view_folder(repo, "api")
    assert sorted(path.relative_to(view).as_posix() for path in view.rglob("*") if path.is_file()) == ["main.go"]
    assert (folder_tokens(view), folder_tokens(repo / "api")) == (10, 2010)


def test_the_source_copy_sits_inside_a_linked_worktree_and_git_sees_no_change(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo")
    worktree = tmp_path / "worktrees" / "repo"
    _ = subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "book", str(worktree)], check=True)
    (worktree / "api").mkdir()
    _ = (worktree / "api" / "main.go").write_text("a", encoding="utf-8")
    _ = subprocess.run(["git", "-C", str(worktree), "add", "api"], check=True)
    _ = subprocess.run(["git", "-C", str(worktree), "commit", "-q", "-m", "api"], check=True)

    view = build_source_view(worktree, "api")

    assert view.is_relative_to(worktree)
    assert (view / "main.go").is_file()
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain"], check=True, capture_output=True, text=True
    )
    assert status.stdout == ""



def test_a_copy_of_the_repository_root_holds_no_copy_of_itself(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo")
    (repo / "api").mkdir()
    _ = (repo / "api" / "main.go").write_text("a", encoding="utf-8")
    _ = build_source_view(repo, ".")

    view = build_source_view(repo, ".")

    copied = sorted(path.relative_to(view).as_posix() for path in view.rglob("*") if path.is_file())
    assert "api/main.go" in copied
    assert not [path for path in copied if path.startswith(".okf-book-source")]
