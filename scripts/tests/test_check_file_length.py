"""What `check_file_length.py` counts, and what it leaves alone."""

from __future__ import annotations

from pathlib import Path

import check_file_length
import strict_scope
from conftest import strict_repo


def _length_problems(repo: Path, ceilings: dict[str, int] | None = None) -> list[str]:
    scope = strict_scope.load(repo)
    return check_file_length.length_problems(
        repo, scope, check_file_length.repo_files(repo), ceilings or {}
    )


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


def test_a_new_long_file_outside_the_strict_scope_fails(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "long.py").write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo) == ["pkg/loose/long.py: 50 lines, over the 10-line limit"]


def test_a_long_file_that_is_not_python_is_not_counted(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "strict" / "notes.md").write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo) == []


def test_vendored_and_plan_files_are_not_counted(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    for rel in ("pkg/loose/_vendor/copy.py", "docs/plans/old/workflow.py"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo) == []


def test_a_frozen_file_at_its_ceiling_passes(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "old.py").write_text(_lines(50), encoding="utf-8")
    assert _length_problems(repo, {"pkg/loose/old.py": 50}) == []


def test_a_frozen_file_that_grows_fails(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "old.py").write_text(_lines(51), encoding="utf-8")
    assert _length_problems(repo, {"pkg/loose/old.py": 50}) == [
        "pkg/loose/old.py: 51 lines, over its 50-line ceiling"
    ]


def test_a_frozen_file_that_shrinks_a_lot_must_lower_its_ceiling(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "old.py").write_text(_lines(20), encoding="utf-8")
    assert _length_problems(repo, {"pkg/loose/old.py": 50}) == [
        "pkg/loose/old.py: 20 lines, lower its ceiling from 50 to 20"
    ]


def test_a_frozen_file_that_shrinks_a_little_passes(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "old.py").write_text(_lines(25), encoding="utf-8")
    assert _length_problems(repo, {"pkg/loose/old.py": 50}) == []


def test_a_frozen_file_that_shrinks_to_the_limit_must_leave_the_list(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "loose" / "old.py").write_text(_lines(10), encoding="utf-8")
    assert _length_problems(repo, {"pkg/loose/old.py": 20}) == [
        "pkg/loose/old.py: 10 lines, now within the 10-line limit, "
        "remove it from [check-file-length.ceilings]"
    ]


def test_a_strict_path_may_not_hold_a_ceiling(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    (repo / "pkg" / "strict" / "long.py").write_text(_lines(12), encoding="utf-8")
    assert _length_problems(repo, {"pkg/strict/long.py": 12}) == [
        "pkg/strict/long.py: under the strict scope, remove it from [check-file-length.ceilings]",
        "pkg/strict/long.py: 12 lines, over the 10-line limit",
    ]


def test_a_ceiling_for_a_deleted_file_fails(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path, max_lines=10)
    assert _length_problems(repo, {"pkg/loose/gone.py": 50}) == [
        "pkg/loose/gone.py: listed in [check-file-length.ceilings] but no such file, remove it"
    ]
