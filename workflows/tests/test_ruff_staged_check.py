"""The python-lint policy's commit check refuses a staged Python file that fails ruff."""
from __future__ import annotations

import subprocess
from pathlib import Path

from _staged import run_check, stage
from workhorse.testing import make_git_repo

SCRIPT = Path(__file__).resolve().parents[2] / "base-library/library/policies/repo/python-lint/scripts/check_ruff_staged.py"


def _check(root: Path, *pathspecs: str) -> subprocess.CompletedProcess[str]:
    return run_check(SCRIPT, root, *pathspecs)


def test_a_staged_file_with_an_unused_import_is_refused_and_named(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "services/x/journey.py", "import os\n")

    ran = _check(root)

    assert ran.returncode == 1
    assert "services/x/journey.py:1:8: F401" in ran.stderr


def test_a_clean_staged_file_passes(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "a.py", "x = 1\n")

    assert _check(root).returncode == 0


def test_the_check_reads_the_index_not_the_working_tree(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "a.py", "x = 1\n")
    _ = (root / "a.py").write_text("import os\n", encoding="utf-8")

    assert _check(root).returncode == 0


def test_a_file_outside_the_pathspecs_is_not_checked(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "other/a.py", "import os\n")
    stage(root, "docs/b.py", "x = 1\n")

    assert _check(root, "docs").returncode == 0
