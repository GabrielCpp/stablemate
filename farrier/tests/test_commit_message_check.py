from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "base-library/library/policies/git/commit-and-push/scripts/check_commit_message.py"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "farrier").mkdir()
    (tmp_path / "farrier" / "x.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "farrier/x.py"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", "--no-verify"],
        check=True,
    )
    return tmp_path


def check(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    path = repo / "MSG"
    path.write_text(message, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], cwd=repo, capture_output=True, text=True
    )


def test_a_conventional_subject_scoped_to_a_tracked_directory_passes(repo: Path):
    assert check(repo, "feat(farrier): add a thing\n\nBody.\n").returncode == 0


def test_an_extra_scope_passes(repo: Path):
    assert check(repo, "build(deps): bump a pin\n").returncode == 0


def test_a_free_form_subject_is_refused(repo: Path):
    result = check(repo, "Added a thing\n")

    assert result.returncode == 1
    assert result.stderr


def test_an_unknown_scope_is_refused(repo: Path):
    result = check(repo, "fix(nowhere): mend a thing\n")

    assert result.returncode == 1
    assert "nowhere" in result.stderr


def test_a_merge_subject_passes(repo: Path):
    assert check(repo, "Merge branch 'x'\n").returncode == 0
