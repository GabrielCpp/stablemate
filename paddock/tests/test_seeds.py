"""Capture, verify, unpack — the integrity story a benchmark result rests on."""

from __future__ import annotations

from pathlib import Path

import pytest

from paddock import paths, seeds
from paddock.pointer import Pointer, PointerError


def capture(repo: Path, data_dir: Path, store: Path, **kwargs: object) -> seeds.Captured:
    return seeds.capture(repo, name="acme", data_dir=data_dir, store=store, **kwargs)  # ty: ignore[invalid-argument-type]


def test_capture_writes_a_pointer_and_a_zip(repo: Path, data_dir: Path, store: Path) -> None:
    captured = capture(repo, data_dir, store)
    assert captured.zip_path == paths.seed_zip(store, "acme")
    assert captured.pointer_path == paths.seed_pointer(data_dir, "acme")
    pointer = Pointer.load(captured.pointer_path)
    assert pointer.repo_dir == "acme-api"
    assert pointer.dirty is True
    assert len(pointer.head) == 40
    pointer.verify(captured.zip_path)


def test_capture_refuses_junk_in_the_tree(repo: Path, data_dir: Path, store: Path) -> None:
    (repo / ".venv").mkdir()
    with pytest.raises(seeds.SeedError, match=r"\.venv"):
        capture(repo, data_dir, store)


def test_capture_accepts_junk_that_is_explicitly_excluded(
    repo: Path, data_dir: Path, store: Path
) -> None:
    (repo / ".venv").mkdir()
    captured = capture(repo, data_dir, store, excludes=(".venv",))
    assert captured.zip_path.exists()


def test_capture_refuses_to_replace_a_seed_without_force(
    repo: Path, data_dir: Path, store: Path
) -> None:
    capture(repo, data_dir, store)
    with pytest.raises(seeds.SeedError, match="already exists"):
        capture(repo, data_dir, store)
    assert capture(repo, data_dir, store, force=True).zip_path.exists()


def test_verify_rejects_a_zip_that_drifted(repo: Path, data_dir: Path, store: Path) -> None:
    # A seed that quietly changed is a benchmark whose numbers cannot be attributed.
    captured = capture(repo, data_dir, store)
    captured.zip_path.write_bytes(captured.zip_path.read_bytes() + b"tampered")
    with pytest.raises(PointerError, match="sha256"):
        captured.pointer.verify(captured.zip_path)


def test_unpack_restores_the_captured_directory_name(
    repo: Path, data_dir: Path, store: Path, tmp_path: Path
) -> None:
    # farrier derives generated filenames from the repo basename, so a seed that unpacks
    # under a different name gets skills that dangle.
    captured = capture(repo, data_dir, store)
    out = seeds.unpack(captured.pointer, store=store, dest=tmp_path / "dest", install=False)
    assert out.name == "acme-api"
    assert (out / "README.md").read_text(encoding="utf-8") == "acme, edited\n"


def test_unpack_replaces_a_stale_tree_rather_than_merging(
    repo: Path, data_dir: Path, store: Path, tmp_path: Path
) -> None:
    captured = capture(repo, data_dir, store)
    dest = tmp_path / "dest"
    first = seeds.unpack(captured.pointer, store=store, dest=dest, install=False)
    (first / "left-over.txt").write_text("from an earlier run", encoding="utf-8")
    second = seeds.unpack(captured.pointer, store=store, dest=dest, install=False)
    assert not (second / "left-over.txt").exists()


def test_fetch_without_a_url_or_a_local_zip_is_an_error(
    repo: Path, data_dir: Path, store: Path
) -> None:
    captured = capture(repo, data_dir, store)
    captured.zip_path.unlink()
    with pytest.raises(seeds.SeedError, match="no url"):
        seeds.fetch(captured.pointer, store=store)


def test_non_https_urls_are_refused(repo: Path, data_dir: Path, store: Path) -> None:
    captured = capture(repo, data_dir, store, url="file:///etc/passwd")
    captured.zip_path.unlink()
    with pytest.raises(seeds.SeedError, match="only https"):
        seeds.fetch(captured.pointer, store=store)
