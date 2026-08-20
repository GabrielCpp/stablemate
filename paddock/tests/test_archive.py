"""The properties a seed zip rests on: modes, symlinks, reproducibility, safety."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from paddock import archive


def test_roundtrip_preserves_the_executable_bit(repo: Path, tmp_path: Path) -> None:
    # A .git hook or a build script that comes back non-executable makes the unpacked
    # seed behave differently from the tree it was captured from, silently.
    zip_path = archive.create(repo, tmp_path / "seed.zip", prefix=repo.name)
    out = archive.extract(zip_path, tmp_path / "out")
    mode = (out / repo.name / "cmd" / "build.sh").stat().st_mode
    assert stat.S_IMODE(mode) & 0o111


def test_roundtrip_preserves_symlinks(repo: Path, tmp_path: Path) -> None:
    zip_path = archive.create(repo, tmp_path / "seed.zip", prefix=repo.name)
    out = archive.extract(zip_path, tmp_path / "out")
    link = out / repo.name / "latest"
    assert link.is_symlink()
    assert link.readlink() == Path("cmd/build.sh")


def test_roundtrip_preserves_uncommitted_state_and_git(repo: Path, tmp_path: Path) -> None:
    zip_path = archive.create(repo, tmp_path / "seed.zip", prefix=repo.name)
    out = archive.extract(zip_path, tmp_path / "out") / repo.name
    assert (out / ".git" / "HEAD").is_file()
    assert (out / "README.md").read_text(encoding="utf-8") == "acme, edited\n"


def test_identical_trees_hash_identically(repo: Path, tmp_path: Path) -> None:
    # The sha256 in a pointer is a statement about the content. If mtimes leaked into
    # the archive, re-capturing the same tree would produce a different fixture identity.
    first = archive.create(repo, tmp_path / "a.zip", prefix=repo.name)
    out = archive.extract(first, tmp_path / "out")
    second = archive.create(out / repo.name, tmp_path / "b.zip", prefix=repo.name)
    assert archive.digest(first) == archive.digest(second)


def test_empty_directories_survive(repo: Path, tmp_path: Path) -> None:
    (repo / "qa").mkdir()
    zip_path = archive.create(repo, tmp_path / "seed.zip", prefix=repo.name)
    out = archive.extract(zip_path, tmp_path / "out")
    assert (out / repo.name / "qa").is_dir()


def test_junk_is_reported_and_excludable(repo: Path) -> None:
    (repo / "web" / "node_modules").mkdir(parents=True)
    (repo / "dist").mkdir()
    assert archive.junk_in(repo) == ["dist", "web/node_modules"]
    assert archive.junk_in(repo, ("node_modules", "dist")) == []


def test_docs_build_is_not_junk(repo: Path) -> None:
    # `build/` is output at the root and an ordinary source directory anywhere else.
    (repo / "docs" / "build").mkdir(parents=True)
    assert archive.junk_in(repo) == []


def test_extract_refuses_a_member_that_escapes(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as handle:
        handle.writestr("../escaped.txt", "no")
    with pytest.raises(archive.ArchiveError, match="escapes"):
        archive.extract(hostile, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()


def test_manifest_diff_names_what_changed(repo: Path) -> None:
    before = archive.manifest(repo)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert archive.diff_manifests(before, archive.manifest(repo)) == ["added new.txt"]
