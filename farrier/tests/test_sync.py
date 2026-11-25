"""`farrier sync`: the drift check that repairs and stages what it finds."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from repo_install import configured

from farrier import cli


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    skill = root / "library" / "skills" / "demo" / "plain" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: plain\ndescription: a plain skill\n---\n\n# Plain\n\nFirst.\n",
        encoding="utf-8",
    )
    (root / "packs").mkdir()
    return root


@pytest.fixture
def repo(monkeypatch, library: Path, tmp_path: Path) -> Path:
    root = configured(monkeypatch, library, tmp_path)
    git(root, "init", "-q")
    assert cli.main(["install", "--repo", str(root)]) == 0
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--no-verify", "-qm", "init")
    return root


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def drift(library: Path) -> None:
    skill = library / "library" / "skills" / "demo" / "plain" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8").replace("First.", "Second."), encoding="utf-8")


def test_a_clean_tree_passes_in_silence(repo: Path, capsys):
    assert cli.main(["sync", "--repo", str(repo)]) == 0

    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert git(repo, "status", "--porcelain") == ""


def test_drift_is_reinstalled_and_staged(repo: Path, library: Path, capsys):
    drift(library)

    assert cli.main(["sync", "--repo", str(repo)]) == 0

    staged = git(repo, "diff", "--cached", "--name-only").splitlines()
    assert staged and all(path.endswith("SKILL.md") for path in staged)
    assert git(repo, "diff", "--name-only") == ""
    assert "Second." in git(repo, "show", f":{staged[0]}")
    assert f"Staged {len(staged)} regenerated agent files" in capsys.readouterr().err


def test_drift_under_named_paths_is_listed_and_refused(repo: Path, library: Path, capsys):
    drift(library)

    assert cli.main(["sync", "--repo", str(repo), "README.md"]) == 1

    assert git(repo, "diff", "--cached", "--name-only") == ""
    changed = git(repo, "diff", "--name-only").splitlines()
    err = capsys.readouterr().err
    assert changed and all(f"  {path}" in err for path in changed)


def test_a_dirty_unrelated_file_is_left_unstaged(repo: Path, library: Path):
    (repo / "notes.txt").write_text("mine\n", encoding="utf-8")
    drift(library)

    assert cli.main(["sync", "--repo", str(repo)]) == 0

    assert "notes.txt" not in git(repo, "diff", "--cached", "--name-only")
    assert "?? notes.txt" in git(repo, "status", "--porcelain")


def test_a_repo_without_agents_yml_passes(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()

    assert cli.main(["sync", "--repo", str(bare)]) == 0


def test_a_folder_outside_git_is_skipped(monkeypatch, library: Path, tmp_path: Path, capsys):
    """A commit check has nothing to stage where there is no repository."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    folder = configured(monkeypatch, library, tmp_path)

    assert cli.main(["sync", "--repo", str(folder)]) == 0

    assert sorted(p.name for p in folder.iterdir()) == ["agents.yml"]
    assert "not a git repository" in capsys.readouterr().err
