"""What `check_file_length.py` counts, and what it leaves alone."""

from __future__ import annotations

from pathlib import Path

import check_file_length
import strict_scope
from conftest import strict_repo


def _length_problems(repo: Path) -> list[str]:
    scope = strict_scope.load(repo)
    return check_file_length.length_problems(repo, scope, check_file_length.scoped_files(repo, scope))


def _lines(count: int) -> str:
    return "".join(f"VALUE_{index} = {index}\n" for index in range(count))


def test_a_file_at_the_limit_passes(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "strict" / "full.py").write_text(_lines(10), encoding="utf-8")
    assert _length_problems(repo) == []


def test_an_untracked_file_over_the_limit_fails(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "strict" / "long.py").write_text(_lines(11), encoding="utf-8")
    assert _length_problems(repo) == ["pkg/strict/long.py: 11 lines, over the 10-line limit"]


def test_a_long_file_outside_the_scope_is_not_counted(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "long.py").write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo) == []


def test_a_long_file_that_is_not_python_is_not_counted(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "strict" / "notes.md").write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo) == []
