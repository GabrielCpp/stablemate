"""The python-lint policy's commit check refuses a staged Python file that fails ty or basedpyright."""
from __future__ import annotations

import subprocess
from pathlib import Path

from _staged import run_check, stage
from workhorse.testing import make_git_repo

SCRIPT = Path(__file__).resolve().parents[2] / "base-library/library/policies/repo/python-lint/scripts/check_types_staged.py"

NONE_KEY = """\
VALUES: dict[str, str] = {}


def lookup(key: str | None) -> str:
    return VALUES[key]
"""


def _check(root: Path, *pathspecs: str) -> subprocess.CompletedProcess[str]:
    return run_check(SCRIPT, root, *pathspecs)


def test_a_staged_file_with_a_none_key_lookup_is_refused_and_named(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "services/x/actions.py", NONE_KEY)

    ran = _check(root)

    assert ran.returncode == 1
    assert "services/x/actions.py:5" in ran.stderr
    assert "ty" in ran.stderr
    assert "basedpyright" in ran.stderr


def test_a_clean_staged_file_passes(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "lib/typed.py", "def one() -> int:\n    return 1\n")

    assert _check(root).returncode == 0


def test_the_check_reads_the_index_not_the_working_tree(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "lib/typed.py", "def one() -> int:\n    return 1\n")
    _ = (root / "lib/typed.py").write_text(NONE_KEY, encoding="utf-8")
    ran = _check(root)
    assert ran.returncode == 0, ran.stderr


def test_a_file_outside_the_pathspecs_is_not_checked(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    stage(root, "other/a.py", NONE_KEY)
    stage(root, "docs/b.py", "x = 1\n")

    assert _check(root, "docs").returncode == 0
