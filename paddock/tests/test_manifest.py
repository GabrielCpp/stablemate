"""The stat manifest that holds a score function to read-only."""

from __future__ import annotations

from pathlib import Path

from paddock import manifest


def test_manifest_diff_names_what_changed(repo: Path) -> None:
    before = manifest.manifest(repo)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert manifest.diff_manifests(before, manifest.manifest(repo)) == ["added new.txt"]


def test_manifest_diff_names_a_removal_and_an_edit(repo: Path) -> None:
    before = manifest.manifest(repo)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    middle = manifest.manifest(repo)
    (repo / "new.txt").unlink()
    assert manifest.diff_manifests(middle, manifest.manifest(repo)) == ["removed new.txt"]
    assert manifest.diff_manifests(before, manifest.manifest(repo)) == []


def test_manifest_ignores_the_paddock_folder(repo: Path) -> None:
    before = manifest.manifest(repo)
    (repo / ".paddock").mkdir()
    (repo / ".paddock" / "note").write_text("x", encoding="utf-8")
    assert manifest.diff_manifests(before, manifest.manifest(repo)) == []
