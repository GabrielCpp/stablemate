"""Capture, verify, unpack — the integrity story a benchmark result rests on."""

from __future__ import annotations

import shutil
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
    assert Pointer.load(captured.pointer_path).excludes == (".venv",)


def test_capture_refuses_to_replace_a_seed_without_force(
    repo: Path, data_dir: Path, store: Path
) -> None:
    capture(repo, data_dir, store)
    with pytest.raises(seeds.SeedError, match="already exists"):
        capture(repo, data_dir, store)
    assert capture(repo, data_dir, store, force=True).zip_path.exists()


def test_a_re_capture_keeps_the_url_and_note_nobody_retyped(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """The two fields a person typed survive a `--force` that re-measures the tree.

    The usual reason to re-capture is that something in the tracked tree moved, which is
    exactly when nobody is thinking about the pointer's prose — so a re-capture that took
    the defaults would drop the fixture's fetch story on the way past.
    """
    capture(repo, data_dir, store, url="https://example.com/acme.zip", note="the frozen fixture")

    kept = capture(repo, data_dir, store, force=True).pointer
    assert kept.url == "https://example.com/acme.zip"
    assert kept.note == "the frozen fixture"

    # Named explicitly, the new value wins — inheriting is what an *omission* means.
    said = capture(repo, data_dir, store, force=True, note="now with a defect").pointer
    assert said.note == "now with a defect"
    assert said.url == "https://example.com/acme.zip"


def test_a_re_capture_keeps_the_recorded_excludes_unless_new_ones_are_named(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """The `--exclude` globs travel with the pointer like `url` and `note` do.

    They shaped `tree_sha256`, so a bare `--force` that dropped them would either refuse the
    tree it accepted last time or record a digest the next verify_tree cannot reproduce.
    """
    (repo / ".venv").mkdir()
    capture(repo, data_dir, store, excludes=(".venv",))

    kept = capture(repo, data_dir, store, force=True).pointer
    assert kept.excludes == (".venv",)

    (repo / "build").mkdir()
    said = capture(repo, data_dir, store, force=True, excludes=(".venv", "build")).pointer
    assert said.excludes == (".venv", "build")


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


def test_capture_records_nothing_to_compare_for_an_out_of_tree_repo(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """A capture from elsewhere on disk has no in-tree source, and says so by leaving it empty.

    That is the exemption the freshness guard reads: a greenfield seed taken from a live
    session's workdir cannot drift from a tracked tree it never had.
    """
    pointer = capture(repo, data_dir, store).pointer
    assert pointer.source == ""
    assert pointer.tree_sha256


def test_capture_pins_a_repo_that_lives_under_the_data_directory(
    repo: Path, data_dir: Path, store: Path
) -> None:
    inside = data_dir / "apps" / "acme-api"
    shutil.copytree(repo, inside, symlinks=True)
    pointer = seeds.capture(inside, name="acme", data_dir=data_dir, store=store).pointer
    assert pointer.source == "apps/acme-api"
    pointer.verify_tree(inside)


def test_verify_tree_rejects_a_source_that_moved_after_capture(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """The whole point: the trials run the zip, so an unre-captured edit is invisible to them."""
    inside = data_dir / "apps" / "acme-api"
    shutil.copytree(repo, inside, symlinks=True)
    pointer = seeds.capture(inside, name="acme", data_dir=data_dir, store=store).pointer
    (inside / "README.md").write_text("acme, repaired\n", encoding="utf-8")
    with pytest.raises(PointerError, match="paddock seed capture"):
        pointer.verify_tree(inside)


def test_verify_tree_honours_the_recorded_excludes(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """A tree captured around a local environment verifies around it too.

    The digest was taken with the globs, so a verification without them hashes content the
    capture never saw and reports a drift nobody introduced — which is the F5 finding: a
    pointer whose freshness guard could not be reproduced from the pointer.
    """
    inside = data_dir / "apps" / "acme-api"
    shutil.copytree(repo, inside, symlinks=True)
    (inside / ".venv").mkdir()
    (inside / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    pointer = seeds.capture(
        inside, name="acme", data_dir=data_dir, store=store, excludes=(".venv",)
    ).pointer
    pointer.verify_tree(inside)
    # The excluded tree may churn freely; only what the capture saw is measured.
    (inside / ".venv" / "pyvenv.cfg").write_text("home = /opt\n", encoding="utf-8")
    pointer.verify_tree(inside)
    # And a real edit is still caught, with the flags the re-capture needs in the message.
    (inside / "README.md").write_text("acme, repaired\n", encoding="utf-8")
    with pytest.raises(PointerError, match=r"--force --exclude \.venv"):
        pointer.verify_tree(inside)


def test_verify_tree_ignores_the_source_directorys_own_git(
    repo: Path, data_dir: Path, store: Path
) -> None:
    """A digest that moved on `git gc` would report skew nobody introduced."""
    inside = data_dir / "apps" / "acme-api"
    shutil.copytree(repo, inside, symlinks=True)
    pointer = seeds.capture(inside, name="acme", data_dir=data_dir, store=store).pointer
    (inside / ".git" / "a-new-object").write_text("whatever\n", encoding="utf-8")
    pointer.verify_tree(inside)
